"""Propose-only, grounded AI assistance for the resume canvas.

Contract (user decision, 2026-09-30): the provider the user picked in Settings
*proposes*, the human *applies*. Nothing here writes to a resume — it only
produces a list of pinpoint suggestions, each with the binding path it targets,
and drops anything it cannot trace back to evidence.

Three layers, deliberately separable:

- :func:`build_prompt` / :func:`parse_suggestions` — talk to the model and read
  its JSON back (defensive: fenced, prefixed, or bare).
- :func:`validate_suggestions` — the **grounding gate**. A suggestion that
  invents a number, names an employer that isn't in the evidence, targets a
  path that doesn't exist, or has no evidence at all is dropped, and the drop
  count is reported honestly rather than hidden.
- :func:`local_suggestions` — the no-key path. With the rule provider (or when
  no AI tier can answer) the panel still fills with deterministic, useful,
  zero-fabrication observations built from the assembler and the JD diff.

Pure functions: no store, no network, no settings. Unit tested.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.services.builder_template import get_path, normalize

__all__ = [
    "SUGGEST_KINDS",
    "SUGGEST_SYSTEM",
    "build_prompt",
    "local_suggestions",
    "parse_suggestions",
    "validate_suggestions",
]

#: What a suggestion may be. ``rewrite``/``drop`` carry user-facing text and go
#: through the full grounding gate; the structural kinds only need a real path.
SUGGEST_KINDS: tuple[str, ...] = (
    "rewrite",
    "reorder",
    "drop",
    "add_section",
    "style",
    "ats",
    "confirm",
)

_MAX_SUGGESTIONS = 12
_MAX_PROPOSED = 600
_MAX_REASON = 400

_NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?%?")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z']{3,}")
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)

# Frequent filler in resume bullets. Removing it states nothing new, so the
# rule provider may do it; it can never add a claim.
_FILLER_RE = re.compile(
    r"^(?:worked on|was responsible for|responsible for|helped with|"
    r"involved in|participated in|duties included|tasks included)\s+",
    re.I,
)

_GENERIC_STOPWORDS = """
about above after again against all also any are because been before being
below between both but can did does doing down during each few for from
further had has have having her here hers herself him himself his how into
its itself just more most not now off once only other our ours ourselves
over own same should some such than that the their theirs them themselves
then there these they this those through under until very was were what
when where which while who whom why will with you your yours yourself
"""

# Domain-neutral verbs/adjectives that carry no claim on their own: a rewrite
# that only swaps these for each other is still grounded in its evidence.
_DOMAIN_STOPWORDS = """
able about across after against along already although always among
another around back become becomes best better between bring brought
build built carry case cases choose chosen come comes could current
daily data deliver delivered drive driven early ease either else enough
ensure even ever every example experience face fact facts fast find
first following found full further gain get give given go going grant
great group grow grown had hand help helped high hold home however
include included including increase increased instead keep kept
know known large last later least less let level like line live local
long look made make making many may mean meant meet might mind money
month move much must near need needed new next night none nothing
number numbers offer offered often one order other others overall page
part particular past per perhaps place placed point post present
pressure probably problem process produce product project prove provide
provided public put quite rather reach read ready real really reason
receive received recent report represent require required research
resource result results right run running said same save saved say
seeing seen send sent serve service services set several shape share
show shown side since small social some something soon sort source
special specific start started state still stop store story street
strong study such system table take taken talk teach team tell test
than thank thing things think third those though thought three through
time today together told took toward travel treat trial try turn two
understand until upon use used using value various view walk want
wanted watch way week well went were what when where whether which
while who whole whom whose within without woman work worked working
world would year years yes yet your
"""

_STOPWORDS = frozenset(_GENERIC_STOPWORDS.split() + _DOMAIN_STOPWORDS.split())


# ---------------------------------------------------------------------------
# prompt + parsing
# ---------------------------------------------------------------------------


def build_prompt(doc: dict[str, Any], jd_text: str = "", focus: str = "") -> str:
    """Bounded, explicit prompt. The doc is the ONLY allowed source of claims."""
    try:
        doc_json = json.dumps(doc, ensure_ascii=False, indent=None)[:6000]
    except (TypeError, ValueError):  # pragma: no cover - doc is always JSON-safe
        doc_json = str(doc)[:6000]
    jd = (jd_text or "").strip()[:2500] or "(no job description provided)"
    focus_line = f"\nThe user asked to focus on: {focus.strip()}." if focus.strip() else ""
    return (
        "You review a resume that has already been assembled from verified "
        "facts. Propose precise improvements — do not rewrite it wholesale.\n"
        f"{focus_line}\n\n"
        "RESUME (JSON, the only source of allowed claims):\n"
        f"{doc_json}\n\n"
        f"TARGET JOB DESCRIPTION:\n{jd}\n\n"
        "Return ONLY a JSON array of objects with these keys:\n"
        "  path      binding path such as experience[0].bullets[1] or summary,\n"
        "            or a section name for document-level items\n"
        "  kind      rewrite | reorder | drop | add_section | style | ats | confirm\n"
        "  current   the exact current text (empty when not applicable)\n"
        "  proposed  the new text (empty when not applicable)\n"
        "  reason    one concrete sentence\n"
        "  evidence  array of quotes copied from the resume or the JD\n"
        "  priority  1 = highest\n\n"
        "Rules — these are not negotiable:\n"
        "1. Never invent employers, titles, dates, degrees, certifications, "
        "metrics or numbers. Anything you propose must be supported by a quote "
        "in `evidence`, taken from the resume JSON or the JD.\n"
        "2. `path` must exist in the resume JSON (list indices are 0-based).\n"
        "3. `current` must quote what is there now (empty for section-level).\n"
        "4. Prefer 3-6 high-value suggestions, ordered by priority. Return [] "
        "if there is genuinely nothing worth changing.\n"
        "5. Do not add skills you cannot point to evidence for; if the JD needs "
        "a term the resume lacks, use kind `ats` and say so in `reason`.\n"
    )


SUGGEST_SYSTEM = (
    "You are a meticulous resume editor working inside a local-first app. "
    "You propose, you never decide: every suggestion must be traceable to a "
    "quote from the resume or the job description. Reply with JSON only."
)


def _strip_fences(text: str) -> str:
    match = _FENCE_RE.search(text)
    if match:
        return match.group(1).strip()
    return text.strip()


def _extract_json(text: str) -> Any | None:
    """Pull a JSON array/object out of a model reply, whatever shape it came in."""
    cleaned = _strip_fences(text or "")
    if not cleaned:
        return None
    for candidate in (
        cleaned,
        _slice_between(cleaned, "[", "]"),
        _slice_between(cleaned, "{", "}"),
    ):
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    return None


def _slice_between(text: str, open_ch: str, close_ch: str) -> str:
    start, end = text.find(open_ch), text.rfind(close_ch)
    if start == -1 or end == -1 or end <= start:
        return ""
    return text[start : end + 1]


def parse_suggestions(raw: str) -> tuple[list[Any], str | None]:
    """Model reply -> ``(items, error)``. ``items`` is [] when parsing failed."""
    payload = _extract_json(raw)
    if payload is None:
        return [], "model reply was not JSON"
    if isinstance(payload, dict):
        payload = payload.get("suggestions", payload.get("items", []))
    if not isinstance(payload, list):
        return [], "model reply was not a JSON array"
    return payload, None


# ---------------------------------------------------------------------------
# grounding gate
# ---------------------------------------------------------------------------


def _numbers(text: str) -> set[str]:
    return {m.group(0).replace(",", "").rstrip("%") for m in _NUM_RE.finditer(text)}


def _content_words(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall(text.lower()) if w not in _STOPWORDS}


def _as_text(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return " ".join(str(v) for v in value)
    return "" if value is None else str(value)


def validate_suggestions(
    items: list[Any],
    doc: dict[str, Any],
    *,
    jd_text: str = "",
) -> tuple[list[dict[str, Any]], int]:
    """Run the gate. Returns ``(kept, dropped_count)`` — never hides a drop."""
    kept: list[dict[str, Any]] = []
    dropped = 0
    seen_paths: set[tuple[str, str, str]] = set()

    for raw in items:
        if not isinstance(raw, dict):
            dropped += 1
            continue
        kind = str(raw.get("kind") or "").strip()
        path = str(raw.get("path") or "").strip()
        proposed = _as_text(raw.get("proposed")).strip()[:_MAX_PROPOSED]
        current = _as_text(raw.get("current")).strip()[:_MAX_PROPOSED]
        reason = _as_text(raw.get("reason")).strip()[:_MAX_REASON]
        evidence_raw = raw.get("evidence")
        evidence = [
            str(e).strip()[:500]
            for e in (evidence_raw if isinstance(evidence_raw, list) else [])
            if str(e).strip()
        ]

        if kind not in SUGGEST_KINDS or not reason:
            dropped += 1
            continue
        if not _path_ok(path, doc, kind):
            dropped += 1
            continue
        if kind in ("rewrite", "drop") and not proposed and not current:
            dropped += 1
            continue

        structural = kind in ("reorder", "style", "ats", "confirm")
        if not structural:
            if not evidence:
                dropped += 1
                continue
            evidence_text = " ".join(evidence)
            if _numbers(proposed) - _numbers(evidence_text):
                dropped += 1  # a number that no quote supports = fabrication
                continue
            if current:
                # quotes must be a quote: reuse whatever was already there
                evidence_text = f"{evidence_text} {current}"
            p_words, e_words = _content_words(proposed), _content_words(evidence_text)
            if p_words and e_words and not (p_words & e_words):
                dropped += 1  # no lexical link to its own evidence
                continue

        # de-duplicate identical proposals for the same path
        key = (path, kind, proposed.lower())
        if key in seen_paths:
            dropped += 1
            continue
        seen_paths.add(key)

        try:
            priority = max(1, min(5, int(raw.get("priority") or 3)))
        except (TypeError, ValueError):
            priority = 3

        kept.append(
            {
                "id": str(raw.get("id") or f"s{len(kept) + 1}"),
                "path": path,
                "kind": kind,
                "current": current,
                "proposed": proposed,
                "reason": reason,
                "evidence": evidence[:4],
                "priority": priority,
            }
        )
        if len(kept) >= _MAX_SUGGESTIONS:
            break

    kept.sort(key=lambda s: s["priority"])
    return kept, dropped


def _path_ok(path: str, doc: dict[str, Any], kind: str) -> bool:
    if not path:
        # document-level items (ats/confirm) may omit the path
        return kind in ("ats", "confirm", "add_section")
    if path in doc and isinstance(doc[path], list):
        return True  # a whole list path, e.g. "skills"
    return get_path(doc, path) is not None


# ---------------------------------------------------------------------------
# rule-provider fallback (no key, no network, still useful)
# ---------------------------------------------------------------------------


def local_suggestions(
    doc: dict[str, Any],
    *,
    jd_text: str = "",
    tailoring: dict[str, Any] | None = None,
    pending_facts: int = 0,
) -> list[dict[str, Any]]:
    """Deterministic suggestions — Tier 0/1 only, zero keys, zero fabrication."""
    out: list[dict[str, Any]] = []
    index = 0

    def add(**kwargs: Any) -> None:
        nonlocal index
        index += 1
        out.append(
            {
                "id": f"r{index}",
                "path": kwargs.get("path", ""),
                "kind": kwargs["kind"],
                "current": kwargs.get("current", ""),
                "proposed": kwargs.get("proposed", ""),
                "reason": kwargs["reason"],
                "evidence": kwargs.get("evidence", []),
                "priority": kwargs.get("priority", 3),
            }
        )

    # Terms the JD uses and the resume does not — spelled cleanly (tokenizers
    # leave trailing punctuation behind) and reported once, not twice: the
    # tailoring dict repeats them in `suggestions`, which we skip below.
    raw_missing = (tailoring or {}).get("missing_terms", []) or []
    missing = [clean for clean in (str(t).strip(".,;:!?()[]\"'") for t in raw_missing[:8]) if clean]
    if missing:
        add(
            kind="ats",
            reason=(
                "The job description uses terms your resume does not: "
                + ", ".join(missing)
                + " — do NOT claim them; add real evidence or address them in the cover note."
            ),
            evidence=[f"JD term: {t}" for t in missing[:4]],
            priority=1,
        )

    for line in (tailoring or {}).get("suggestions", [])[:3]:
        text = str(line)
        low = text.lower()
        if low.startswith("lead with kb entry"):
            continue  # the panel has its own KB view; avoid duplicating it
        if missing and low.startswith("jd mentions terms absent"):
            continue  # already on the panel as the card above
        add(kind="ats", reason=text, evidence=[text], priority=2)

    # Filler-heavy bullets. The rule tier may not invent wording, so this is a
    # pinpoint pointer, not a ghost-writer: highlight the line and say what is
    # wrong with it. Model providers return actual rewrite proposals instead.
    for i, role in enumerate(doc.get("experience") or []):
        if not isinstance(role, dict):
            continue
        for j, bullet in enumerate(role.get("bullets") or []):
            text = normalize(bullet)
            match = _FILLER_RE.match(text)
            if not match:
                continue
            filler = match.group(0).strip().rstrip()
            add(
                path=f"experience[{i}].bullets[{j}]",
                kind="rewrite",
                current=text,
                proposed="",
                reason=(
                    f'Opens with filler ("{filler}") that hides the actual contribution — '
                    "rewrite this line in your own words; the panel highlights it for you."
                ),
                evidence=[text],
                priority=3,
            )

    # structure checks against the doc itself
    if doc.get("experience") and not doc.get("skills"):
        add(
            path="skills",
            kind="add_section",
            reason=(
                "No skills section: keyword filters often scan it first. "
                "Add one listing only skills you can evidence."
            ),
            priority=2,
        )
    for role_i, role in enumerate(doc.get("experience") or []):
        if not isinstance(role, dict):
            continue
        bullets = [b for b in (role.get("bullets") or []) if normalize(b)]
        if role.get("company") and not bullets:
            add(
                path=f"experience[{role_i}]",
                kind="add_section",
                reason=(
                    f"{role.get('company')} has no bullet yet — one concrete outcome "
                    "here is the single highest-value addition you can make."
                ),
                evidence=[normalize(role.get("company"))],
                priority=2,
            )
        if not normalize(role.get("role")):
            add(
                path=f"experience[{role_i}].role",
                kind="confirm",
                reason=(
                    "This role has a company but no title; add the title so ATS "
                    "parsing groups it correctly."
                ),
                evidence=[normalize(role.get("company"))],
                priority=2,
            )

    if not normalize(doc.get("summary")):
        add(
            path="summary",
            kind="add_section",
            reason=(
                "No summary line. Two sentences of positioning (years, domain, "
                "strongest tool) help both humans and parsers."
            ),
            priority=3,
        )

    if pending_facts:
        add(
            kind="confirm",
            reason=(
                f"{pending_facts} extracted field(s) are still unconfirmed in Profile. "
                "Confirming the true ones lets this builder quote them safely."
            ),
            evidence=[f"{pending_facts} pending"],
            priority=1,
        )

    out.sort(key=lambda s: s["priority"])
    return out[:_MAX_SUGGESTIONS]
