"""Resume canvas — the bound HTML skeleton, override diff, and merge.

The builder (GrapesJS, vendored, offline) edits a *view* of the resume; the
semantic truth stays the ``doc`` dict produced by
:func:`app.services.resume_builder.ResumeAssembler.build`. This module is the
contract between the two:

- :func:`render_skeleton` turns a ``doc`` into HTML whose content nodes carry
  ``data-nl-path`` (``contact.email``, ``experience[1].bullets[0]``).
- :func:`bound_values` reads those paths back out of any HTML the editor saved.
- :func:`diff_overrides` keeps only the paths the human actually changed — text
  that still equals the fact is *not* an override, so provenance is preserved.
- :func:`merge_doc` applies overrides to a fresh ``doc`` for PDF/DOCX/ATS-text
  export, so every format is built from one merged source.
- :func:`html_export` (the canvas, as a page) and :func:`text_export` (the
  ATS plain text) are the two renderers the builder downloads.

Nothing here calls the network, the AI or the store: pure functions, unit
tested. Raw resume text never appears — only assembled ``doc`` content.
"""

from __future__ import annotations

import copy
import html as html_lib
import re
from typing import Any

from selectolax.parser import HTMLParser

__all__ = [
    "DEFAULT_RESUME_CSS",
    "DEFAULT_SECTIONS",
    "bound_values",
    "diff_overrides",
    "get_path",
    "html_export",
    "merge_doc",
    "render_skeleton",
    "section_order",
    "set_path",
    "text_export",
]

#: Shipped with the builder so a first-time canvas (and its HTML export) looks
#: like a resume before the user touches a single style control. It is the
#: stylesheet GrapesJS's Style Manager edits through CSS variables.
DEFAULT_RESUME_CSS = """\
:root{--nl-accent:#1f4f8b;--nl-body:#16181d;--nl-muted:#5b6472;--nl-size:16px;--nl-gap:14px}
.nl-resume{max-width:820px;margin:0 auto;padding:28px 32px 40px;
  font-family:Georgia,'Times New Roman',serif;
  font-size:var(--nl-size);line-height:1.5;color:var(--nl-body);background:#fff}
.nl-section{margin:0 0 var(--nl-gap)}
.nl-h2{font:600 13px/1.2 system-ui,-apple-system,'Segoe UI',sans-serif;letter-spacing:.1em;
  text-transform:uppercase;color:var(--nl-accent);border-bottom:1.5px solid var(--nl-accent);
  margin:0 0 8px;padding-bottom:4px}
.nl-name{font-size:30px;font-weight:700;line-height:1.15;color:var(--nl-accent);margin:0 0 4px}
.nl-contact{font:14px/1.4 system-ui,-apple-system,'Segoe UI',sans-serif;
  color:var(--nl-muted);margin:0 0 6px}
.nl-contact [data-nl-path]{color:inherit}
.nl-sep{margin:0 8px;color:var(--nl-accent)}
.nl-summary-text{margin:0}
.nl-skills,.nl-certs{list-style:none;margin:0;padding:0;display:flex;flex-wrap:wrap;gap:6px}
.nl-chip,.nl-cert{font:13px/1.3 system-ui,-apple-system,'Segoe UI',sans-serif;background:#eef3fa;
  color:var(--nl-accent);border:1px solid #d5e2f3;border-radius:999px;padding:3px 10px}
.nl-role,.nl-project,.nl-edu{margin:0 0 12px;break-inside:avoid}
.nl-role-head{display:flex;justify-content:space-between;gap:12px;align-items:baseline}
.nl-role-title,.nl-project-title{font-size:17px;font-weight:700;margin:0;color:var(--nl-body)}
.nl-company,.nl-edu-school{font:15px/1.4 system-ui,-apple-system,'Segoe UI',sans-serif;
  color:var(--nl-muted);margin:0}
.nl-edu-degree{font-weight:700;margin:0}
.nl-period{font:13px/1.3 system-ui,-apple-system,'Segoe UI',sans-serif;
  color:var(--nl-muted);white-space:nowrap}
.nl-bullets{margin:6px 0 0;padding-left:20px}
.nl-bullets li{margin:0 0 4px}
.nl-certs{display:block}
.nl-cert{display:inline-block;margin:0 6px 6px 0}"""

