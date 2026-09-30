"""The propose-only AI contract: parsing, the grounding gate, and the no-key path.

Two properties matter most here and are asserted directly:

1. A suggestion with no evidence, an unsupported number, or a path that does
   not exist is dropped — the panel must never show a fabrication.
2. With no API key the panel still fills, from deterministic local analysis,
   and the response says so instead of pretending a model answered.
"""

from __future__ import annotations

from typing import Any

from app.services.builder_ai import (
    SUGGEST_KINDS,
    build_prompt,
    local_suggestions,
    parse_suggestions,
    validate_suggestions,
)

DOC: dict[str, Any] = {
    "contact": {"name": "Ada", "email": "a@b.c", "phone": "", "location": "London"},
    "summary": "Backend engineer.",
    "skills": ["Python"],
    "experience": [
        {
            "role": "Engineer",
            "company": "Acme",
            "period": "2021 - Present",
            "bullets": ["Worked on payments"],
        }
    ],
}


def _item(**over: Any) -> dict[str, Any]:
    base = {
        "id": "s1",
        "path": "experience[0].bullets[0]",
        "kind": "rewrite",
        "current": "Worked on payments",
        "proposed": "Owned the payments migration to Kafka",
        "reason": "Turns a duty into an outcome.",
        "evidence": ["Worked on payments", "JD: payments migration"],
        "priority": 2,
    }
    base.update(over)
    return base


class TestParsing:
    def test_bare_array_fenced_array_and_object_all_read(self) -> None:
        item = _item()
        import json

        raw = json.dumps([item])
        for candidate in (
            raw,
            f"```json\n{raw}\n```",
            f"Here you go: {raw}",
            json.dumps({"suggestions": [item]}),
        ):
            items, error = parse_suggestions(candidate)
            assert error is None, candidate
            assert len(items) == 1

    def test_prose_is_reported_not_swallowed(self) -> None:
        items, error = parse_suggestions("I think your resume is fine.")
        assert items == []
        assert error and "JSON" in error

    def test_prompt_bounds_the_input_and_states_the_rules(self) -> None:
        prompt = build_prompt(DOC, jd_text="Kafka required", focus="bullets")
        assert "Kafka required" in prompt
        assert "Never invent" in prompt
        assert "binding path such as experience[0].bullets[1]" in prompt
        assert "focus on: bullets" in prompt
        # the doc is the only allowed source of claims
        assert "the only source of allowed claims" in prompt


class TestGroundingGate:
    def test_a_grounded_rewrite_passes(self) -> None:
        kept, dropped = validate_suggestions([_item()], DOC)
        assert dropped == 0
        assert kept[0]["path"] == "experience[0].bullets[0]"
        assert kept[0]["kind"] == "rewrite"

    def test_a_number_no_quote_supports_is_dropped(self) -> None:
        fabricated = _item(proposed="Improved throughput 340% for payments")
        kept, dropped = validate_suggestions([fabricated], DOC)
        assert kept == []
        assert dropped == 1

    def test_a_number_that_is_in_the_evidence_is_kept(self) -> None:
        grounded = _item(
            current="Handled 40k requests/s",
            proposed="Sustained 40k requests/s on the payments API",
            evidence=["Handled 40k requests/s on the payments API"],
        )
        kept, dropped = validate_suggestions([grounded], DOC)
        assert len(kept) == 1 and dropped == 0

    def test_missing_evidence_is_dropped(self) -> None:
        kept, dropped = validate_suggestions([_item(evidence=[])], DOC)
        assert kept == [] and dropped == 1

    def test_an_unknown_path_is_dropped(self) -> None:
        kept, dropped = validate_suggestions([_item(path="experience[9].role")], DOC)
        assert kept == [] and dropped == 1

    def test_unrelated_text_with_no_overlap_is_dropped(self) -> None:
        rambling = _item(
            proposed="Certified yoga instructor and sommelier with 15 awards",
            evidence=["Worked on payments"],
        )
        kept, dropped = validate_suggestions([rambling], DOC)
        assert kept == [] and dropped == 1

    def test_structural_kinds_need_no_text_evidence(self) -> None:
        items = [
            _item(kind="reorder", path="experience", proposed="", current="", evidence=[]),
            _item(
                kind="ats",
                path="",
                proposed="",
                current="",
                reason="Missing term: Kafka",
                evidence=[],
            ),
        ]
        kept, dropped = validate_suggestions(items, DOC)
        assert len(kept) == 2 and dropped == 0

    def test_unknown_kinds_and_duplicates_are_counted_as_dropped(self) -> None:
        items = [_item(kind="rewrite-my-back"), _item(), _item()]
        kept, dropped = validate_suggestions(items, DOC)
        assert len(kept) == 1
        assert dropped == 2

    def test_results_are_capped_and_the_rest_truncated_not_rejected(self) -> None:
        items = [
            _item(id=f"n{i}", path="summary", proposed=f"Payments summary variant {chr(97 + i)}")
            for i in range(20)
        ]
        items[0]["priority"] = 1
        kept, dropped = validate_suggestions(items, DOC)
        assert len(kept) == 12
        # truncation is not a rejection: dropped counts only gate failures
        assert dropped == 0
        assert kept[0]["priority"] == 1
        assert [s["priority"] for s in kept] == sorted(s["priority"] for s in kept)

    def test_every_kind_advertised_is_accepted_by_the_gate(self) -> None:
        for kind in SUGGEST_KINDS:
            item = _item(kind=kind, path="" if kind in ("ats", "confirm") else "summary")
            kept, dropped = validate_suggestions([item], DOC)
            assert dropped == 0 and len(kept) == 1, kind


