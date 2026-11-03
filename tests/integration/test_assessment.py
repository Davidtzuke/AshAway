"""I3 to I5: recorded feeds, the saved model and the assessment service working together."""
import json
from datetime import date

import pytest

from ashaway.assess import ASSESSED, INSUFFICIENT
from ashaway.evidence import EvidenceKind
from ashaway.feeds import AIR, DISRUPTION, FIRES, WEATHER
from ashaway.request import RequestRejected
from ashaway.risk import DISCLAIMER, LEVEL_ORDER

# The July 2023 Rhodes fires led to Greece's largest wildfire evacuation (Task 1).
RHODES = ("rhodes", "2023-07-18", "2023-07-24")
# A cool, wet early June in Chania, for which the model says low.
CHANIA = ("chania", "2023-06-01", "2023-06-03")


def test_I3_rhodes_heatwave_gives_a_complete_high_assessment(make_assessor):
    a = make_assessor().assess(*RHODES)
    assert a.status == ASSESSED
    assert a.level == "high"
    assert a.as_of == date(2023, 7, 17)  # replayed from the day before the trip
    assert [d.date for d in a.days] == [date(2023, 7, 18 + i) for i in range(7)]
    assert all(0 <= d.probability <= 1 for d in a.days)
    assert a.model_version == "live-v1" and a.generated_at
    assert a.disclaimer == DISCLAIMER
    assert a.reasons and all(isinstance(r, str) for r in a.reasons)


def test_I3_every_evidence_item_is_labelled_dated_and_sourced(make_assessor):
    a = make_assessor().assess(*RHODES)
    assert [e.kind for e in a.evidence] == [EvidenceKind.FORECAST, EvidenceKind.OBSERVATION, EvidenceKind.OBSERVATION]
    assert all(e.source and e.observed_on and e.summary for e in a.evidence)
    assert "not a confirmed fire" in a.evidence[0].summary
    fires = next(e for e in a.evidence if e.source == FIRES)
    assert fires.summary.startswith("2 satellite heat detection(s) within 20 km")  # a third is too far away


def test_I3_evidence_after_the_assessment_date_is_ignored(make_assessor):
    a = make_assessor().assess(*RHODES)
    assert all(e.observed_on <= a.as_of for e in a.evidence if e.kind is EvidenceKind.OBSERVATION)


def test_I3_low_forecast_with_full_evidence_is_stated_as_low(make_assessor):
    a = make_assessor(firms_file="no_fires.csv").assess(*CHANIA)
    assert (a.status, a.level) == (ASSESSED, "low")
    assert a.alternatives == []


def test_I3_low_forecast_with_fires_nearby_is_a_flagged_conflict(make_assessor):
    a = make_assessor(firms_file="chania_firms.csv").assess(*CHANIA)
    assert (a.status, a.level, a.forecast_level) == (INSUFFICIENT, None, "low")
    assert any("detected 1 fire(s) nearby" in w for w in a.warnings)


def test_I3_every_update_is_logged_without_user_data(make_assessor, tmp_path):
    make_assessor(down=["air"]).assess(*RHODES)
    lines = [json.loads(line) for line in (tmp_path / "updates.jsonl").read_text().splitlines()]
    assert {line["name"] for line in lines} == {WEATHER, FIRES, AIR, DISRUPTION}
    failed = next(line for line in lines if line["name"] == AIR)
    assert failed["available"] is False and "500" in failed["error"] and failed["retrieved_at"]
    assert set(lines[0]) == {"destination", "name", "critical", "available", "retrieved_at", "latest_observation", "error"}


def test_I4_weather_failure_gives_no_score_and_no_invented_values(make_assessor):
    a = make_assessor(down=["weather"]).assess(*RHODES)
    assert (a.status, a.level, a.forecast_level, a.peak_probability) == (INSUFFICIENT, None, None, None)
    assert a.days == [] and a.reasons == []
    assert next(s for s in a.sources if s.name == WEATHER).available is False
    assert a.level_text.startswith("INSUFFICIENT EVIDENCE")
    assert a.disclaimer == DISCLAIMER


@pytest.mark.parametrize("failure", [{"down": ["firms"]}, {"firms_key": None}])
def test_I4_fire_feed_failure_blocks_a_low_result(make_assessor, failure):
    a = make_assessor(**failure).assess(*CHANIA)
    assert (a.status, a.level, a.forecast_level) == (INSUFFICIENT, None, "low")
    assert any(FIRES in w for w in a.warnings)


def test_I4_fire_feed_failure_keeps_a_high_warning_visible(make_assessor):
    a = make_assessor(down=["firms"]).assess(*RHODES)
    assert (a.status, a.level) == (ASSESSED, "high")
    assert any(FIRES in w for w in a.warnings)


def test_I4_optional_feed_failure_is_reported_and_not_filled_in(make_assessor):
    a = make_assessor(down=["air"], firms_file="no_fires.csv").assess(*CHANIA)
    assert a.level == "low"
    assert all(e.source != AIR for e in a.evidence)
    assert next(s for s in a.sources if s.name == AIR).available is False


def test_I4_a_firms_key_never_appears_in_an_error(make_assessor):
    a = make_assessor(down=["firms"], firms_key="secret-key").assess(*RHODES)
    assert all("secret-key" not in (s.error or "") for s in a.sources)


def test_I4_weather_gaps_block_a_low_result(make_assessor):
    # Weather recordings stop on 2023-07-31, so the last days of this trip have no history.
    a = make_assessor(firms_file="no_fires.csv").assess("chania", "2023-07-30", "2023-08-02")
    assert len(a.days) < 4
    assert any("could be scored" in w for w in a.warnings)
    assert a.level != "low"


def test_I5_alternatives_are_lower_risk_on_the_same_dates(make_assessor):
    a = make_assessor().assess("rhodes", "2023-07-01", "2023-07-03")
    assert a.forecast_level in ("medium", "high")
    assert 1 <= len(a.alternatives) <= 3
    for alt in a.alternatives:
        assert alt["id"] != "rhodes"
        assert LEVEL_ORDER[alt["level"]] < LEVEL_ORDER[a.forecast_level]
        assert "not proof of safety" in alt["note"]
    peaks = [alt["peak_probability"] for alt in a.alternatives]
    assert peaks == sorted(peaks)


def test_I5_comparison_uses_the_same_dates_for_each_destination(make_assessor):
    table = make_assessor().compare(["rhodes", "chania"], "2023-07-18", "2023-07-24")
    assert [row["destination"] for row in table] == ["Rhodes", "Chania"]
    for row in table:
        assert set(row) == {
            "destination", "level", "forecast_level", "peak_probability", "evidence_age_days", "sources_available",
        }
        assert row["evidence_age_days"] == 0


def test_I5_comparison_needs_two_destinations(make_assessor):
    with pytest.raises(ValueError):
        make_assessor().compare(["rhodes"], "2023-07-18", "2023-07-24")


def test_I5_comparison_rejects_an_unsupported_place(make_assessor):
    with pytest.raises(RequestRejected):
        make_assessor().compare(["rhodes", "atlantis"], "2023-07-18", "2023-07-24")


def test_I4_old_weather_is_flagged_as_stale_and_not_scored(make_assessor):
    # Weather recordings stop on 2023-07-31, nine days before this assessment date.
    a = make_assessor(firms_file="no_fires.csv").assess("chania", "2023-08-10", "2023-08-12")
    assert (a.status, a.level, a.days) == (INSUFFICIENT, None, [])
    assert any(WEATHER in w and "too old" in w for w in a.warnings)
