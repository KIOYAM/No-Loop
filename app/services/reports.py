"""Report builders (user request 2026-09-29): downloadable, shareable output.

Four report families, each renderable as CSV, JSON or a self-contained styled
HTML document:

``applications``  every ledger record with evidence, artifacts and timing
``companies``     one row per company — what happened there, and when
``runs``          what the agents actually did, step by step
``facts``         the fact ledger with confirmation states (audit view)

Nothing here reaches the network; files are assembled in memory and streamed
by the local UI server as an attachment.
"""

from __future__ import annotations

import csv
import html
import io
import json
from datetime import UTC, datetime
from typing import Any

__all__ = ["ReportService", "REPORT_KINDS", "REPORT_FORMATS"]

REPORT_KINDS = ("applications", "companies", "runs", "facts", "summary")
REPORT_FORMATS = ("csv", "json", "html")

_APPLICATION_COLUMNS = (
    "id",
    "company",
    "title",
    "status",
    "entry_method",
    "job_id",
    "application_url",
    "created_at",
    "updated_at",
    "follow_up_date",
    "artifacts",
    "evidence",
    "failure",
    "notes",
    "profile_id",
)

_COMPANY_COLUMNS = (
    "company",
    "applications",
    "statuses",
    "entry_methods",
    "first_applied",
    "last_activity",
    "outcome",
    "urls",
)

_RUN_COLUMNS = (
    "run_id",
    "started_at",
    "duration_ms",
    "step",
    "label",
    "status",
    "company",
    "title",
    "score",
    "detail",
)

_FACT_COLUMNS = (
    "id",
    "field_class",
    "value",
    "skill",
    "confidence",
    "state",
    "extraction_rule",
    "document_id",
    "created_at",
    "decided_at",
)

_STATUS_ORDER = (
    "offer",
    "interview",
    "submitted",
    "review_required",
    "verification_required",
    "drafted",
    "ready",
    "shortlisted",
    "discovered",
    "failed",
    "rejected",
    "withdrawn",
    "closed",
    "rejected_by_user",
    "skipped",
)


