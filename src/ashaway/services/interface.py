"""Interface server: where travellers' requests come in (Task 6, T20; storage moved out in T24).

    ashaway-interface --port 8000      (finds the orchestrator at ASHAWAY_ORCHESTRATOR_URL)

It serves a web page and a JSON API, checks every request before passing it on,
and forwards valid ones to the orchestrator. It keeps no data of its own: stored
assessments and feedback live behind the orchestrator, and the interface asks
for them there. It never calls the AI server: it has no address for it, and it
does not import the model code or pandas.
"""
from __future__ import annotations

import csv
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

from ..request import RequestRejected, validate_request
from . import REQUEST_ID, add_request_tracing, default_url, error_body, serve
from .schemas import AssessBody, CompareBody, FeedbackBody

SERVICE = "interface"
ORCHESTRATOR_TIMEOUT_S = float(os.environ.get("ASHAWAY_ORCHESTRATOR_TIMEOUT", "120"))
PACKAGE = Path(__file__).resolve().parent.parent
PAGE = Path(__file__).resolve().parent / "static" / "index.html"


def supported_places() -> dict[str, str]:
    """Destination id -> name, read straight from the destination list (no pandas needed)."""
    with (PACKAGE / "resources" / "pilot_destinations.csv").open(encoding="utf-8", newline="") as f:
        return {row["id"]: row["name"] for row in csv.DictReader(f)}


def create_app(
    orchestrator_url: str | None = None,
    *,
    orchestrator_client: httpx.Client | None = None,
    today: Callable[[], date] = lambda: datetime.now(timezone.utc).date(),
) -> FastAPI:
    """The interface server, passing requests to the orchestrator at `orchestrator_url`.

    `orchestrator_client` and `today` can be replaced in tests.
    """
    client = orchestrator_client or httpx.Client(base_url=orchestrator_url or default_url("orchestrator"),
                                                 timeout=ORCHESTRATOR_TIMEOUT_S)
    places = supported_places()
    app = FastAPI(title="AshAway interface")
    add_request_tracing(app, SERVICE)

    def forward(method: str, path: str, request_id: str, payload: dict | None = None,
                params: dict | None = None) -> tuple[int, dict | list]:
        """Ask the orchestrator. Returns (status, body); an unreachable orchestrator is a 503."""
        try:
            r = client.request(method, path, json=payload, params=params, headers={REQUEST_ID: request_id})
        except httpx.TimeoutException:
            return 503, error_body("orchestrator_timeout", "The assessment took too long. Please try again.", SERVICE)
        except httpx.HTTPError:
            return 503, error_body("orchestrator_unavailable", "AshAway cannot answer right now. Please try again later.", SERVICE)
        try:
            body = r.json()
        except ValueError:
            body = None
        if r.status_code in (200, 201) or (isinstance(body, dict) and "error" in body):
            # A request the orchestrator refused is the caller's mistake, so it is a 400 here.
            return (400 if r.status_code == 422 else r.status_code), body
        return 502, error_body("orchestrator_error", f"The orchestrator answered {r.status_code}.", SERVICE)

    def check(place: str, start: str, end: str) -> JSONResponse | None:
        """The interface's own check, so a bad request never reaches the other servers (FR1, FR9)."""
        try:
            validate_request(place, start, end, places, today())
        except RequestRejected as rejected:
            return JSONResponse(error_body(rejected.code, rejected.message, SERVICE), 400)
        return None

    def traced(body: dict, request_id: str) -> dict:
        return {"interface": {"request_id": request_id}, **body.get("trace", {})}

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
        rid = request.state.request_id
        refused = check(body.place, body.start, body.end)
        if refused:
            return refused
        status, answer = forward("POST", "/assess", rid, body.model_dump())
        if status == 200:
            answer = {"id": answer["id"], "assessment": answer["result"], "trace": traced(answer, rid)}
        return JSONResponse(answer, status)

    @app.post("/api/compare")
    def compare(body: CompareBody, request: Request):
        rid = request.state.request_id
        for place in body.places:
            refused = check(place, body.start, body.end)
            if refused:
                return refused
        status, answer = forward("POST", "/compare", rid, body.model_dump())
        if status == 200:
            answer = {"rows": answer["result"], "trace": traced(answer, rid)}
        return JSONResponse(answer, status)

    @app.get("/api/assessments")
    def recent(request: Request, limit: int = 20):
        status, answer = forward("GET", "/assessments", request.state.request_id, params={"limit": limit})
        return JSONResponse(answer, status)

    @app.get("/api/assessments/{assessment_id}")
    def stored(assessment_id: str, request: Request):
        status, answer = forward("GET", f"/assessments/{assessment_id}", request.state.request_id)
        return JSONResponse(answer, status)

    @app.post("/api/assessments/{assessment_id}/feedback", status_code=201)
    def feedback(assessment_id: str, body: FeedbackBody, request: Request):
        status, answer = forward("POST", f"/assessments/{assessment_id}/feedback", request.state.request_id, body.model_dump())
        return JSONResponse(answer, status)

    return app


def main(argv: list[str] | None = None) -> None:
    """Command line: `ashaway-interface [--host H] [--port P]`."""
    serve(create_app, SERVICE, argv)


if __name__ == "__main__":
    main(sys.argv[1:])
