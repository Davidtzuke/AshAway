"""Answer a traveller's question: risk per day, why, how recent, and what else to consider."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Callable

import pandas as pd

from . import feeds
from .evidence import EvidenceItem, EvidenceKind, SourceStatus, check_evidence
from .geo import aggregate_cells_to_municipality
from .model.bundle import ModelBundle
from .model.data import ISSUE_TIME_IDX, STATIC_FEATURES, window_features
from .request import validate_request
from .risk import DISCLAIMER, HIGH, LEVEL_ORDER, LEVEL_TEXT, LOW, MEDIUM, explain, highest_level, risk_level

MAX_ALTERNATIVES = 3
HISTORY_DAYS = ISSUE_TIME_IDX + 1  # same 29-day window the model was trained on
ASSESSED, INSUFFICIENT = "assessed", "insufficient evidence"
RESOURCES = Path(__file__).parent / "resources"


@lru_cache(maxsize=1)
def load_destinations() -> pd.DataFrame:
    return pd.read_csv(RESOURCES / "pilot_destinations.csv").set_index("id", drop=False)


def daily_feature_rows(weather: pd.DataFrame, static: pd.Series, days: list[date]) -> pd.DataFrame:
    """One feature row per day we can score, built only from days before it.

    A day whose 29-day history has a gap gets no row: it is not scored at all (NFR5).
    """
    frame = weather.dropna().set_index("date")
    rows = []
    for day in days:
        issue = day - timedelta(days=1)
        wanted = [issue - timedelta(days=i) for i in range(HISTORY_DAYS - 1, -1, -1)]
        if not all(d in frame.index for d in wanted):
            continue
        hist = frame.loc[wanted]
        win = window_features(*(hist[c].to_numpy().reshape(1, -1) for c in ("tp", "t2m_max", "rh_min")))
        last = hist.iloc[-1]
        rows.append({
            "date": day,
            "cell_id": static["cell_id"],
            "t2m_max": last["t2m_max"],
            "rh_min": last["rh_min"],
            "wind_speed": last["wind_speed"],
            "tp": last["tp"],
            **{k: float(v[0]) for k, v in win.items()},
            **{c: float(static[c]) for c in STATIC_FEATURES},
        })
    return pd.DataFrame(rows)


def lower_risk_alternatives(current_level: str, candidates: list[dict], limit: int = MAX_ALTERNATIVES) -> list[dict]:
    """Keep candidates at a strictly lower level with the same coverage, lowest score first (FR6, AI6)."""
    lower = [c for c in candidates if c["comparable"] and LEVEL_ORDER[c["level"]] < LEVEL_ORDER[current_level]]
    return sorted(lower, key=lambda c: (c["peak_probability"], c["id"]))[:limit]


@dataclass(frozen=True)
class DayRisk:
    date: date
    probability: float
    level: str


@dataclass
class Assessment:
    destination_id: str
    destination: str
    start: date
    end: date
    as_of: date
    generated_at: str
    model_version: str
    status: str
    level: str | None  # None when the evidence does not support stating one (FR5)
    forecast_level: str | None
    peak_probability: float | None
    level_text: str
    days: list[DayRisk] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    evidence: list[EvidenceItem] = field(default_factory=list)
    sources: list[SourceStatus] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    alternatives: list[dict] = field(default_factory=list)
    disclaimer: str = DISCLAIMER

    def to_dict(self) -> dict:
        return asdict(self)


class Assessor:
    def __init__(
        self,
        bundle: ModelBundle,
        destinations: pd.DataFrame | None = None,
        fetch: feeds.Fetch = feeds.http_get,
        clock: Callable[[], datetime] = feeds.now_utc,
        firms_key: str | None = None,
        log_path: str | Path | None = None,
    ):
        self.bundle = bundle
        self.destinations = load_destinations() if destinations is None else destinations
        self.fetch = fetch
        self.clock = clock
        self.firms_key = firms_key
        self.log_path = log_path

    def _supported(self) -> dict[str, str]:
        return dict(zip(self.destinations["id"], self.destinations["name"]))

    def _forecast(self, dest: pd.Series, days: list[date], as_of: date) -> dict:
        """Everything that does not depend on which destination was asked about first."""
        now = self.clock()
        stamp, today = now.isoformat(timespec="seconds"), now.date()
        first = days[0] - timedelta(days=HISTORY_DAYS)
        weather = feeds.get_weather(dest["lat"], dest["lon"], first, days[-1] - timedelta(days=1), as_of, today, self.fetch, stamp)
        fires = feeds.get_fires(dest["lat"], dest["lon"], as_of, today, self.fetch, stamp, self.firms_key)
        sources = [weather.status, fires.status]

        scored = pd.DataFrame()
        if weather.data is not None:
            rows = daily_feature_rows(weather.data, dest, days)
            if not rows.empty:
                rows["prob"] = self.bundle.predict(rows)
                scored = rows
        day_risks = []
        if not scored.empty:
            daily = aggregate_cells_to_municipality(scored, {dest["cell_id"]: dest["id"]})
            day_risks = [
                DayRisk(d, float(p), risk_level(float(p), self.bundle.medium_from, self.bundle.high_from))
                for d, p in zip(daily["date"], daily["prob_max"])
            ]
        level = highest_level([d.level for d in day_risks]) if day_risks else None
        return {
            "sources": sources,
            "rows": scored,
            "days": day_risks,
            "level": level,
            "peak": max((d.probability for d in day_risks), default=None),
            "fires": fires,
            "complete": len(day_risks) == len(days),
        }

    def _alternatives(self, asked_id: str, base: dict, days: list[date], as_of: date) -> list[dict]:
        wanted = {s.name for s in base["sources"] if s.available}
        candidates = []
        for dest_id, dest in self.destinations.iterrows():
            if dest_id == asked_id:
                continue
            other = self._forecast(dest, days, as_of)
            if other["level"] is None:
                continue
            candidates.append({
                "id": dest_id,
                "name": dest["name"],
                "level": other["level"],
                "peak_probability": other["peak"],
                # Only compare like with like: the same sources and every day scored.
                "comparable": other["complete"] and {s.name for s in other["sources"] if s.available} == wanted,
            })
        return [
            {**{k: c[k] for k in ("id", "name", "level", "peak_probability")},
             "note": "Lower estimated risk for the same dates. This is not proof of safety."}
            for c in lower_risk_alternatives(base["level"], candidates)
        ]

    def assess(self, place: str, start: str | date, end: str | date, as_of: date | None = None, with_alternatives: bool = True) -> Assessment:
        now = self.clock()
        request = validate_request(place, start, end, self._supported(), now.date())
        # A past trip is replayed as if asked the day before it, so no later evidence can leak in.
        as_of = as_of or min(now.date(), request.start - timedelta(days=1))
        dest = self.destinations.loc[request.destination_id]

        base = self._forecast(dest, request.days, as_of)
        stamp = now.isoformat(timespec="seconds")
        air, disruption = feeds.get_air(dest["lat"], dest["lon"], as_of, self.fetch, stamp), feeds.get_disruption(stamp)
        sources = base["sources"] + [air.status, disruption.status]
        if self.log_path:
            feeds.log_update(self.log_path, sources, request.destination_id)

        fires = base["fires"]
        check = check_evidence(sources, as_of, base["level"], fires.detections)
        warnings = list(check.warnings)
        for name in check.missing_critical:
            warnings.append(f"{name} is unavailable, and this assessment needs it.")
        for name in check.stale_critical:
            warnings.append(f"{name} is too old to rely on.")
        warnings.extend(check.conflicts)
        if base["days"] and not base["complete"]:
            warnings.append(f"Only {len(base['days'])} of {len(request.days)} days could be scored, because weather data has gaps.")

        # FR5: never show an unqualified low. Medium and high stay visible, with the warnings.
        supported_level = base["level"]
        if base["level"] is None or (base["level"] == LOW and not (check.sufficient and base["complete"])):
            supported_level = None
        status = ASSESSED if supported_level else INSUFFICIENT

        evidence = list(fires.items) + list(air.items)
        reasons: list[str] = []
        if base["days"]:
            peak_day = max(base["days"], key=lambda d: d.probability).date
            evidence.insert(0, EvidenceItem(
                EvidenceKind.FORECAST, f"AshAway model {self.bundle.version}", peak_day,
                f"Predicted, not a confirmed fire: conditions on {peak_day} score {max(d.probability for d in base['days']):.2f} "
                "against past fire days.",
            ))
            row = base["rows"][base["rows"]["date"] == peak_day]
            reasons = explain(self.bundle.contributions(row).iloc[0], row.iloc[0])

        text = LEVEL_TEXT[supported_level] if supported_level else (
            "INSUFFICIENT EVIDENCE: AshAway cannot give a confident answer for these dates. "
            "This does not mean the risk is low."
        )
        alternatives = []
        if with_alternatives and base["level"] in (MEDIUM, HIGH):
            alternatives = self._alternatives(request.destination_id, base, request.days, as_of)
        return Assessment(
            destination_id=request.destination_id,
            destination=request.destination_name,
            start=request.start,
            end=request.end,
            as_of=as_of,
            generated_at=stamp,
            model_version=self.bundle.version,
            status=status,
            level=supported_level,
            forecast_level=base["level"],
            peak_probability=base["peak"],
            level_text=text,
            days=base["days"],
            reasons=reasons,
            evidence=evidence,
            sources=sources,
            warnings=warnings,
            alternatives=alternatives,
        )

    def compare(self, places: list[str], start: str | date, end: str | date) -> list[dict]:
        """Side-by-side rows on the same dates and the same logic (FR7)."""
        if len(places) < 2:
            raise ValueError("A comparison needs at least two destinations.")
        table = []
        for place in places:
            a = self.assess(place, start, end, with_alternatives=False)
            newest = [s.latest_observation for s in a.sources if s.available and s.latest_observation]
            table.append({
                "destination": a.destination,
                "level": a.level or INSUFFICIENT,
                "forecast_level": a.forecast_level,
                "peak_probability": a.peak_probability,
                "evidence_age_days": (a.as_of - max(newest)).days if newest else None,
                "sources_available": f"{sum(s.available for s in a.sources)} of {len(a.sources)}",
            })
        return table

