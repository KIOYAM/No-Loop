"""Skill taxonomy — open-vocabulary detection + canonical normalisation (LOOP-5/6).

Replaces the old closed 53-skill tuple with a *data* driven vocabulary:

- **Discovery is open**: any alias in the catalog can match, and matches are
  boundary-safe (``C++``, ``C#`` and ``node.js`` match; ``java`` never matches
  inside ``javascript``).
- **Storage is canonical**: every hit carries a canonical surface form which is
  written to ``SkillClaim.normalized_name`` — the field the schema always had
  and nothing ever set (IMPROVEMENT_AUDIT "skill-taxonomy normalizer").
- **No fabrication**: the catalog only *labels* strings that are literally
  present in the source text; it never invents skills. Skills outside the
  catalog are still reported (``canonical`` falls back to the cleaned surface
  form) so nothing a candidate actually wrote is silently dropped.

ESCO/O*NET ids: ``SkillDefinition.esco_uri`` exists and is intentionally ``None``
for now — the ESCO bulk CSV (CC-BY 4.0, attribution in docs/ATTRIBUTIONS.md)
fills it in a later step. Guessing a URI would be fabrication.

Reference: ESCoE Skills Extractor Library (extract → map to a standard
taxonomy), ESCO v1.2 preferred/non-preferred/hidden terms as the alias source.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

__all__ = [
    "SkillDefinition",
    "SkillHit",
    "canonical",
    "category",
    "definitions",
    "esco_uri",
    "extract_skills",
    "normalize_claim",
    "known_surface_names",
]

# ---------------------------------------------------------------------------
# catalog: (canonical, category, ambiguous?, esco_uri?, *aliases)
# `ambiguous` marks surface forms that are also common prose words ("go") and
# are therefore only matched inside a skills/technologies section.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SkillDefinition:
    """One canonical technology/skill and every surface form that means it."""

    canonical: str
    category: str
    aliases: tuple[str, ...]
    ambiguous: bool = False
    esco_uri: str | None = None

    @property
    def surfaces(self) -> tuple[str, ...]:
        return (self.canonical, *self.aliases)


def _d(canonical: str, category: str, *aliases: str, ambiguous: bool = False) -> SkillDefinition:
    return SkillDefinition(
        canonical=canonical, category=category, aliases=tuple(aliases), ambiguous=ambiguous
    )


_CATALOG: tuple[SkillDefinition, ...] = (
    # -- languages ---------------------------------------------------------
    _d("python", "language", "py", "python3"),
    _d("java", "language"),
    _d("javascript", "language", "js", "ecmascript"),
    _d("typescript", "language", "ts"),
    _d("sql", "language", "pl/sql"),
    _d("c++", "language", "cpp", "c plus plus"),
    _d("c#", "language", "csharp", "c sharp"),
    _d("go", "language", "golang", ambiguous=True),
    _d("rust", "language", ambiguous=True),
    _d("php", "language"),
    _d("ruby", "language", "rb"),
    _d("kotlin", "language"),
    _d("swift", "language", ambiguous=True),
    _d("scala", "language"),
    _d("elixir", "language"),
    _d("haskell", "language"),
    _d("perl", "language"),
    _d("bash", "language", "shell scripting", "unix shell"),
    _d("powershell", "language"),
    _d("dart", "language"),
    _d("julia", "language", ambiguous=True),
    _d("matlab", "language"),
    # -- web / frontend ----------------------------------------------------
    _d("react", "frontend", "reactjs", "react.js"),
    _d("angular", "frontend", "angularjs", "angular.js"),
    _d("vue", "frontend", "vuejs", "vue.js"),
    _d("next.js", "frontend", "nextjs"),
    _d("svelte", "frontend"),
    _d("html", "frontend", "html5"),
    _d("css", "frontend", "css3"),
    _d("sass", "frontend", "scss", "less"),
    _d("tailwind css", "frontend", "tailwind", "tailwindcss"),
    _d("jquery", "frontend"),
    _d("redux", "frontend"),
    # -- backend / frameworks ---------------------------------------------
    _d("fastapi", "backend", "fast api"),
    _d("django", "backend", "django rest framework", "drf"),
    _d("flask", "backend"),
    _d("spring boot", "backend", "spring", "java spring"),
    _d("node.js", "backend", "nodejs"),
    _d("express.js", "backend", "expressjs", "express"),
    _d(".net", "backend", "dotnet", ".net core", "asp.net", "c#.net"),
    _d("ruby on rails", "backend", "ror"),
    _d("laravel", "backend"),
    _d(
        "rest api",
        "backend",
        "rest apis",
        "restful",
        "restful api",
        "rest",
        "api",
        "apis",
        ambiguous=True,
    ),
    _d("graphql", "backend", "apollo graphql"),
    _d("grpc", "backend"),
    _d("microservices", "backend", "microservice"),
    _d("soap", "backend", ambiguous=True),
    # -- data stores / messaging ------------------------------------------
    _d("postgresql", "database", "postgres", "psql"),
    _d("mysql", "database", "mariadb"),
    _d("mongodb", "database", "mongo", "mongo db"),
    _d("redis", "database", "redis cache"),
    _d("cassandra", "database"),
    _d("elasticsearch", "database", "elastic search", "opensearch"),
    _d("dynamodb", "database", "dynamo db"),
    _d("sqlite", "database"),
    _d("oracle database", "database", "oracle db", "oracle sql", "oracle cloud", "oci"),
    _d("mssql", "database", "ms sql", "sql server", "microsoft sql server"),
    _d("snowflake", "database", ambiguous=True),
    _d("redshift", "database", "aws redshift"),
    _d("bigquery", "database", "google bigquery"),
    _d("neo4j", "database"),
    _d("kafka", "data", "apache kafka"),
    _d("rabbitmq", "data"),
    _d("celery", "data", "django celery", "celery worker"),
    _d("airflow", "data", "apache airflow", "apache-airflow"),
    _d("dbt", "data"),
    _d("spark", "data", "pyspark", "apache spark", ambiguous=True),
    _d("hadoop", "data", "apache hadoop"),
    _d("flink", "data", "apache flink"),
    _d("etl", "data"),
    # -- cloud / devops ----------------------------------------------------
    _d("aws", "cloud", "amazon web services"),
    _d("azure", "cloud", "microsoft azure"),
    _d("gcp", "cloud", "google cloud", "google cloud platform"),
    _d("docker", "devops", "docker-compose"),
    _d("kubernetes", "devops", "k8s"),
    _d("terraform", "devops", "terraform cloud"),
    _d("ansible", "devops"),
    _d("jenkins", "devops", "jenkins ci"),
    _d("github actions", "devops", "gha"),
    _d("gitlab ci", "devops", "gitlab ci/cd", "gitlab pipelines"),
    _d("circleci", "devops", "circle ci"),
    _d("argocd", "devops", "argo cd"),
    _d("helm", "devops", "helm charts"),
    _d("prometheus", "devops", ambiguous=True),
    _d("grafana", "devops"),
    _d("ci/cd", "devops", "cicd", "ci-cd", "continuous integration", "continuous delivery"),
    _d("site reliability engineering", "devops", "sre"),
    _d("virtualization", "devops", "vmware", "hyperv"),
    # -- ml / ai -----------------------------------------------------------
    _d("machine learning", "ai", "ml", "machine-learning"),
    _d("deep learning", "ai", "dl"),
    _d("natural language processing", "ai", "nlp"),
    _d("computer vision", "ai"),
    _d("generative ai", "ai", "genai", "generative ai (genai)"),
    _d("llm", "ai", "large language models", "large language model"),
    _d("pytorch", "ai", "torch"),
    _d("tensorflow", "ai", "tf"),
    _d("keras", "ai"),
    _d("scikit-learn", "ai", "sklearn", "scikit learn", "sk-learn"),
    _d("xgboost", "ai"),
    _d("lightgbm", "ai"),
    _d("hugging face", "ai", "huggingface", "hf transformers"),
    _d("langchain", "ai", "lang chain"),
    _d("llamaindex", "ai", "llama index"),
    _d("mlops", "ai"),
    _d("prompt engineering", "ai"),
    _d("retrieval augmented generation", "ai", "rag"),
    _d("transformers", "ai", "transformer models"),
    _d("recommendation systems", "ai", "recommender systems"),
    # -- analytics / bi ----------------------------------------------------
    _d("pandas", "analytics", "python pandas"),
    _d("numpy", "analytics", "num py"),
    _d("matplotlib", "analytics"),
    _d("seaborn", "analytics"),
    _d("plotly", "analytics"),
    _d("power bi", "analytics", "powerbi"),
    _d("tableau", "analytics"),
    _d("microsoft excel", "analytics", "excel", "advanced excel", "ms excel"),
    _d("looker", "analytics", ambiguous=True),
    _d("google analytics", "analytics", "ga4"),
    _d("statistics", "analytics", "statistical analysis"),
    # -- practices / tools -------------------------------------------------
    _d("git", "tool", "version control", "vcs"),
    _d("linux", "tool", "unix", "ubuntu", "centos"),
    _d("agile", "practice", "agile methodology"),
    _d("scrum", "practice"),
    _d("jira", "tool"),
    _d("confluence", "tool"),
    _d("tdd", "practice", "test driven development", "unit testing", "pytest"),
    _d("selenium", "tool", "selenium webdriver"),
    _d("playwright", "tool"),
    _d("cypress", "tool"),
    _d("jest", "tool", "jest js"),
    _d("vitest", "tool"),
    _d("mocha", "tool"),
    _d("postman", "tool"),
    _d("oauth", "security", "oauth2"),
    _d("jwt", "security", "json web tokens"),
    _d("cybersecurity", "security", "information security", "appsec", "owasp"),
    _d("datadog", "observability"),
    _d("splunk", "observability"),
    _d("grafana loki", "observability"),
    # -- design / misc -----------------------------------------------------
    _d("figma", "design"),
    _d("adobe photoshop", "design", "photoshop"),
    _d("adobe illustrator", "design", "illustrator"),
    _d("salesforce", "saas"),
    _d("sap", "saas"),
    _d("servicenow", "saas", "service now"),
    _d("autocad", "cad", "auto cad"),
    _d("unity", "gamedev", ambiguous=True),
    _d("unreal engine", "gamedev", "unreal"),
)

#: Definition lookup by canonical name.
_BY_CANONICAL: dict[str, SkillDefinition] = {d.canonical: d for d in _CATALOG}

#: alias (lower, stripped) → canonical surface form.
_ALIAS_INDEX: dict[str, str] = {}
for _defn in _CATALOG:
    for _surface in _defn.surfaces:
        _ALIAS_INDEX.setdefault(_surface.strip().lower(), _defn.canonical)

#: Ambiguous surface forms ("go", "spark") → canonical, matched only in-section.
_AMBIGUOUS_SURFACES: frozenset[str] = frozenset(
    surface.strip().lower() for _defn in _CATALOG if _defn.ambiguous for surface in _defn.surfaces
)

#: Every alias, longest first, so alternation prefers the greedy surface.
_ALIASES_BY_LENGTH: tuple[str, ...] = tuple(sorted(_ALIAS_INDEX, key=len, reverse=True))

_PATTERN = re.compile(
    r"(?<!\w)(?:" + "|".join(re.escape(a) for a in _ALIASES_BY_LENGTH) + r")(?!\w)",
    re.IGNORECASE,
)

_CLEAN_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class SkillHit:
    """One literal occurrence of a skill in source text."""

    canonical: str
    matched: str  # the alias as it appears in the catalog (lower-cased key)
    span: tuple[int, int]  # (start, end) offsets in the searched text
    category: str = ""
    ambiguous: bool = False
    in_vocabulary: bool = True

    def claim_kwargs(self) -> dict[str, object]:
        return {"name": self.canonical, "normalized_name": self.canonical}


def definitions() -> tuple[SkillDefinition, ...]:
    """The full catalog (data, not logic — safe to expose)."""
    return _CATALOG


def known_surface_names() -> tuple[str, ...]:
    """Backwards-compatible alias for the old ``KNOWN_SKILLS`` tuple."""
    return tuple(_ALIAS_INDEX)


def _clean(value: str) -> str:
    return _CLEAN_RE.sub(" ", value.strip()).strip(" ,;:|/-")


def canonical(name: str) -> str:
    """Map any surface form to its canonical name (or the cleaned input)."""
    cleaned = _clean(name)
    if not cleaned:
        return ""
    return _ALIAS_INDEX.get(cleaned.lower(), cleaned)


def category(name: str) -> str | None:
    """Category of a known skill, ``None`` for out-of-catalog skills."""
    defn = _BY_CANONICAL.get(_ALIAS_INDEX.get(_clean(name).lower(), ""))
    return defn.category if defn else None


def esco_uri(name: str) -> str | None:
    """ESCO concept URI when the catalog has one (currently: never — no guessing)."""
    defn = _BY_CANONICAL.get(_ALIAS_INDEX.get(_clean(name).lower(), ""))
    return defn.esco_uri if defn else None


def extract_skills(text: str, *, offset: int = 0, allow_ambiguous: bool = False) -> list[SkillHit]:
    """Find every skill surface form literally present in ``text``.

    ``offset`` shifts the reported spans into the enclosing document (section
    bodies are slices of the original text). Ambiguous prose words ("go",
    "spark") are only returned when ``allow_ambiguous`` is set — i.e. when the
    caller is scanning a dedicated skills/technologies section.
    """
    hits: list[SkillHit] = []
    seen: set[tuple[str, int]] = set()
    for match in _PATTERN.finditer(text):
        surface = match.group(0)
        key = surface.strip().lower()
        canonical_name = _ALIAS_INDEX.get(key)
        if canonical_name is None:
            continue  # pattern only matches catalog aliases
        if key in _AMBIGUOUS_SURFACES and not allow_ambiguous:
            continue
        span = (match.start() + offset, match.end() + offset)
        if (canonical_name, span[0]) in seen:
            continue
        seen.add((canonical_name, span[0]))
        defn = _BY_CANONICAL[canonical_name]
        hits.append(
            SkillHit(
                canonical=canonical_name,
                matched=key,
                span=span,
                category=defn.category,
                ambiguous=defn.ambiguous,
                in_vocabulary=True,
            )
        )
    return hits


def normalize_claim(claim: object, canonical_name: str | None = None) -> object:
    """Set ``SkillClaim.normalized_name`` (returns the same frozen instance)."""
    name = canonical_name or canonical(getattr(claim, "name", ""))
    if not name:
        return claim
    if getattr(claim, "normalized_name", None) == name:
        return claim
    try:
        return claim.model_copy(update={"normalized_name": name})  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 - never let normalisation break an import
        return claim


_ = field  # dataclasses import kept explicit for future record types
