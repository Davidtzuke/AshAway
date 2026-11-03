"""Evidence items, their labels, and whether they are good enough to trust (FR5, FR8, NFR4)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class EvidenceKind(str, Enum):
    FORECAST = "forecast"
    OBSERVATION = "observation"
    OFFICIAL_ALERT = "official alert"


@dataclass(frozen=True)
class EvidenceItem:
    kind: EvidenceKind
    source: str
    observed_on: date
    summary: str
    link: str | None = None


@dataclass(frozen=True)
class SourceStatus:
    """What happened when a source was asked. An unavailable source has no values at all (NFR5)."""

    name: str
    critical: bool
    available: bool
    retrieved_at: str
    latest_observation: date | None = None
    error: str | None = None


@dataclass(frozen=True)
class EvidenceCheck:
    missing_critical: list[str] = field(default_factory=list)
    stale_critical: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def sufficient(self) -> bool:
        return not (self.missing_critical or self.stale_critical or self.conflicts)


# Oldest evidence, in days before the assessment date, that still counts as current.
MAX_AGE_DAYS = 2


def is_stale(latest: date | None, as_of: date, max_age_days: int = MAX_AGE_DAYS) -> bool:
    """True when the newest value is older than the limit, or there is none."""
    return latest is None or (as_of - latest).days > max_age_days


def check_evidence(sources: list[SourceStatus], as_of: date, forecast_level: str | None, fire_count: int) -> EvidenceCheck:
    """Find missing, stale and conflicting inputs. `fire_count` is detections near the place."""
    missing, stale, warnings = [], [], []
    for s in sources:
        if not s.available:
            (missing if s.critical else warnings).append(s.name)
        elif s.critical and is_stale(s.latest_observation, as_of):
            stale.append(s.name)
    conflicts = []
    if forecast_level == "low" and fire_count > 0:
        conflicts.append(f"The forecast is low, but satellites detected {fire_count} fire(s) nearby.")
    notes = [f"{name} is unavailable, so this assessment does not use it." for name in warnings]
    return EvidenceCheck(missing, stale, conflicts, notes)
