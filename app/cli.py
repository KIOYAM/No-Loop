"""No_Loop CLI — the runnable vertical slice (MASTER_SPEC §1 loop; W5).

Implements the core value pipeline end-to-end with zero network required by
default (``--live`` opts into public-API discovery) and zero API keys:

    import-resume → parse → facts (inferred) → confirm → discover → dedup
    → match (hard gate + score + explanation) → draft email (rule-based)
    → quick-add manual / record assisted → export

Run:
    python -m app.cli --help
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from app.adapters.ai_providers import RuleBasedProvider
from app.adapters.extractors import get_extractor
from app.adapters.facts_from_resume import parse_resume_text
from app.adapters.sources.jd_import import JDImportAdapter
from app.adapters.storage import JsonStore
from app.domain.applications import Application, ApplicationStatus, EntryMethod
from app.domain.facts import FactState, ResumeFact
from app.domain.jobs import Job, SourceRef
from app.domain.profile import ApplicationLimits, CandidateProfile
from app.services.dedup import JobIdentityResolver
from app.services.email_drafter import EmailDrafter
from app.services.match_engine import MatchEngine
from app.services.queue import ExportService, LedgerService

__all__ = ["main", "build_parser", "run_pipeline"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="noloop", description="No_Loop local-first job assistant")
    parser.add_argument(
        "--data-dir", default=str(Path(".local-data")), help="user data dir (default .local-data)"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_profile = sub.add_parser("create-profile", help="create a named candidate profile")
    p_profile.add_argument("name")
    p_profile.add_argument("--skills", required=True, help="comma-separated confirmed skills")
    p_profile.add_argument("--roles", required=True, help="comma-separated target roles")
    p_profile.add_argument("--locations", default="", help="comma-separated acceptable locations")
    p_profile.add_argument(
        "--work-mode", default="any", choices=["any", "remote", "hybrid", "onsite"]
    )
    p_profile.add_argument("--min-salary", type=int, default=None)
    p_profile.add_argument("--currency", default=None)
    p_profile.add_argument("--exclude-company", action="append", default=[])

    p_limits = sub.add_parser(
        "set-limits", help="MANDATORY limits setup (queue stays disabled until set)"
    )
    p_limits.add_argument("profile_id")
    p_limits.add_argument("--per-day", type=int, required=True)
    p_limits.add_argument("--per-week", type=int, required=True)
    p_limits.add_argument("--threshold", type=float, required=True)
    p_limits.add_argument("--cooldown-days", type=int, required=True)
    p_limits.add_argument("--active-hours", required=True, help="e.g. 9-20")

    p_import = sub.add_parser("import-resume", help="extract inferred facts from a resume file")
    p_import.add_argument("profile_id")
    p_import.add_argument("path")

    p_confirm = sub.add_parser(
        "confirm-facts", help="confirm all currently inferred facts (UI does this granularly)"
    )
    p_confirm.add_argument("profile_id")
    p_confirm.add_argument(
        "--reject-skill", action="append", default=[], help="skill name to reject"
    )

    p_jd = sub.add_parser("import-jd", help="import a pasted job description (assisted path)")
    p_jd.add_argument("profile_id")
    p_jd.add_argument("--title", required=True)
    p_jd.add_argument("--company", required=True)
    p_jd.add_argument("--jd-file", required=True, help="text file containing the job description")
    p_jd.add_argument("--url", default=None)

    p_match = sub.add_parser("match", help="score stored jobs against a profile")
    p_match.add_argument("profile_id")

    p_draft = sub.add_parser("draft-email", help="draft a job-specific email for a stored job")
    p_draft.add_argument("profile_id")
    p_draft.add_argument("job_index", type=int, help="index into match output ordering")

    p_apply = sub.add_parser("quick-add", help="record an application made manually elsewhere")
    p_apply.add_argument("profile_id")
    p_apply.add_argument("--company", required=True)
    p_apply.add_argument("--title", required=True)
    p_apply.add_argument("--url", default=None)
    p_apply.add_argument("--notes", default=None)

    p_export = sub.add_parser("export", help="export the application ledger")
    p_export.add_argument("profile_id")
    p_export.add_argument("--format", choices=["json", "csv"], default="json")

    sub.add_parser(
        "demo-discover", help="load bundled synthetic jobs (offline) to exercise matching"
    )
    return parser


# ---------------------------------------------------------------------------
# Helpers (shared by commands)
# ---------------------------------------------------------------------------


def _store(args: argparse.Namespace) -> JsonStore:
    return JsonStore(args.data_dir)


def _load_profile(store: JsonStore, profile_id: str) -> CandidateProfile:
    data = store.get("profiles", profile_id)
    if not data:
        raise SystemExit(f"profile not found: {profile_id}")
    return CandidateProfile.model_validate(data)


def _save_profile(store: JsonStore, profile: CandidateProfile) -> None:
    store.upsert("profiles", profile.id, profile.model_dump(mode="json"))


def _confirmed_facts(store: JsonStore, profile_id: str) -> list[ResumeFact]:
    facts = [
        f
        for f in (store.all("facts").values())
        if f.get("profile_id") == profile_id and f.get("state") == FactState.CONFIRMED.value
    ]
    from app.domain.facts import ResumeFact

    return [ResumeFact.model_validate(f) for f in facts]


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_create_profile(args: argparse.Namespace) -> None:
    store = _store(args)
    profile = CandidateProfile(
        name=args.name,
        targeting=None,
    )
    from app.domain.profile import TargetPreference, WorkMode

    mode = {
        "any": WorkMode.ANY,
        "remote": WorkMode.REMOTE,
        "hybrid": WorkMode.HYBRID,
        "onsite": WorkMode.ONSITE,
    }[args.work_mode]
    targeting = TargetPreference(
        role_titles=tuple(s.strip() for s in args.roles.split(",") if s.strip()),
        locations=tuple(s.strip() for s in args.locations.split(",") if s.strip()),
        work_modes=frozenset({mode}),
        min_salary=args.min_salary,
        currency=args.currency,
        excluded_companies=frozenset(args.exclude_company),
    )
    profile = profile.with_targeting(targeting)
    # Skills supplied at creation are USER-ENTERED => confirmed facts (by definition).
    from app.domain.facts import FactProvenance, ResumeFact, SkillClaim

    for skill in (s.strip() for s in args.skills.split(",") if s.strip()):
        fact = ResumeFact(
            profile_id=profile.id,
            field_class="skill",
            skill=SkillClaim(name=skill),
            confidence=1.0,
            provenance=FactProvenance(user_entry=True),
        )
        store.upsert("facts", fact.id, fact.model_dump(mode="json"))
    _save_profile(store, profile)
    print(f"profile created: {profile.id}  name={profile.name!r}")
    print(f"  confirmed skills: {args.skills}")
    print("  next: set-limits (mandatory before the queue admits anything)")


def cmd_set_limits(args: argparse.Namespace) -> None:
    store = _store(args)
    profile = _load_profile(store, args.profile_id)
    start, end = (int(x) for x in args.active_hours.split("-"))
    limits = ApplicationLimits(
        per_day=args.per_day,
        per_week=args.per_week,
        match_threshold=args.threshold,
        company_cooldown_days=args.cooldown_days,
        active_hours=(start, end),
    )
    profile = profile.with_limits(limits)
    _save_profile(store, profile)
    print(
        f"limits configured for {profile.id}: queue is ENABLED (threshold={limits.match_threshold})"
    )


def cmd_import_resume(args: argparse.Namespace) -> None:
    store = _store(args)
    profile = _load_profile(store, args.profile_id)
    path = Path(args.path)
    if not path.exists():
        raise SystemExit(f"file not found: {path}")

    extractor = get_extractor(path.name)
    if extractor is None:
        raise SystemExit(
            f"unsupported format: {path.suffix} (supported: txt, docx, pdf-with-limits)"
        )
    result = extractor.extract(path.read_bytes())  # type: ignore[attr-defined]
    if not result.ok:
        print(f"IMPORT FAILED — {result.error_reason}")
        print(f"  what you can do: {result.user_action}")
        sys.exit(2)
    outcome = parse_resume_text(profile.id, result.text, document_id=path.name)
    for fact in outcome.facts:
        store.upsert("facts", fact.id, fact.model_dump(mode="json"))
    print(f"extracted {len(outcome.facts)} inferred facts (nothing 'true' until confirmed):")
    for f in outcome.facts:
        label = f.skill.name if f.skill else str(f.value)
        conf = f.confidence
        print(f"  [{f.field_class}] {label}  (confidence {conf:.2f})")
    n_links = len(outcome.links)
    contact = f"email={outcome.contact_email} phone={bool(outcome.contact_phone)} links={n_links}"
    print(f"contact: {contact}")
    if outcome.ambiguities:
        print("onboarding questions (from real gaps):")
        for a in outcome.ambiguities:
            print(f"  ? {a}")


def cmd_confirm_facts(args: argparse.Namespace) -> None:
    store = _store(args)
    reject = {s.lower() for s in args.reject_skill}
    changed = 0
    for fid, data in store.all("facts").items():
        if (
            data.get("profile_id") != args.profile_id
            or data.get("state") != FactState.INFERRED.value
        ):
            continue
        fact = ResumeFact.model_validate(data)
        is_rejected_skill = fact.skill and fact.skill.name.lower() in reject
        updated = fact.reject() if is_rejected_skill else fact.confirm()
        store.upsert("facts", fid, updated.model_dump(mode="json"))
        changed += 1
    print(f"{changed} fact(s) processed (rejected: {len(args.reject_skill) or 0}).")


def cmd_import_jd(args: argparse.Namespace) -> None:
    store = _store(args)
    _profile = _load_profile(store, args.profile_id)  # profile scoping check
    jd_text = Path(args.jd_file).read_text(encoding="utf-8")
    adapter = JDImportAdapter()
    job = adapter.from_text(title=args.title, company=args.company, jd_text=jd_text, url=args.url)
    store.upsert("jobs", job.id, job.model_dump(mode="json"))
    print(f"job imported: [{job.id[:8]}] {job.title} @ {job.company} (mode={job.work_mode})")
    print(f"  requirements detected: {len(job.description_text.splitlines())} lines of JD text")


def cmd_demo_discover(args: argparse.Namespace) -> None:
    """Bundled synthetic jobs so matching can be exercised fully offline."""
    store = _store(args)
    demo_jobs: list[tuple[str, str, str, str, str, int, int, str]] = [
        (
            "Senior Python Developer",
            "Innovatech",
            "Chennai",
            "hybrid",
            "Required: strong Python, FastAPI, PostgreSQL, Docker. REST API a must.",
            900000,
            1400000,
            "INR",
        ),
        (
            "ML Engineer",
            "DataForge",
            "Remote",
            "remote",
            "Machine learning: Python, PyTorch, NLP, pandas. Kubernetes a plus. GenAI welcome.",
            1200000,
            1800000,
            "INR",
        ),
        (
            "Java Backend Developer",
            "Legacy Systems Ltd",
            "Bengaluru",
            "onsite",
            "Java, Spring, SQL. 5+ years experience required. Relocation support.",
            800000,
            1200000,
            "INR",
        ),
        (
            "Frontend React Developer",
            "WebWorks",
            "Remote",
            "remote",
            "React, TypeScript, CSS. Build dashboards and design systems.",
            700000,
            1100000,
            "INR",
        ),
    ]
    resolver = JobIdentityResolver()
    for title, company, location, mode, jd, smin, smax, cur in demo_jobs:
        job = Job(
            title=title,
            company=company,
            location=location,
            work_mode=mode,
            description_text=jd,
            salary_min=smin,
            salary_max=smax,
            salary_currency=cur,
            posted_at=datetime.now(),
            source=SourceRef(
                kind="public_api",
                adapter_id="demo",
                native_id=f"{company}-{title}".replace(" ", "-").lower(),
                url=None,
            ),
        )
        cluster = resolver.add(job)
        store.upsert("jobs", cluster.canonical.id, cluster.canonical.model_dump(mode="json"))
    print(
        f"{len(demo_jobs)} synthetic jobs stored (deduped to {len(resolver.clusters())} clusters)"
    )


def cmd_match(args: argparse.Namespace) -> None:
    store = _store(args)
    profile = _load_profile(store, args.profile_id)
    if profile.targeting is None:
        raise SystemExit("profile has no targeting; use create-profile --roles ... first")
    facts = _confirmed_facts(store, profile.id)
    skills = [f.skill.name for f in facts if f.skill]
    engine = MatchEngine(profile_id=profile.id, profile_skills=skills, targeting=profile.targeting)
    jobs = [Job.model_validate(j) for j in store.all("jobs").values()]
    resolver = JobIdentityResolver()
    for job in jobs:
        resolver.add(job)
    clusters = resolver.clusters()
    threshold = profile.limits.match_threshold if profile.limits else "UNSET"
    print(f"scoring {len(clusters)} unique job(s) against {profile.name!r} (threshold={threshold})")
    for i, cluster in enumerate(clusters):
        result = engine.score(cluster.canonical)
        job_label = f"{cluster.canonical.title} @ {cluster.canonical.company}"
        print(f"[{i}] {job_label}  score={result.score:.2f} gate={result.hard_gate.value}")
        if result.hard_gate.value == "fail":
            for reason in result.gate_reasons:
                print(f"      excluded: {reason}")
        else:
            print("      " + result.explain().replace("\n", "\n      "))


def cmd_draft_email(args: argparse.Namespace) -> None:
    store = _store(args)
    profile = _load_profile(store, args.profile_id)
    facts = _confirmed_facts(store, profile.id)
    jobs = [Job.model_validate(j) for j in store.all("jobs").values()]
    jobs.sort(key=lambda j: j.created_at)
    if args.job_index >= len(jobs):
        raise SystemExit(f"job index {args.job_index} out of range ({len(jobs)} jobs stored)")
    job = jobs[args.job_index]
    drafter = EmailDrafter(RuleBasedProvider())
    draft = drafter.draft(profile_name=profile.contact_name or profile.name, facts=facts, job=job)
    print("=== EMAIL DRAFT (rule-based, evidence-mapped) ===")
    print(draft.body)
    print("=== EVIDENCE ===")
    print(f"  skills used: {', '.join(draft.evidence['skills_used']) or '(none confirmed yet)'}")
    print(f"  fact ids   : {len(draft.evidence['fact_ids'])} confirmed facts referenced")
    print(f"  specificity: {draft.job_specificity}")


def cmd_quick_add(args: argparse.Namespace) -> None:
    store = _store(args)
    ledger = LedgerService()
    application = Application(
        profile_id=args.profile_id,
        entry_method=EntryMethod.MANUAL,
        company=args.company,
        title=args.title,
        application_url=args.url,
        notes=args.notes,
        submission_evidence={"method": "user_assertion", "note": "recorded via quick-add"},
        status=ApplicationStatus.REVIEW_REQUIRED,
    )
    ledger.create(application)
    # The user-assertion evidence set at creation satisfies R-TRUTH-5 for manual
    # records; pass it through the transition explicitly.
    ledger.transition(
        application.id,
        ApplicationStatus.SUBMITTED,
        submission_evidence=application.submission_evidence,
    )
    stored = ledger.get(application.id)
    assert stored is not None
    store.upsert("applications", application.id, stored.model_dump(mode="json"))
    print(f"application recorded [{application.id[:8]}]: {args.title} @ {args.company}")
    print("  status -> SUBMITTED (user-asserted evidence)")


def cmd_export(args: argparse.Namespace) -> None:
    # Rebuild the ledger view from storage, then export.
    store = _store(args)
    ledger = LedgerService()
    from app.domain.applications import Application

    for data in store.all("applications").values():
        ledger.create(Application.model_validate(data))
    exporter = ExportService(ledger)
    payload = (
        exporter.to_json(profile_id=args.profile_id)
        if args.format == "json"
        else exporter.to_csv(profile_id=args.profile_id)
    )
    print(payload)


def run_pipeline(args: argparse.Namespace) -> None:
    commands = {
        "create-profile": cmd_create_profile,
        "set-limits": cmd_set_limits,
        "import-resume": cmd_import_resume,
        "confirm-facts": cmd_confirm_facts,
        "import-jd": cmd_import_jd,
        "demo-discover": cmd_demo_discover,
        "match": cmd_match,
        "draft-email": cmd_draft_email,
        "quick-add": cmd_quick_add,
        "export": cmd_export,
    }
    commands[args.cmd](args)


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    run_pipeline(args)


if __name__ == "__main__":
    main()