class ReportService:
    """Reads the store + ledger and renders report documents."""

    def __init__(self, store: Any, ledger: Any) -> None:
        self.store = store
        self.ledger = ledger

    # -- data -------------------------------------------------------------

    def _applications(self, profile_id: str | None) -> list[Any]:
        records = self.ledger.all()
        if profile_id:
            records = [r for r in records if r.profile_id == profile_id]
        return sorted(records, key=lambda r: r.updated_at, reverse=True)

    def _runs(self, profile_id: str | None) -> list[dict[str, Any]]:
        runs = [
            r
            for r in self.store.all("runs").values()
            if isinstance(r, dict) and (not profile_id or r.get("profile_id") == profile_id)
        ]
        return sorted(runs, key=lambda r: str(r.get("started_at", "")), reverse=True)

    def records(self, report: str, profile_id: str | None = None) -> list[dict[str, Any]]:
        """Normalized rows for one report kind (keys match the column tuples)."""
        if report == "applications":
            return [self._application_row(a) for a in self._applications(profile_id)]
        if report == "companies":
            return self._company_rows(profile_id)
        if report == "runs":
            return self._run_rows(profile_id)
        if report == "facts":
            return self._fact_rows(profile_id)
        if report == "summary":
            # rows must match the (metric, value) columns or the CSV/HTML
            # renderings would be a row of empty cells
            return [
                {
                    "metric": key,
                    "value": json.dumps(value, ensure_ascii=False)
                    if isinstance(value, (dict, list))
                    else value,
                }
                for key, value in self.summary(profile_id).items()
            ]
        raise ValueError(f"unknown report: {report}")

    def columns(self, report: str) -> tuple[str, ...]:
        # raises ValueError (not KeyError) so callers can map it to a 400 with
        # a readable message, exactly like records() does
        known = {
            "applications": _APPLICATION_COLUMNS,
            "companies": _COMPANY_COLUMNS,
            "runs": _RUN_COLUMNS,
            "facts": _FACT_COLUMNS,
            "summary": ("metric", "value"),
        }
        if report not in known:
            raise ValueError(f"unknown report: {report}")
        return known[report]

    @staticmethod
    def _application_row(a: Any) -> dict[str, Any]:
        return {
            "id": a.id,
            "company": a.company,
            "title": a.title,
            "status": a.status.value,
            "entry_method": a.entry_method.value,
            "job_id": a.job_id or "",
            "application_url": a.application_url or "",
            "created_at": a.created_at.isoformat(),
            "updated_at": a.updated_at.isoformat(),
            "follow_up_date": a.follow_up_date or "",
            "artifacts": ", ".join(a.artifact_ids),
            "evidence": json.dumps(a.submission_evidence or {}, ensure_ascii=False),
            "failure": json.dumps(a.failure or {}, ensure_ascii=False),
            "notes": a.notes or "",
            "profile_id": a.profile_id,
        }

    def _company_rows(self, profile_id: str | None) -> list[dict[str, Any]]:
        grouped: dict[str, list[Any]] = {}
        for record in self._applications(profile_id):
            grouped.setdefault(record.company, []).append(record)

        rows: list[dict[str, Any]] = []
        for company, records in sorted(grouped.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            statuses = sorted(
                {r.status.value for r in records},
                key=lambda s: _STATUS_ORDER.index(s) if s in _STATUS_ORDER else 99,
            )
            timestamps = sorted(
                r.updated_at if r.updated_at.tzinfo else r.updated_at.replace(tzinfo=UTC)
                for r in records
            )
            urls = sorted({r.application_url for r in records if r.application_url})
            rows.append(
                {
                    "company": company,
                    "applications": len(records),
                    "statuses": ", ".join(statuses),
                    "entry_methods": ", ".join(sorted({r.entry_method.value for r in records})),
                    "first_applied": timestamps[0].date().isoformat() if timestamps else "",
                    "last_activity": timestamps[-1].date().isoformat() if timestamps else "",
                    "outcome": statuses[0] if statuses else "",
                    "urls": " ".join(urls),
                }
            )
        return rows

    def _run_rows(self, profile_id: str | None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for run in self._runs(profile_id):
            for step in run.get("steps", []):
                rows.append(
                    {
                        "run_id": run.get("run_id", ""),
                        "started_at": run.get("started_at", ""),
                        "duration_ms": run.get("duration_ms", ""),
                        "step": step.get("step", ""),
                        "label": step.get("label", ""),
                        "status": step.get("status", ""),
                        "company": step.get("company") or "(pipeline)",
                        "title": step.get("title") or "",
                        "score": step.get("score") if step.get("score") is not None else "",
                        "detail": step.get("detail", ""),
                    }
                )
        return rows

    def _fact_rows(self, profile_id: str | None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for raw in self.store.all("facts").values():
            if profile_id and raw.get("profile_id") != profile_id:
                continue
            provenance = raw.get("provenance") or {}
            skill = raw.get("skill") or {}
            value = raw.get("value")
            if value is None and skill:
                value = skill.get("name")
            rows.append(
                {
                    "id": raw.get("id", ""),
                    "field_class": raw.get("field_class", ""),
                    "value": json.dumps(value, ensure_ascii=False)
                    if isinstance(value, (list, dict))
                    else value,
                    "skill": skill.get("name", ""),
                    "confidence": raw.get("confidence", ""),
                    "state": raw.get("state", ""),
                    "extraction_rule": provenance.get("extraction_rule", ""),
                    "document_id": provenance.get("document_id", ""),
                    "created_at": raw.get("created_at", ""),
                    "decided_at": raw.get("decided_at") or "",
                }
            )
        return rows

    def summary(self, profile_id: str | None = None) -> dict[str, Any]:
        """KPI block used by the dashboard and the report header."""
        records = self._applications(profile_id)
        by_status: dict[str, int] = {}
        by_method: dict[str, int] = {}
        companies: set[str] = set()
        for r in records:
            by_status[r.status.value] = by_status.get(r.status.value, 0) + 1
            by_method[r.entry_method.value] = by_method.get(r.entry_method.value, 0) + 1
            companies.add(r.company)

        submitted = by_status.get("submitted", 0)
        interviews = by_status.get("interview", 0)
        offers = by_status.get("offer", 0)
        runs = self._runs(profile_id)
        facts = [
            f
            for f in self.store.all("facts").values()
            if not profile_id or f.get("profile_id") == profile_id
        ]
        confirmed = sum(1 for f in facts if f.get("state") == "confirmed")
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "profile_id": profile_id or "all",
            "total_applications": len(records),
            "distinct_companies": len(companies),
            "submitted": submitted,
            "interviews": interviews,
            "offers": offers,
            "needs_review": by_status.get("review_required", 0)
            + by_status.get("verification_required", 0)
            + by_status.get("failed", 0),
            "interview_rate": round(interviews / submitted, 3) if submitted else 0.0,
            "by_status": dict(sorted(by_status.items(), key=lambda kv: -kv[1])),
            "by_entry_method": by_method,
            "agent_runs": len(runs),
            "agent_steps": sum(len(r.get("steps", [])) for r in runs),
            "last_agent_run": runs[0].get("started_at") if runs else None,
            "facts_total": len(facts),
            "facts_confirmed": confirmed,
        }

    # -- rendering ----------------------------------------------------------

    def to_csv(self, report: str, profile_id: str | None = None) -> str:
        columns = self.columns(report)
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(columns), extrasaction="ignore")
        writer.writeheader()
        for row in self.records(report, profile_id):
            writer.writerow(row)
        return buffer.getvalue()

    def to_json(self, report: str, profile_id: str | None = None) -> str:
        return json.dumps(
            {
                "report": report,
                "generated_at": datetime.now(UTC).isoformat(),
                "profile_id": profile_id or "all",
                "summary": self.summary(profile_id),
                "rows": self.records(report, profile_id),
            },
            indent=2,
            default=str,
            ensure_ascii=False,
        )

    def to_html(self, report: str, profile_id: str | None = None) -> str:
        columns = self.columns(report)
        rows = self.records(report, profile_id)
        stats = self.summary(profile_id)
        title = f"No_Loop · {report.title()} report"

        cards = "".join(
            _card(label, value)
            for label, value in (
                ("Applications", stats["total_applications"]),
                ("Companies", stats["distinct_companies"]),
                ("Submitted", stats["submitted"]),
                ("Interviews", stats["interviews"]),
                ("Offers", stats["offers"]),
                ("Agent runs", stats["agent_runs"]),
                ("Facts confirmed", f"{stats['facts_confirmed']}/{stats['facts_total']}"),
            )
        )
        head = "".join(f"<th>{html.escape(c.replace('_', ' ').title())}</th>" for c in columns)
        body = "".join(
            "<tr>" + "".join(f"<td>{_cell(row.get(col))}</td>" for col in columns) + "</tr>"
            for row in rows
        )
        return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
  :root {{ --ink:#0f1420; --dim:#5b6b85; --line:#e3e8f2; --accent:#0a66c2; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; padding:32px; font:14px/1.5 "Segoe UI",system-ui,sans-serif;
         color:var(--ink); background:#fff; }}
  header {{ border-bottom:3px solid var(--accent); padding-bottom:14px; margin-bottom:22px; }}
  h1 {{ font-size:22px; margin:0 0 4px; }}
  .meta {{ color:var(--dim); font-size:12px; }}
  .cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr));
            gap:12px; margin:20px 0 26px; }}
  .card {{ border:1px solid var(--line); border-radius:10px; padding:12px 14px;
           background:#f7f9fc; }}
  .card b {{ display:block; font-size:22px; line-height:1.2; }}
  .card span {{ color:var(--dim); font-size:11px; text-transform:uppercase; letter-spacing:.06em; }}
  table {{ border-collapse:collapse; width:100%; font-size:12.5px; }}
  th,td {{ border-bottom:1px solid var(--line); padding:8px 10px; text-align:left;
           vertical-align:top; word-break:break-word; }}
  th {{ background:#eef3fa; text-transform:uppercase; font-size:10.5px; letter-spacing:.06em;
        color:var(--dim); position:sticky; top:0; }}
  tr:nth-child(even) td {{ background:#fafbfd; }}
  footer {{ margin-top:26px; color:var(--dim); font-size:11px; border-top:1px solid var(--line);
            padding-top:10px; }}
  @media print {{ body {{ padding:0; }} th {{ position:static; }} }}
</style></head><body>
<header><h1>{html.escape(title)}</h1>
<div class="meta">Generated {html.escape(str(stats["generated_at"]))} ·
scope: {html.escape(str(stats["profile_id"]))} · No_Loop local report</div></header>
<div class="cards">{cards}</div>
<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>
<footer>{len(rows)} row(s) · every value comes from your local ledger — nothing was
sent anywhere to build this document.</footer>
</body></html>"""


def _cell(value: Any) -> str:
    if value in (None, ""):
        return "—"
    text = str(value)
    if text.startswith(("http://", "https://")):
        return f'<a href="{html.escape(text, quote=True)}" rel="noopener">{html.escape(text)}</a>'
    return html.escape(text[:600])


def _card(label: str, value: Any) -> str:
    return (
        f'<div class="card"><b>{html.escape(str(value))}</b><span>{html.escape(label)}</span></div>'
    )
