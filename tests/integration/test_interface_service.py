"""I9: the interface server in front of a stand-in orchestrator.

The interface checks requests and passes them on; it keeps no data of its own.
"""
import json
import subprocess
import sys

import httpx
import pytest
from fastapi.testclient import TestClient

from ashaway.services import interface

RHODES = {"place": "rhodes", "start": "2023-07-18", "end": "2023-07-24"}
RESULT = {"status": "assessed", "level": "high", "model_version": "live-v1", "destination": "Rhodes"}
ANSWER = {"id": "a1b2c3", "result": RESULT, "trace": {"orchestrator": {"request_id": "x", "ai_calls": 3}}}


def orchestrator_stub(calls, status=200, body=None):
    """Answers like the orchestrator and records what it was sent."""
    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status, json=ANSWER if body is None else body)
    return httpx.Client(base_url="http://orchestrator", transport=httpx.MockTransport(handle))


def make_interface(client):
    return TestClient(interface.create_app(orchestrator_client=client))


def test_I9_valid_request_is_forwarded_and_answered(tmp_path):
    calls = []
    r = make_interface(orchestrator_stub(calls)).post("/api/assess", json=RHODES)
    assert r.status_code == 200
    body = r.json()
    assert (body["id"], body["assessment"]) == ("a1b2c3", RESULT)
    assert json.loads(calls[0].content) == {**RHODES, "alternatives": True}
    assert calls[0].url.path == "/assess"
    assert calls[0].headers["X-Request-ID"] == r.headers["X-Request-ID"] == body["trace"]["interface"]["request_id"]
    assert body["trace"]["orchestrator"]["ai_calls"] == 3


@pytest.mark.parametrize("change, code", [
    ({"place": "atlantis"}, "unsupported_place"),
    ({"start": "18-07-2023"}, "invalid_date"),
    ({"start": "2023-12-01", "end": "2023-12-03"}, "out_of_season"),
])
def test_I9_bad_request_is_refused_and_never_forwarded(change, code):
    calls = []
    r = make_interface(orchestrator_stub(calls)).post("/api/assess", json={**RHODES, **change})
    assert r.status_code == 400
    assert r.json()["error"] == {"code": code, "message": r.json()["error"]["message"], "service": "interface"}
    assert calls == []


def test_I9_unreachable_orchestrator_gives_503():
    def refuse(request):
        raise httpx.ConnectError("refused", request=request)
    r = make_interface(httpx.Client(base_url="http://orchestrator", transport=httpx.MockTransport(refuse))).post("/api/assess", json=RHODES)
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "orchestrator_unavailable"


def test_I9_ai_outage_reported_by_the_orchestrator_is_passed_on():
    error = {"id": "z9", "error": {"code": "ai_unavailable", "message": "No assessment was made.", "service": "orchestrator"}}
    r = make_interface(orchestrator_stub([], 503, error)).post("/api/assess", json=RHODES)
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "ai_unavailable"
    assert "assessment" not in r.json()


def test_I9_a_refusal_by_the_orchestrator_becomes_a_400():
    error = {"error": {"code": "beyond_horizon", "message": "Too far ahead.", "service": "orchestrator"}}
    assert make_interface(orchestrator_stub([], 422, error)).post("/api/assess", json=RHODES).status_code == 400


def test_I9_stored_assessments_are_fetched_from_the_orchestrator():
    calls = []
    api = make_interface(orchestrator_stub(calls, body={"id": "a1b2c3", "outcome": "assessed"}))
    assert api.get("/api/assessments/a1b2c3").json() == {"id": "a1b2c3", "outcome": "assessed"}
    api.get("/api/assessments", params={"limit": 5})
    assert [(c.method, c.url.path, c.url.params.get("limit")) for c in calls] == [
        ("GET", "/assessments/a1b2c3", None), ("GET", "/assessments", "5")]


def test_I9_unknown_assessment_404_is_passed_on():
    missing = {"error": {"code": "not_found", "message": "No assessment with this id.", "service": "orchestrator"}}
    assert make_interface(orchestrator_stub([], 404, missing)).get("/api/assessments/nope").status_code == 404


def test_I9_feedback_is_checked_then_forwarded():
    calls = []
    api = make_interface(orchestrator_stub(calls, 201, {"saved": True}))
    r = api.post("/api/assessments/a1b2c3/feedback", json={"verdict": "risk_too_high", "comment": "Calm all week."})
    assert r.status_code == 201
    assert (calls[0].url.path, json.loads(calls[0].content)) == (
        "/assessments/a1b2c3/feedback", {"verdict": "risk_too_high", "comment": "Calm all week."})


@pytest.mark.parametrize("body", [{"verdict": "great"}, {"verdict": "other", "comment": "x" * 501}])
def test_I9_invalid_feedback_is_refused_by_the_interface(body):
    calls = []
    assert make_interface(orchestrator_stub(calls)).post("/api/assessments/a1/feedback", json=body).status_code == 422
    assert calls == []


def test_I9_web_page_and_destinations_are_served():
    api = make_interface(orchestrator_stub([]))
    assert "AshAway" in api.get("/").text
    assert {"id": "rhodes", "name": "Rhodes"} in api.get("/api/destinations").json()


def test_I9_interface_cannot_reach_the_model_or_the_data():
    """Importing the interface server loads no model code, no XGBoost, no pandas and no storage."""
    check = (
        "import sys, ashaway.services.interface as i; "
        "heavy = [m for m in ('xgboost', 'pandas', 'sqlite3', 'ashaway.model', 'ashaway.assess', 'ashaway.services.ai', "
        "'ashaway.services.orchestrator', 'ashaway.services.store') if m in sys.modules]; "
        "print(','.join(heavy))"
    )
    out = subprocess.run([sys.executable, "-c", check], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == ""
