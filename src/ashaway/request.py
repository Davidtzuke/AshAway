"""Validate a traveller's request before anything is computed (FR1, FR9)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Mapping

SEASON_MONTHS = range(5, 11)  # May to October
COVERAGE_START = date(2006, 6, 1)  # first season in the training data
FORECAST_HORIZON_DAYS = 14  # weather forecasts stop being usable around here


class RequestRejected(ValueError):
    """A request AshAway must refuse. `code` is stable; `message` is shown to the user."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class AssessmentRequest:
    destination_id: str
    destination_name: str
    start: date
    end: date

    @property
    def days(self) -> list[date]:
        return [self.start + timedelta(days=i) for i in range((self.end - self.start).days + 1)]


def _parse_date(value: str | date, label: str) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise RequestRejected("invalid_date", f"The {label} date '{value}' is not a date. Use YYYY-MM-DD.") from None


def validate_request(
    place: str, start: str | date, end: str | date, supported: Mapping[str, str], today: date
) -> AssessmentRequest:
    """Return the accepted request, or raise RequestRejected with the reason.

    `supported` maps destination id to display name. `place` can be either, in any case.
    """
    wanted = str(place).strip().casefold()
    matches = [i for i, name in supported.items() if wanted in (i.casefold(), name.casefold())]
    if not matches:
        raise RequestRejected(
            "unsupported_place",
            f"'{place}' is not a supported destination. AshAway does not assess it rather than guess. "
            f"Supported: {', '.join(sorted(supported.values()))}.",
        )
    start_day, end_day = _parse_date(start, "start"), _parse_date(end, "end")
    if start_day > end_day:
        raise RequestRejected("reversed_dates", f"The start date {start_day} is after the end date {end_day}.")
    if start_day.year != end_day.year or start_day.month not in SEASON_MONTHS or end_day.month not in SEASON_MONTHS:
        raise RequestRejected(
            "out_of_season", f"AshAway only covers May to October, and {start_day} to {end_day} falls outside that."
        )
    if start_day < COVERAGE_START:
        raise RequestRejected("before_coverage", f"AshAway has no data before {COVERAGE_START}.")
    horizon = today + timedelta(days=FORECAST_HORIZON_DAYS)
    if end_day > horizon:
        raise RequestRejected(
            "beyond_horizon",
            f"AshAway can only assess up to {FORECAST_HORIZON_DAYS} days ahead (until {horizon}), "
            f"because no reliable weather forecast exists for {end_day} yet.",
        )
    return AssessmentRequest(matches[0], supported[matches[0]], start_day, end_day)
