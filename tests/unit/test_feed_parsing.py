import json
from datetime import date

import numpy as np
import pytest

from ashaway.feeds import firms_url, parse_air, parse_firms, parse_weather, weather_url


def weather_json(temp=30.0, humidity=40, wind=5.0, rain=5.0):
    return json.dumps({"daily": {
        "time": ["2023-07-10"],
        "temperature_2m_max": [temp],
        "relative_humidity_2m_min": [humidity],
        "wind_speed_10m_max": [wind],
        "precipitation_sum": [rain],
    }})


def test_U4_parse_weather_converts_to_training_units():
    row = parse_weather(weather_json()).iloc[0]
    assert row["date"] == date(2023, 7, 10)
    assert row["t2m_max"] == pytest.approx(303.15)
    assert row["rh_min"] == pytest.approx(0.40)
    assert row["wind_speed"] == pytest.approx(5.0)
    assert row["tp"] == pytest.approx(0.005)


def test_U4_parse_weather_keeps_a_null_as_missing_not_zero():
    row = parse_weather(weather_json(rain=None)).iloc[0]
    assert np.isnan(row["tp"])


@pytest.mark.parametrize("text", ['{"error": true, "reason": "bad"}', "[]", "<html>down</html>"])
def test_U4_parse_weather_rejects_a_malformed_response(text):
    with pytest.raises(ValueError):
        parse_weather(text)


def test_parse_air_averages_each_day_and_skips_empty_hours():
    text = json.dumps({"hourly": {
        "time": ["2023-07-10T00:00", "2023-07-10T01:00", "2023-07-10T02:00", "2023-07-11T00:00"],
        "pm2_5": [10.0, None, 20.0, 5.0],
    }})
    daily = parse_air(text)
    assert daily[date(2023, 7, 10)] == pytest.approx(15.0)
    assert daily[date(2023, 7, 11)] == pytest.approx(5.0)


def test_parse_firms_keeps_detections_in_radius_and_up_to_the_date():
    text = (
        "latitude,longitude,acq_date\n"
        "36.23,28.00,2023-07-16\n"  # near the point
        "37.50,28.00,2023-07-16\n"  # about 140 km away
        "36.23,28.00,2023-07-18\n"  # after the assessment date
    )
    fires = parse_firms(text, lat=36.23, lon=27.99, radius_km=20, as_of=date(2023, 7, 17))
    assert len(fires) == 1
    assert fires.iloc[0]["km"] < 2


@pytest.mark.parametrize("text", ["Invalid MAP_KEY.", ""])
def test_parse_firms_rejects_an_error_message(text):
    with pytest.raises(ValueError):
        parse_firms(text, lat=36.23, lon=27.99, radius_km=20, as_of=date(2023, 7, 17))


def test_urls_pick_archive_or_live_service_by_date():
    today = date(2026, 7, 10)
    assert "archive-api" in weather_url(36.0, 28.0, date(2023, 7, 1), date(2023, 7, 2), today)
    assert "archive-api" not in weather_url(36.0, 28.0, date(2026, 7, 1), date(2026, 7, 12), today)
    assert "VIIRS_SNPP_NRT" in firms_url("k", 36.0, 28.0, date(2026, 7, 9), today, 20)
    assert "VIIRS_SNPP_SP" in firms_url("k", 36.0, 28.0, date(2023, 7, 9), today, 20)
