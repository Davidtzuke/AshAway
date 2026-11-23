"""Orchestrator server: coordinates every assessment (Task 6, T19).

    ashaway-orchestrator --port 8001      (finds the AI server at ASHAWAY_AI_URL)

It runs the Task 5 assessment logic unchanged: request checks, weather, fire and
air-quality feeds, features, evidence checks and alternatives. The one change is
the model: instead of loading it, the orchestrator hands the assessment a
RemoteModel that sends every prediction to the AI server over HTTP.

If the AI server cannot answer, no assessment is made and the caller gets a 503
saying so. A failed feed is handled as in Task 5: the source is marked
unavailable and the answer becomes "insufficient evidence" where needed.

The orchestrator also owns the storage: every assessment it handles, its
outcome and any feedback on it go into one SQLite file. The interface asks the
orchestrator for stored assessments instead of keeping its own copy, so all
state sits behind one server (changed after the Task 6 feedback, T24).
"""
from __future__ import annotations

import os
import sys
import time
import uuid
from pathlib import Path
from typing import Callable

import httpx
import numpy as np
import pandas as pd
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from .. import feeds
from ..assess import Assessor, load_destinations
from ..replay import ReplayFetch
from ..request import RequestRejected
from . import REQUEST_ID, add_request_tracing, default_url, error_body, serve
from .schemas import AssessBody, CompareBody, FeedbackBody
from .store import Store

SERVICE = "orchestrator"
AI_TIMEOUT_S = float(os.environ.get("ASHAWAY_AI_TIMEOUT", "10"))
UPDATE_LOG = "logs/feed_updates.jsonl"
DEFAULT_DB = os.environ.get("ASHAWAY_DB", "data/ashaway.sqlite3")


class ModelUnavailable(RuntimeError):
    """The AI server could not give an answer."""


class RemoteModel:
    """Stands in for ModelBundle; every call goes to the AI server.

    Create one per request: the model's description is fetched once and then
    reused, so a whole assessment uses one model version.
    """

    def __init__(self, client: httpx.Client, request_id: str | None = None):
        self.client = client
        self.headers = {REQUEST_ID: request_id} if request_id else {}
        self.calls = 0
        self._info: dict | None = None

    def _call(self, method: str, path: str, **kwargs) -> dict:
        try:
            response = self.client.request(method, path, headers=self.headers, **kwargs)
        except httpx.HTTPError as exc:
            raise ModelUnavailable(f"the AI server could not be reached ({type(exc).__name__})") from exc
        self.calls += 1
        if response.status_code != 200:
            raise ModelUnavailable(f"the AI server answered {response.status_code}: {response.text[:200]}")
        return response.json()

    @property
    def info(self) -> dict:
        if self._info is None:
            self._info = self._call("GET", "/model")
        return self._info

    @property
    def version(self) -> str:
        return self.info["version"]

    @property
    def features(self) -> list[str]:
        return self.info["features"]

    @property
    def medium_from(self) -> float:
        return self.info["medium_from"]

    @property
    def high_from(self) -> float:
        return self.info["high_from"]

    def _rows(self, df: pd.DataFrame) -> list[dict]:
        return df[self.features].astype(float).to_dict(orient="records")

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        return np.asarray(self._call("POST", "/predict", json={"rows": self._rows(df)})["probabilities"], dtype=float)

    def contributions(self, df: pd.DataFrame) -> pd.DataFrame:
        out = self._call("POST", "/predict", json={"rows": self._rows(df), "explain": True})["contributions"]
        return pd.DataFrame(out, columns=self.features, index=df.index)