#: Section order of the canvas (also the default order used by the renderer).
DEFAULT_SECTIONS: tuple[str, ...] = (
    "header",
    "summary",
    "skills",
    "experience",
    "projects",
    "education",
    "certifications",
)

_SECTION_LABELS: dict[str, str] = {
    "header": "",
    "summary": "Summary",
    "skills": "Skills",
    "experience": "Experience",
    "projects": "Projects",
    "education": "Education",
    "certifications": "Certifications",
}

_WS_RE = re.compile(r"[\s ]+")
_PATH_RE = re.compile(r"([^[.\]]+)|\[(\d+)\]")


# ---------------------------------------------------------------------------
# path helpers
# ---------------------------------------------------------------------------


def _tokens(path: str) -> list[str | int]:
    out: list[str | int] = []
    for match in _PATH_RE.finditer(path):
        key, index = match.group(1), match.group(2)
        out.append(int(index) if index is not None else key)
    return out


def get_path(doc: Any, path: str) -> Any:
    """Read ``a.b[0].c`` from the doc; missing branches yield ``None``."""
    node = doc
    for token in _tokens(path):
        if isinstance(node, dict):
            node = node.get(token) if isinstance(token, str) else None
        elif isinstance(node, list):
            node = node[token] if isinstance(token, int) and 0 <= token < len(node) else None
        else:
            return None
        if node is None:
            return None
    return node


def set_path(doc: dict[str, Any], path: str, value: Any) -> bool:
    """Write ``value`` at ``path``; returns False when the path cannot exist."""
    tokens = _tokens(path)
    if not tokens:
        return False
    node: Any = doc
    for position, token in enumerate(tokens[:-1]):
        nxt = tokens[position + 1]
        if isinstance(node, dict):
            if token not in node or not isinstance(node[token], (dict, list)):
                node[token] = [] if isinstance(nxt, int) else {}
            node = node[token]
        elif isinstance(node, list):
            if not isinstance(token, int) or not 0 <= token < len(node):
                return False
            node = node[token]
        else:
            return False
    last = tokens[-1]
    if isinstance(node, dict) and isinstance(last, str):
        node[last] = value
        return True
    if isinstance(node, list) and isinstance(last, int) and 0 <= last < len(node):
        node[last] = value
        return True
    return False


