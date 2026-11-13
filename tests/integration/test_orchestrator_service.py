"""I8: the orchestrator server with recorded feeds and the AI server behind it."""
import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient

from ashaway.services import ai, orchestrator

from conftest import FIXED_NOW, FIRMS_TEST_KEY, ReplayFetch

RHODES = {"place": "rhodes", "start": "2023-07-18", "end": "2023-07-24"}


@pytest.fixture
def ai_client(bundle):
    return TestClient(ai.create_app(bundle))


def make_orchestrator(ai_client, tmp_path, down=()):
    app = orchestrator.create_app(ai_client=ai_client, fetch=ReplayFetch(down), clock=lambda: FIXED_NOW,
                                  firms_key=FIRMS_TEST_KEY, log_path=tmp_path / "updates.jsonl")
    return TestClient(app)


def test_I8_assessment_through_the_ai_server_equals_the_in_process_one(ai_client, tmp_path, make_assessor):
    r = make_orchestrator(ai_client, tmp_path).post("/assess", json=RHODES)
    assert r.status_code == 200
    body = r.json()
    result, trace = body["result"], body["trace"]["orchestrator"]
    local = make_assessor().assess(RHODES["place"], RHODES["start"], RHODES["end"])
    assert (result["status"], result["level"], result["model_version"]) == ("assessed", "high", "live-v1")
    np.testing.assert_allclose([d["probability"] for d in result["days"]], [d.probability for d in local.days], rtol=0, atol=1e-12)
    assert result["reasons"] == local.reasons
    assert trace["ai_calls"] >= 2 and trace["request_id"] == r.headers["X-Request-ID"]


def test_I8_unsupported_place_is_refused_without_asking_the_ai_server(ai_client, tmp_path):
    before = ai_client.app.state.requests_served
    r = make_orchestrator(ai_client, tmp_path).post("/assess", json={**RHODES, "place": "atlantis"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "unsupported_place"
    assert ai_client.app.state.requests_served == before


def test_I8_ai_server_down_gives_503_and_no_assessment(tmp_path):
    down = httpx.Client(base_url="http://127.0.0.1:9", transport=httpx.HTTPTransport(retries=0), timeout=1)
    client = make_orchestrator(down, tmp_path)
    r = client.post("/assess", json=RHODES)
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "ai_unavailable"
    assert "result" not in r.json()
    assert client.get("/health").json()["status"] == "degraded"


def test_I8_failed_weather_feed_still_gives_an_honest_answer(ai_client, tmp_path):
    result = make_orchestrator(ai_client, tmp_path, down=["weather"]).post("/assess", json=RHODES).json()["result"]
    assert (result["status"], result["level"]) == ("insufficient evidence", None)
    assert any("Open-Meteo weather" in w for w in result["warnings"])


def test_I8_compare_runs_through_the_orchestrator(ai_client, tmp_path):
    body = {"places": ["rhodes", "chania"], "start": "2023-07-18", "end": "2023-07-24"}
    rows = make_orchestrator(ai_client, tmp_path).post("/compare", json=body).json()["result"]
    assert [row["destination"] for row in rows] == ["Rhodes", "Chania"]


def test_I8_health_and_destinations(ai_client, tmp_path):
    client = make_orchestrator(ai_client, tmp_path)
    assert client.get("/health").json()["ai"] == {"status": "ok", "model_version": "live-v1"}
    assert {"id": "rhodes", "name": "Rhodes"} in client.get("/destinations").json()
