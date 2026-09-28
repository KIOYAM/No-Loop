"""JobIdentityResolver — 5-key deduplication (RESEARCH.md S8; LOOP-6).

Keys:
1. canonical URL (stripped tracking params, normalized host)
2. source native id (within the same adapter)
3. company+title fuzzy pair (rapidfuzz >= thresholds)
4. content fingerprint (domain sha256)
5. cross-source exact fingerprint match => merge with provenance list

Deterministic, tested on synthetic cross-source fixtures (LOOP-6).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from rapidfuzz import fuzz

from app.domain.jobs import Job

__all__ = ["JobCluster", "JobIdentityResolver"]

_TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "ref",
    "source",
}
_FUZZ_TITLE_THRESHOLD = 92.0
_FUZZ_COMPANY_THRESHOLD = 90.0


@dataclass
class JobCluster:
    """One real-world job; members are duplicates across/within sources."""

    canonical: Job
    members: list[Job] = field(default_factory=list)
    adapter_ids: list[str] = field(default_factory=list)

    @property
    def provenance(self) -> list[str]:
        """All adapter ids that reported this job (evidence preservation)."""
        return list(dict.fromkeys(self.adapter_ids))


def _canonical_url(url: str | None) -> str | None:
    if not url:
        return None
    parts = urlsplit(url.strip())
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAMS
    ]
    path = re.sub(r"/+$", "", parts.path)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


class JobIdentityResolver:
    """Accumulates jobs and clusters duplicates. Pure, synchronous, testable."""

    def __init__(self) -> None:
        self._by_url: dict[str, JobCluster] = {}
        self._by_native: dict[tuple[str, str], JobCluster] = {}
        self._by_fingerprint: dict[str, JobCluster] = {}
        self._clusters: list[JobCluster] = []

    # -- key registration -------------------------------------------------

    def _register(self, cluster: JobCluster, job: Job) -> None:
        url = _canonical_url(job.url)
        if url:
            self._by_url.setdefault(url, cluster)
        if job.source.native_id:
            self._by_native.setdefault((job.source.adapter_id, job.source.native_id), cluster)
        if job.fingerprint:
            self._by_fingerprint.setdefault(job.fingerprint, cluster)

    def _fuzzy_match(self, job: Job) -> JobCluster | None:
        for cluster in self._clusters:
            c = cluster.canonical
            if (
                fuzz.ratio(c.title.lower(), job.title.lower()) >= _FUZZ_TITLE_THRESHOLD
                and fuzz.ratio(c.company.lower(), job.company.lower()) >= _FUZZ_COMPANY_THRESHOLD
            ):
                return cluster
        return None

    # -- public API --------------------------------------------------------

    def add(self, job: Job) -> JobCluster:
        """Add a job; returns its cluster. Deterministic merge order = add order."""
        url = _canonical_url(job.url)
        native_key = (job.source.adapter_id, job.source.native_id) if job.source.native_id else None

        # Exact-key lookups in S8 priority order: URL, native id, fingerprint.
        cluster: JobCluster | None = None
        if url is not None:
            cluster = self._by_url.get(url)
        if cluster is None and native_key is not None:
            cluster = self._by_native.get(native_key)
        if cluster is None and job.fingerprint is not None:
            cluster = self._by_fingerprint.get(job.fingerprint)
        if cluster is not None:
            if job.id not in {m.id for m in cluster.members}:
                cluster.members.append(job)
                cluster.adapter_ids.append(job.source.adapter_id)
            return cluster

        fuzzy = self._fuzzy_match(job)
        if fuzzy is not None and job.source.adapter_id in set(fuzzy.adapter_ids):
            # Same-source near-duplicate (re-posted listing) merges on fuzz keys.
            fuzzy.members.append(job)
            return fuzzy

        cluster = JobCluster(canonical=job, members=[job], adapter_ids=[job.source.adapter_id])
        self._clusters.append(cluster)
        self._register(cluster, job)
        return cluster

    def clusters(self) -> list[JobCluster]:
        """All distinct clusters in insertion order."""
        return list(self._clusters)