def normalize(value: Any) -> str:
    """Comparison key for text: entities decoded, whitespace collapsed."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return _WS_RE.sub(" ", str(value)).strip()


# ---------------------------------------------------------------------------
# skeleton
# ---------------------------------------------------------------------------


def _esc(value: Any) -> str:
    return html_lib.escape(normalize(value), quote=False)


def _leaf(path: str, value: Any, tag: str = "span", cls: str = "") -> str:
    class_attr = f' class="{cls}"' if cls else ""
    return f'<{tag}{class_attr} data-nl-path="{path}">{_esc(value)}</{tag}>'


def _heading(label: str) -> str:
    return f'<h2 class="nl-h2">{_esc(label)}</h2>'


def _section(name: str, body: str) -> str:
    label = _SECTION_LABELS.get(name, name.title())
    inner = f"{_heading(label)}{body}" if label else body
    return f'<section class="nl-section nl-{name}" data-nl-section="{name}">{inner}</section>'


def render_skeleton(
    doc: dict[str, Any], sections: list[str] | tuple[str, ...] | None = None
) -> str:
    """Bound, ATS-safe single-column HTML for the given assembled ``doc``.

    Every piece of content the human may edit sits on a ``data-nl-path`` leaf;
    headings and separators are structural (freely edited in the canvas, saved
    with the project, but never mixed into fact provenance).
    """
    order = list(sections or DEFAULT_SECTIONS)
    contact = doc.get("contact") or {}
    parts: dict[str, str] = {}
    # Sections with no evidence are omitted rather than shown as hollow
    # headings — the canvas mirrors what the profile can actually back up.
    present: set[str] = {"header"}

    parts["header"] = (
        '<div class="nl-name" data-nl-section-name="header">'
        + _leaf("contact.name", contact.get("name"), tag="div", cls="nl-name-text")
        + "</div>"
        + '<div class="nl-contact">'
        + _leaf("contact.email", contact.get("email"))
        + '<span class="nl-sep" aria-hidden="true">·</span>'
        + _leaf("contact.phone", contact.get("phone"))
        + '<span class="nl-sep" aria-hidden="true">·</span>'
        + _leaf("contact.location", contact.get("location"))
        + "</div>"
    )

    parts["summary"] = _leaf("summary", doc.get("summary"), tag="p", cls="nl-summary-text")
    if normalize(doc.get("summary")):
        present.add("summary")

    skills = list(doc.get("skills") or [])
    if skills:
        present.add("skills")
    chips = "".join(
        f'<li class="nl-chip" data-nl-path="skills[{i}]">{_esc(s)}</li>'
        for i, s in enumerate(skills)
    )
    parts["skills"] = f'<ul class="nl-skills" data-nl-repeat="skills">{chips}</ul>'

    roles: list[str] = []
    for i, role in enumerate(doc.get("experience") or []):
        bullets = [
            f'<li data-nl-path="experience[{i}].bullets[{j}]">{_esc(b)}</li>'
            for j, b in enumerate(role.get("bullets") or [])
        ]
        if not bullets:
            bullets = [f'<li data-nl-path="experience[{i}].bullets[0]"></li>']
        roles.append(
            f'<article class="nl-role" data-nl-repeat="experience">'
            f'<div class="nl-role-head">'
            f"{_leaf(f'experience[{i}].role', role.get('role'), tag='h3', cls='nl-role-title')}"
            f"{_leaf(f'experience[{i}].period', role.get('period'), tag='span', cls='nl-period')}"
            f"</div>"
            f"{_leaf(f'experience[{i}].company', role.get('company'), tag='div', cls='nl-company')}"
            f'<ul class="nl-bullets">{"".join(bullets)}</ul>'
            f"</article>"
        )
    parts["experience"] = "".join(roles)
    if roles:
        present.add("experience")

    projects: list[str] = []
    for i, project in enumerate(doc.get("projects") or []):
        bullets = [
            f'<li data-nl-path="projects[{i}].bullets[{j}]">{_esc(b)}</li>'
            for j, b in enumerate(project.get("bullets") or [])
        ]
        if not bullets:
            bullets = [f'<li data-nl-path="projects[{i}].bullets[0]"></li>']
        title = _leaf(
            f"projects[{i}].title", project.get("title"), tag="h3", cls="nl-project-title"
        )
        projects.append(
            f'<article class="nl-project" data-nl-repeat="projects">'
            f"{title}"
            f'<ul class="nl-bullets">{"".join(bullets)}</ul>'
            f"</article>"
        )
    parts["projects"] = "".join(projects)
    if projects:
        present.add("projects")

    education: list[str] = []
    for i, entry in enumerate(doc.get("education") or []):
        education.append(
            '<article class="nl-edu" data-nl-repeat="education">'
            + _leaf(f"education[{i}].degree", entry.get("degree"), tag="div", cls="nl-edu-degree")
            + _leaf(f"education[{i}].school", entry.get("school"), tag="div", cls="nl-edu-school")
            + _leaf(f"education[{i}].period", entry.get("period"), tag="span", cls="nl-period")
            + "</article>"
        )
    parts["education"] = "".join(education)
    if education:
        present.add("education")

    certs = [
        f'<li class="nl-cert" data-nl-path="certifications[{i}]">{_esc(c)}</li>'
        for i, c in enumerate(doc.get("certifications") or [])
    ]
    parts["certifications"] = (
        f'<ul class="nl-certs" data-nl-repeat="certifications">{"".join(certs)}</ul>'
    )
    if certs:
        present.add("certifications")

    blocks = [
        _section(name, parts.get(name, "")) for name in order if name in parts and name in present
    ]
    return (
        '<div class="nl-resume" data-nl="resume" data-nl-format="v1">' + "".join(blocks) + "</div>"
    )


# ---------------------------------------------------------------------------
# reading the editor back
# ---------------------------------------------------------------------------


def bound_values(markup: str) -> dict[str, str]:
    """``{path: text}`` for every non-container bound node in ``markup``."""
    if not markup or "data-nl-path" not in markup:
        return {}
    out: dict[str, str] = {}
    tree = HTMLParser(markup)
    for node in tree.css("[data-nl-path]"):
        attrs = node.attributes or {}
        if "data-nl-repeat" in attrs:  # container: children carry the paths
            continue
        path = (attrs.get("data-nl-path") or "").strip()
        if not path:
            continue
        out[path] = normalize(node.text())
    return out


def section_order(markup: str) -> list[str]:
    """Section order as laid out in the canvas (the layer manager is the UI)."""
    if not markup or "data-nl-section" not in markup:
        return list(DEFAULT_SECTIONS)
    seen: list[str] = []
    for node in HTMLParser(markup).css("[data-nl-section]"):
        name = (node.attributes or {}).get("data-nl-section")
        if name and name not in seen:
            seen.append(name)
    return seen or list(DEFAULT_SECTIONS)


def diff_overrides(markup: str, doc: dict[str, Any]) -> dict[str, str]:
    """Only the paths the human changed (text differing from the fact)."""
    overrides: dict[str, str] = {}
    for path, text in bound_values(markup).items():
        current = normalize(get_path(doc, path))
        if text != current:
            overrides[path] = text
    return overrides


def merge_doc(doc: dict[str, Any], overrides: dict[str, str] | None) -> dict[str, Any]:
    """A copy of ``doc`` with human overrides applied, for every export."""
    merged = copy.deepcopy(doc)
    for path, value in (overrides or {}).items():
        set_path(merged, path, value)
    return merged


def text_export(doc: dict[str, Any], sections: list[str] | tuple[str, ...] | None = None) -> str:
    """ATS plain text: contact details, headings, dates and bullets.

    :meth:`app.services.resume_builder.ResumeAssembler.resume_text` is
    deliberately flat — it is the string the ATS *score* is computed from.
    This is the file a human pastes into an application portal, so it keeps
    everything a parser looks for (email, phone, employers, periods) and
    follows the section order the canvas is in. Empty sections are omitted,
    exactly like the skeleton.
    """
    order = list(sections or DEFAULT_SECTIONS)
    contact = doc.get("contact") or {}

    def joined(*parts: Any) -> str:
        return " — ".join(text for text in (normalize(p) for p in parts) if text)

    blocks: dict[str, list[str]] = {}
    contact_line = "  ".join(
        text
        for text in (
            normalize(contact.get("email")),
            normalize(contact.get("phone")),
            normalize(contact.get("location")),
        )
        if text
    )
    blocks["header"] = [t for t in (normalize(contact.get("name")), contact_line) if t]

    summary = normalize(doc.get("summary"))
    blocks["summary"] = [summary] if summary else []
    skills = [normalize(s) for s in (doc.get("skills") or []) if normalize(s)]
    blocks["skills"] = [", ".join(skills)] if skills else []

    experience: list[str] = []
    for i, role in enumerate(doc.get("experience") or []):
        if i:
            experience.append("")
        head = joined(role.get("role"), role.get("company"))
        period = normalize(role.get("period"))
        if period:
            head = f"{head} ({period})" if head else period
        if head:
            experience.append(head)
        experience += [
            f"  \u2022 {normalize(b)}" for b in (role.get("bullets") or []) if normalize(b)
        ]
    blocks["experience"] = experience

    projects: list[str] = []
    for i, project in enumerate(doc.get("projects") or []):
        if i:
            projects.append("")
        title = normalize(project.get("title"))
        if title:
            projects.append(title)
        projects += [
            f"  \u2022 {normalize(b)}" for b in (project.get("bullets") or []) if normalize(b)
        ]
    blocks["projects"] = projects

    education: list[str] = []
    for entry in doc.get("education") or []:
        head = joined(entry.get("degree"), entry.get("school"))
        period = normalize(entry.get("period"))
        if period:
            head = f"{head} ({period})" if head else period
        if head:
            education.append(head)
    blocks["education"] = education
    blocks["certifications"] = [
        normalize(c) for c in (doc.get("certifications") or []) if normalize(c)
    ]

    out: list[str] = []
    for name in order:
        body = blocks.get(name) or []
        if not body:
            continue
        label = _SECTION_LABELS.get(name, name.title())
        if label:
            out += [label.upper(), ""]
        out += body
        out.append("")
    while out and not out[-1].strip():
        out.pop()
    return "\n".join(out) + ("\n" if out else "")


def html_export(markup: str, css: str, *, title: str = "Resume") -> str:
    """Self-contained HTML (inline stylesheet) — the visual export."""
    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{html_lib.escape(title)}</title>\n"
        "<style>\n"
        "body{margin:0;background:#fff;color:#111;"
        "font:16px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}\n"
        f"{css}\n"
        "</style>\n</head>\n<body>\n"
        f"{markup}\n</body>\n</html>\n"
    )
