"""I7: the AI inference server's HTTP API, with the real saved model behind it."""
from datetime import date, timedelta

import numpy as np
import pytest
from fastapi.testclient import TestClient

from ashaway.assess import HISTORY_DAYS, daily_feature_rows, load_destinations
from ashaway.feeds import parse_weather
from ashaway.services.ai import create_app

from conftest import FEEDS_DIR


@pytest.fixture(scope="module")
def rhodes_rows():
    """Real feature rows: Rhodes, 18-20 July 2023, built from the recorded weather."""
    weather = parse_weather((FEEDS_DIR / "rhodes_weather.json").read_text(encoding="utf-8"))
    days = [date(2023, 7, 18) + timedelta(days=i) for i in range(3)]
    rows = daily_feature_rows(weather, load_destinations().loc["rhodes"], days)
    assert len(rows) == 3 and HISTORY_DAYS == 29
    return rows


@pytest.fixture(scope="module")
def client(bundle):
    return TestClient(create_app(bundle))


def payload(rows, features, explain=False):
    return {"rows": rows[features].astype(float).to_dict(orient="records"), "explain": explain}


def test_I7_model_endpoint_describes_the_saved_model(client, bundle):
    info = client.get("/model").json()
    assert info == {"version": "live-v1", "features": bundle.features,
                    "medium_from": bundle.medium_from, "high_from": bundle.high_from}


def test_I7_predict_matches_the_model_in_process(client, bundle, rhodes_rows):
    r = client.post("/predict", json=payload(rhodes_rows, bundle.features, explain=True))
    assert r.status_code == 200
    body = r.json()
    np.testing.assert_allclose(body["probabilities"], bundle.predict(rhodes_rows), rtol=0, atol=1e-12)
    assert body["model_version"] == "live-v1"
    assert [list(c) for c in body["contributions"]] == [bundle.features] * 3


def test_I7_without_explain_no_contributions_are_sent(client, bundle, rhodes_rows):
    assert "contributions" not in client.post("/predict", json=payload(rhodes_rows, bundle.features)).json()


def test_I7_a_row_missing_a_feature_is_refused_by_name(client, bundle, rhodes_rows):
    body = payload(rhodes_rows, bundle.features)
    del body["rows"][1]["rain_7d"]
    r = client.post("/predict", json=body)
    assert r.status_code == 422
    assert r.json()["error"] == {"code": "missing_features", "message": "Row 1 lacks rain_7d.", "service": "ai"}


@pytest.mark.parametrize("rows", [[], "not rows", [{"t2m_max": "hot"}]])
def test_I7_malformed_requests_are_refused(client, rows):
    assert client.post("/predict", json={"rows": rows}).status_code == 422


def test_I7_health_reports_the_model_version(client):
    assert client.get("/health").json()["model_version"] == "live-v1"