class TestLocalSuggestions:
    def test_missing_jd_terms_become_an_honest_ats_note(self) -> None:
        out = local_suggestions(
            DOC,
            jd_text="Kafka",
            tailoring={"missing_terms": ["kafka", "terraform"], "suggestions": []},
        )
        ats = [s for s in out if s["kind"] == "ats"]
        assert ats and "kafka" in ats[0]["reason"]
        assert "do NOT claim" in ats[0]["reason"]

    def test_the_jd_terms_note_appears_once_and_without_punctuation(self) -> None:
        out = local_suggestions(
            DOC,
            jd_text="Terraform engineers mentor",
            tailoring={
                "missing_terms": ["terraform.", "engineers,", "mentor"],
                "suggestions": [
                    "JD mentions terms absent from your confirmed facts: "
                    "terraform., engineers, mentor — do NOT claim them"
                ],
            },
        )
        ats = [s for s in out if s["kind"] == "ats"]
        # one card, not the same fact twice in two phrasings
        assert len(ats) == 1, [s["reason"] for s in ats]
        assert "terraform, engineers, mentor" in ats[0]["reason"]
        assert all("." not in e and "," not in e for e in ats[0]["evidence"])

    def test_filler_bullet_is_pointed_at_not_ghost_written(self) -> None:
        out = local_suggestions(DOC)
        rewrites = [s for s in out if s["kind"] == "rewrite"]
        assert rewrites, out
        assert rewrites[0]["path"] == "experience[0].bullets[0]"
        assert rewrites[0]["current"] == "Worked on payments"
        # no wording is invented on the no-key tier: the human writes it
        assert rewrites[0]["proposed"] == ""
        assert '"Worked on"' in rewrites[0]["reason"]
        assert rewrites[0]["evidence"] == ["Worked on payments"]

    def test_empty_profile_sections_and_pending_facts_are_flagged(self) -> None:
        out = local_suggestions(
            {"contact": {"name": "Ada"}, "experience": [{"company": "Acme", "bullets": []}]},
            pending_facts=3,
        )
        reasons = " | ".join(s["reason"] for s in out)
        assert "skills section" in reasons
        assert "Acme has no bullet" in reasons
        assert "No summary line" in reasons
        assert "3 extracted field(s)" in reasons
        # priority 1 first so the panel leads with what matters
        assert out[0]["priority"] <= out[-1]["priority"]

    def test_local_suggestions_never_invent_a_number(self) -> None:
        out = local_suggestions(DOC, tailoring={"missing_terms": ["kafka"], "suggestions": []})
        for suggestion in out:
            if suggestion["kind"] in ("rewrite", "drop"):
                assert suggestion["evidence"], suggestion
