"""Interface server: where travellers' requests come in (Task 6, T20).

    ashaway-interface --port 8000      (finds the orchestrator at ASHAWAY_ORCHESTRATOR_URL)

It serves a web page and a JSON API, checks every request before passing it on,
forwards valid ones to the orchestrator, and stores each request with its
outcome. It never calls the AI server: it has no address for it, and it does not
import the model code or pandas.
"""
from __future__ import annotations

import csv
import os
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Literal

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from ..request import RequestRejected, validate_request
from . import REQUEST_ID, add_request_tracing, default_url, error_body, serve
from .store import Store

SERVICE = "interface"
ORCHESTRATOR_TIMEOUT_S = float(os.environ.get("ASHAWAY_ORCHESTRATOR_TIMEOUT", "120"))
DEFAULT_DB = os.environ.get("ASHAWAY_DB", "data/interface.sqlite3")
PACKAGE = Path(__file__).resolve().parent.parent
PAGE = Path(__file__).resolve().parent / "static" / "index.html"


def supported_places() -> dict[str, str]:
    """Destination id -> name, read straight from the destination list (no pandas needed)."""
    with (PACKAGE / "resources" / "pilot_destinations.csv").open(encoding="utf-8", newline="") as f:
        return {row["id"]: row["name"] for row in csv.DictReader(f)}


class AssessBody(BaseModel):
    place: str = Field(max_length=100)
    start: str = Field(max_length=20)
    end: str = Field(max_length=20)


class CompareBody(BaseModel):
    places: list[str] = Field(min_length=2, max_length=11)
    start: str = Field(max_length=20)
    end: str = Field(max_length=20)


class FeedbackBody(BaseModel):
    """A traveller saying an assessment looks wrong (AI8). Reviewed by the team, never learned from automatically."""

    verdict: Literal["risk_too_high", "risk_too_low", "evidence_wrong", "other"]
    comment: str | None = Field(default=None, max_length=500)


def create_app(
    orchestrator_url: str | None = None,
    *,
    orchestrator_client: httpx.Client | None = None,
    db_path: str | Path = DEFAULT_DB,
    today: Callable[[], date] = lambda: datetime.now(timezone.utc).date(),
) -> FastAPI:
    client = orchestrator_client or httpx.Client(base_url=orchestrator_url or default_url("orchestrator"),
                                                 timeout=ORCHESTRATOR_TIMEOUT_S)
    store = Store(db_path)
    places = supported_places()
    app = FastAPI(title="AshAway interface")
    add_request_tracing(app, SERVICE)

    def forward(path: str, payload: dict, request_id: str) -> tuple[int, dict]:
        """Ask the orchestrator. Returns (status, body); an unreachable orchestrator is a 503."""
        try:
            r = client.post(path, json=payload, headers={REQUEST_ID: request_id})
        except httpx.TimeoutException:
            return 503, error_body("orchestrator_timeout", "The assessment took too long. Please try again.", SERVICE)
        except httpx.HTTPError:
            return 503, error_body("orchestrator_unavailable", "AshAway cannot assess anything right now. Please try again later.", SERVICE)
        try:
            body = r.json()
        except ValueError:
            body = {}
        if r.status_code == 200 or "error" in body:
            return r.status_code, body
        return 502, error_body("orchestrator_error", f"The orchestrator answered {r.status_code}.", SERVICE)

    @app.get("/", response_class=HTMLResponse)
    def page():
        return PAGE.read_text(encoding="utf-8")

    @app.get("/health")
    def health():
        try:
            orch = client.get("/health", timeout=5).json()
            downstream = {"status": orch.get("status", "unknown"), "ai": orch.get("ai", {}).get("status")}
        except (httpx.HTTPError, ValueError):
            downstream = {"status": "unavailable"}
        return {"service": SERVICE, "status": "ok", "orchestrator": downstream, "requests_served": app.state.requests_served}

    @app.get("/api/destinations")
    def destinations():
        return [{"id": i, "name": n} for i, n in sorted(places.items(), key=lambda kv: kv[1])]

    @app.post("/api/assess")
    def assess(body: AssessBody, request: Request):
        request_id = request.state.request_id
        assessment_id = uuid.uuid4().hex[:12]

        def keep(outcome: str, detail: dict, **extra) -> None:
            store.add(assessment_id, request_id, body.place.strip()[:100], body.start, body.end, outcome, detail, **extra)

        try:
            # Checked here first, so a bad request never reaches the other servers (FR1, FR9).
            validate_request(body.place, body.start, body.end, places, today())
        except RequestRejected as rejected:
            detail = error_body(rejected.code, rejected.message, SERVICE)
            keep("rejected", detail)
            return JSONResponse({"id": assessment_id, **detail}, 400)

        status, answer = forward("/assess", body.model_dump(), request_id)
        if status != 200:
            keep("rejected" if status == 422 else "unavailable", answer)
            return JSONResponse({"id": assessment_id, **answer}, 400 if status == 422 else status)

        result = answer["result"]
        keep(result["status"], result, level=result["level"], model_version=result["model_version"])
        trace = {"interface": {"request_id": request_id}, **answer["trace"]}
        return {"id": assessment_id, "assessment": result, "trace": trace}

    @app.post("/api/compare")
    def compare(body: CompareBody, request: Request):
        for place in body.places:
            try:
                validate_request(place, body.start, body.end, places, today())
            except RequestRejected as rejected:
                return JSONResponse(error_body(rejected.code, rejected.message, SERVICE), 400)
        status, answer = forward("/compare", body.model_dump(), request.state.request_id)
        if status != 200:
            return JSONResponse(answer, 400 if status == 422 else status)
        return {"rows": answer["result"], "trace": {"interface": {"request_id": request.state.request_id}, **answer["trace"]}}

    @app.get("/api/assessments")
    def recent(limit: int = 20):
        return store.recent(max(1, min(limit, 100)))

    @app.get("/api/assessments/{assessment_id}")
    def stored(assessment_id: str):
        found = store.get(assessment_id)
        if found is None:
            return JSONResponse(error_body("not_found", "No assessment with this id.", SERVICE), 404)
        return {**found, "feedback": store.feedback_for(assessment_id)}

    @app.post("/api/assessments/{assessment_id}/feedback", status_code=201)
    def feedback(assessment_id: str, body: FeedbackBody):
        found = store.get(assessment_id)
        if found is None or found["outcome"] not in ("assessed", "insufficient evidence"):
            return JSONResponse(error_body("not_found", "Feedback can only be given on an assessment that was made.", SERVICE), 404)
        store.add_feedback(assessment_id, body.verdict, body.comment)
        return {"saved": True, "assessment_id": assessment_id, "model_version": found["model_version"]}

    return app


def main(argv: list[str] | None = None) -> None:
    serve(create_app, SERVICE, argv)


if __name__ == "__main__":
    main(sys.argv[1:])
