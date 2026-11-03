from datetime import date

import pytest

from ashaway.evidence import SourceStatus, check_evidence, is_stale

AS_OF = date(2026, 7, 10)


def source(name="fire", critical=True, available=True, latest=AS_OF):
    return SourceStatus(name, critical, available, "2026-07-10T12:00:00+00:00", latest_observation=latest)


@pytest.mark.parametrize(
    "latest, expected",
    [(date(2026, 7, 10), False), (date(2026, 7, 8), False), (date(2026, 7, 7), True), (None, True)],
)
def test_U3_is_stale_at_the_age_limit(latest, expected):
    assert is_stale(latest, AS_OF, max_age_days=2) is expected


def test_U3_all_sources_current_is_sufficient():
    check = check_evidence([source()], AS_OF, "low", fire_count=0)
    assert check.sufficient
    assert check.warnings == []


def test_U3_missing_critical_source_is_insufficient():
    check = check_evidence([source(available=False, latest=None)], AS_OF, "low", fire_count=0)
    assert check.missing_critical == ["fire"]
    assert not check.sufficient


def test_U3_stale_critical_source_is_insufficient():
    check = check_evidence([source(latest=date(2026, 7, 1))], AS_OF, "low", fire_count=0)
    assert check.stale_critical == ["fire"]
    assert not check.sufficient


def test_U3_missing_optional_source_only_warns():
    check = check_evidence([source("news", critical=False, available=False, latest=None)], AS_OF, "low", fire_count=0)
    assert check.sufficient
    assert "news" in check.warnings[0]


@pytest.mark.parametrize("level, fires, conflict", [("low", 3, True), ("low", 0, False), ("high", 3, False)])
def test_U3_low_forecast_with_detected_fires_is_a_conflict(level, fires, conflict):
    assert bool(check_evidence([source()], AS_OF, level, fires).conflicts) is conflict
