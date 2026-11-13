"""I9: the interface server with its storage, in front of a stand-in orchestrator."""
import json
import subprocess
import sys

import httpx
import pytest
from fastapi.testclient import TestClient

from ashaway.services import interface

RHODES = {"place": "rhodes", "start": "2023-07-18", "end": "2023-07-24"}
RESULT = {"status": "assessed", "level": "high", "model_version": "live-v1", "destination": "Rhodes"}


def orchestrator_stub(calls, status=200, body=None):
    """Answers like the orchestrator and records what it was sent."""
    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        payload = body if body is not None else {"result": RESULT, "trace": {"orchestrator": {"ai_calls": 3}}}
        return httpx.Response(status, json=payload)
    return httpx.Client(base_url="http://orchestrator", transport=httpx.MockTransport(handle))


def make_interface(tmp_path, client):
    return TestClient(interface.create_app(orchestrator_client=client, db_path=tmp_path / "db.sqlite3"))


def test_I9_valid_request_is_forwarded_stored_and_retrievable(tmp_path):
    calls = []
    api = make_interface(tmp_path, orchestrator_stub(calls))
    r = api.post("/api/assess", json=RHODES)
    assert r.status_code == 200
    body = r.json()
    assert body["assessment"] == RESULT
    assert json.loads(calls[0].content) == RHODES
    assert calls[0].headers["X-Request-ID"] == r.headers["X-Request-ID"] == body["trace"]["interface"]["request_id"]
    stored = api.get(f"/api/assessments/{body['id']}").json()
    assert (stored["outcome"], stored["level"], stored["model_version"], stored["detail"]) == ("assessed", "high", "live-v1", RESULT)
    assert api.get("/api/assessments").json()[0]["id"] == body["id"]


@pytest.mark.parametrize("change, code", [
    ({"place": "atlantis"}, "unsupported_place"),
    ({"start": "18-07-2023"}, "invalid_date"),
    ({"start": "2023-12-01", "end": "2023-12-03"}, "out_of_season"),
])
def test_I9_bad_request_is_refused_and_never_forwarded(tmp_path, change, code):
    calls = []
    api = make_interface(tmp_path, orchestrator_stub(calls))
    r = api.post("/api/assess", json={**RHODES, **change})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == code
    assert calls == []
    assert api.get(f"/api/assessments/{r.json()['id']}").json()["outcome"] == "rejected"


def test_I9_unreachable_orchestrator_gives_503_and_is_recorded(tmp_path):
    def refuse(request):
        raise httpx.ConnectError("refused", request=request)
    api = make_interface(tmp_path, httpx.Client(base_url="http://orchestrator", transport=httpx.MockTransport(refuse)))
    r = api.post("/api/assess", json=RHODES)
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "orchestrator_unavailable"
    assert api.get(f"/api/assessments/{r.json()['id']}").json()["outcome"] == "unavailable"


def test_I9_ai_outage_reported_by_the_orchestrator_is_passed_on(tmp_path):
    error = {"error": {"code": "ai_unavailable", "message": "No assessment was made.", "service": "orchestrator"}}
    r = make_interface(tmp_path, orchestrator_stub([], 503, error)).post("/api/assess", json=RHODES)
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "ai_unavailable"
    assert "assessment" not in r.json()


def test_I9_feedback_is_stored_with_the_assessment(tmp_path):
    api = make_interface(tmp_path, orchestrator_stub([]))
    assessment_id = api.post("/api/assess", json=RHODES).json()["id"]
    r = api.post(f"/api/assessments/{assessment_id}/feedback", json={"verdict": "risk_too_high", "comment": "Calm all week."})
    assert r.status_code == 201
    assert r.json() == {"saved": True, "assessment_id": assessment_id, "model_version": "live-v1"}
    feedback = api.get(f"/api/assessments/{assessment_id}").json()["feedback"]
    assert [(f["verdict"], f["comment"]) for f in feedback] == [("risk_too_high", "Calm all week.")]


@pytest.mark.parametrize("body", [{"verdict": "great"}, {"verdict": "other", "comment": "x" * 501}])
def test_I9_invalid_feedback_is_refused(tmp_path, body):
    api = make_interface(tmp_path, orchestrator_stub([]))
    assessment_id = api.post("/api/assess", json=RHODES).json()["id"]
    assert api.post(f"/api/assessments/{assessment_id}/feedback", json=body).status_code == 422


def test_I9_no_feedback_on_a_refused_or_unknown_request(tmp_path):
    api = make_interface(tmp_path, orchestrator_stub([]))
    refused = api.post("/api/assess", json={**RHODES, "place": "atlantis"}).json()["id"]
    for assessment_id in (refused, "nope"):
        assert api.post(f"/api/assessments/{assessment_id}/feedback", json={"verdict": "other"}).status_code == 404


def test_I9_unknown_assessment_id_is_404(tmp_path):
    assert make_interface(tmp_path, orchestrator_stub([])).get("/api/assessments/nope").status_code == 404


def test_I9_web_page_and_destinations_are_served(tmp_path):
    api = make_interface(tmp_path, orchestrator_stub([]))
    assert "AshAway" in api.get("/").text
    assert {"id": "rhodes", "name": "Rhodes"} in api.get("/api/destinations").json()


def test_I9_interface_cannot_reach_the_model():
    """Importing the interface server loads no model code, no XGBoost and no pandas."""
    check = (
        "import sys, ashaway.services.interface as i; "
        "heavy = [m for m in ('xgboost', 'pandas', 'ashaway.model', 'ashaway.assess', 'ashaway.services.ai', "
        "'ashaway.services.orchestrator') if m in sys.modules]; "
        "print(','.join(heavy))"
    )
    out = subprocess.run([sys.executable, "-c", check], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == ""
