from datetime import date

import pytest

from ashaway.request import AssessmentRequest, RequestRejected, validate_request

SUPPORTED = {"rhodes": "Rhodes", "olympia": "Ancient Olympia"}
TODAY = date(2026, 7, 1)


def test_U1_accepts_a_valid_request():
    result = validate_request("rhodes", "2026-07-02", "2026-07-04", SUPPORTED, TODAY)
    assert result == AssessmentRequest("rhodes", "Rhodes", date(2026, 7, 2), date(2026, 7, 4))
    assert result.days == [date(2026, 7, 2), date(2026, 7, 3), date(2026, 7, 4)]


@pytest.mark.parametrize("place", ["olympia", "OLYMPIA", " Ancient Olympia "])
def test_U1_finds_a_place_by_id_or_name(place):
    assert validate_request(place, "2026-07-02", "2026-07-02", SUPPORTED, TODAY).destination_id == "olympia"


@pytest.mark.parametrize(
    "place, start, end, code",
    [
        ("atlantis", "2026-07-02", "2026-07-04", "unsupported_place"),
        ("rhodes", "2-7-2026", "2026-07-04", "invalid_date"),
        ("rhodes", "2026-07-04", "2026-02-30", "invalid_date"),
        ("rhodes", "2026-07-04", "2026-07-02", "reversed_dates"),
        ("rhodes", "2026-04-30", "2026-05-02", "out_of_season"),
        ("rhodes", "2026-10-31", "2026-11-01", "out_of_season"),
        ("rhodes", "2025-10-01", "2026-05-02", "out_of_season"),
        ("rhodes", "2005-07-01", "2005-07-02", "before_coverage"),
        ("rhodes", "2026-07-10", "2026-07-16", "beyond_horizon"),
    ],
)
def test_U1_rejects_with_the_correct_reason(place, start, end, code):
    with pytest.raises(RequestRejected) as rejected:
        validate_request(place, start, end, SUPPORTED, TODAY)
    assert rejected.value.code == code
    assert rejected.value.message


def test_U1_last_forecast_day_is_accepted():
    assert validate_request("rhodes", "2026-07-15", "2026-07-15", SUPPORTED, TODAY).end == date(2026, 7, 15)
