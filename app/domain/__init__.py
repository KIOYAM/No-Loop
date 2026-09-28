"""No_Loop domain layer.

Pure business models and invariants. This package imports only the standard
library and pydantic — never httpx, sqlalchemy, selectolax, playwright, or any
vendor/portal module (R-ARCH-1/3; enforced by CI domain-purity gate).
"""

__all__ = [
    "errors",
    "facts",
    "profile",
    "jobs",
    "applications",
    "matching",
]
