"""Skill taxonomy: canonicalisation, word boundaries, ambiguity gating.

The taxonomy is the layer that lets a job description and a resume be compared
by the same vocabulary, so these tests pin down the three rules that keep it
honest: aliases collapse to one canonical name, matches never fire inside a
longer word, and prose words like "go" only count where a human meant a list.
"""

from __future__ import annotations

from app.adapters import skill_taxonomy
from app.domain.facts import SkillClaim


def test_alias_forms_canonicalise_to_one_name() -> None:
    assert skill_taxonomy.canonical("python3") == "python"
    assert skill_taxonomy.canonical("K8s") == "kubernetes"
    assert skill_taxonomy.canonical("  Node.JS ") == "node.js"
    assert skill_taxonomy.category("k8s") == "devops"


def test_unknown_names_are_cleaned_never_fabricated() -> None:
    # an out-of-catalog skill keeps its own text — no invented canonical, no URI
    assert skill_taxonomy.canonical("  Quantum Widget Wrangling ") == ("Quantum Widget Wrangling")
    assert skill_taxonomy.category("Quantum Widget Wrangling") is None
    assert skill_taxonomy.esco_uri("python") is None


def test_matches_respect_word_boundaries() -> None:
    assert skill_taxonomy.extract_skills("pythonic") == []
    assert skill_taxonomy.extract_skills("cplusplus") == []
    assert [hit.canonical for hit in skill_taxonomy.extract_skills("python")] == ["python"]


def test_cpp_and_csharp_stay_distinct() -> None:
    hits = skill_taxonomy.extract_skills("maintained the C++ core and a C# client")
    assert sorted(hit.canonical for hit in hits) == ["c#", "c++"]
    # the user's casing is preserved on the claim, the canonical is separate
    assert {hit.matched for hit in hits} == {"c++", "c#"}


def test_ambiguous_words_need_the_section_gate() -> None:
    prose = "I will go and spark the conversation"
    assert skill_taxonomy.extract_skills(prose) == []
    gated = skill_taxonomy.extract_skills(prose, allow_ambiguous=True)
    assert sorted(hit.canonical for hit in gated) == ["go", "spark"]


def test_offset_shifts_spans_into_the_enclosing_document() -> None:
    prefix = "TECHNICAL SKILLS\n"
    (hit,) = skill_taxonomy.extract_skills("Kubernetes", offset=len(prefix))
    assert hit.span == (len(prefix), len(prefix) + len("Kubernetes"))


def test_normalize_claim_fills_the_canonical_name() -> None:
    claim = SkillClaim(name="k8s", normalized_name="")
    normalised = skill_taxonomy.normalize_claim(claim)
    assert normalised.normalized_name == "kubernetes"
    assert normalised.name == "k8s"  # surface casing is the user's


def test_catalog_is_free_of_duplicate_surfaces() -> None:
    seen: dict[str, str] = {}
    for definition in skill_taxonomy.definitions():
        for surface in definition.surfaces:
            key = surface.lower()
            assert key not in seen, (
                f"{surface!r} maps to both {seen[key]!r} and {definition.canonical!r}"
            )
            seen[key] = definition.canonical


def test_known_surface_names_matches_the_catalog() -> None:
    assert set(skill_taxonomy.known_surface_names()) == {
        surface.lower()
        for definition in skill_taxonomy.definitions()
        for surface in definition.surfaces
    }