def create_app(
    ai_url: str | None = None,
    *,
    ai_client: httpx.Client | None = None,
    fetch: feeds.Fetch | None = None,
    clock: Callable = feeds.now_utc,
    firms_key: str | None = None,
    log_path: str | None = UPDATE_LOG,
    db_path: str | Path = DEFAULT_DB,
    destinations: pd.DataFrame | None = None,
) -> FastAPI:
    """`ai_client`, `fetch` and `clock` can be replaced, so tests run without the internet.

    With no `fetch`, feeds come from the internet, or from the recordings when
    ASHAWAY_REPLAY=1 is set (an offline demo: weather to 31 July 2023, no FIRMS).
    """
    if fetch is None:
        fetch = ReplayFetch(firms_file=None) if os.environ.get("ASHAWAY_REPLAY") == "1" else feeds.http_get
    client = ai_client or httpx.Client(base_url=ai_url or default_url("ai"), timeout=AI_TIMEOUT_S)
    places = load_destinations() if destinations is None else destinations
    store = Store(db_path)
    app = FastAPI(title="AshAway orchestrator")
    add_request_tracing(app, SERVICE)

    def assessor(model: RemoteModel) -> Assessor:
        return Assessor(model, places, fetch=fetch, clock=clock, firms_key=firms_key, log_path=log_path)

    def run(request: Request, work: Callable[[Assessor], object]) -> tuple[int, dict]:
        """Run one piece of work; known failures become (status, error) in the shared shape."""
        model = RemoteModel(client, request.state.request_id)
        started = time.perf_counter()
        try:
            result = jsonable_encoder(work(assessor(model)))
        except RequestRejected as rejected:
            return 422, error_body(rejected.code, rejected.message, SERVICE)
        except ModelUnavailable as exc:
            return 503, error_body("ai_unavailable", f"No assessment was made, because {exc}.", SERVICE)
        trace = {"request_id": request.state.request_id, "ai_calls": model.calls,
                 "duration_ms": round(1000 * (time.perf_counter() - started))}
        return 200, {"result": result, "trace": {"orchestrator": trace}}

    @app.get("/health")
    def health():
        try:
            r = client.get("/health")
            ai = {"status": "ok", "model_version": r.json()["model_version"]} if r.status_code == 200 else \
                {"status": "unavailable", "error": f"the AI server answered {r.status_code}"}
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            ai = {"status": "unavailable", "error": f"the AI server could not be reached ({type(exc).__name__})"}
        return {"service": SERVICE, "status": "ok" if ai["status"] == "ok" else "degraded", "ai": ai,
                "requests_served": app.state.requests_served}

    @app.get("/destinations")
    def destinations_list():
        return [{"id": i, "name": n} for i, n in zip(places["id"], places["name"])]

    @app.post("/assess")
    def assess(body: AssessBody, request: Request):
        """Assess, then store the request with its outcome, whatever that outcome is (NFR3)."""
        status, answer = run(request, lambda a: a.assess(
            body.place, body.start, body.end, with_alternatives=body.alternatives).to_dict())
        assessment_id = uuid.uuid4().hex[:12]
        if status == 200:
            result = answer["result"]
            outcome, extra = result["status"], {"level": result["level"], "model_version": result["model_version"]}
        else:
            outcome, extra = ("rejected" if status == 422 else "unavailable"), {}
        store.add(assessment_id, request.state.request_id, body.place.strip()[:100], body.start, body.end,
                  outcome, answer.get("result", answer), **extra)
        return JSONResponse({"id": assessment_id, **answer}, status)

    @app.post("/compare")
    def compare(body: CompareBody, request: Request):
        status, answer = run(request, lambda a: a.compare(body.places, body.start, body.end))
        return JSONResponse(answer, status)

    @app.get("/assessments")
    def recent(limit: int = 20):
        return store.recent(max(1, min(limit, 100)))

    @app.get("/assessments/{assessment_id}")
    def stored(assessment_id: str):
        found = store.get(assessment_id)
        if found is None:
            return JSONResponse(error_body("not_found", "No assessment with this id.", SERVICE), 404)
        return {**found, "feedback": store.feedback_for(assessment_id)}

    @app.post("/assessments/{assessment_id}/feedback", status_code=201)
    def feedback(assessment_id: str, body: FeedbackBody):
        found = store.get(assessment_id)
        if found is None or found["outcome"] not in ("assessed", "insufficient evidence"):
            return JSONResponse(error_body("not_found", "Feedback can only be given on an assessment that was made.", SERVICE), 404)
        store.add_feedback(assessment_id, body.verdict, body.comment)
        return {"saved": True, "assessment_id": assessment_id, "model_version": found["model_version"]}

    return app


def main(argv: list[str] | None = None) -> None:
    """Command line: `ashaway-orchestrator [--host H] [--port P]`."""
    serve(create_app, SERVICE, argv)


if __name__ == "__main__":
    main(sys.argv[1:])
