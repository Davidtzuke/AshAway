"""AI inference server: the only process that loads the model (Task 6, T18).

    ashaway-ai --port 8002

It knows nothing about places, dates or feeds. It takes feature rows and gives
back calibrated fire probabilities and, if asked, each feature's contribution.
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

import pandas as pd
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..model.bundle import DEFAULT_BUNDLE_DIR, ModelBundle, load_bundle
from . import add_request_tracing, error_body, serve

SERVICE = "ai"
MAX_ROWS = 1000


class PredictRequest(BaseModel):
    rows: list[dict[str, float]] = Field(min_length=1, max_length=MAX_ROWS)
    explain: bool = False


def bundle_dir() -> Path:
    """ASHAWAY_BUNDLE if set, else models/live-v1 here, else the one in the repository."""
    if "ASHAWAY_BUNDLE" in os.environ:
        return Path(os.environ["ASHAWAY_BUNDLE"])
    if DEFAULT_BUNDLE_DIR.exists():
        return DEFAULT_BUNDLE_DIR
    return Path(__file__).resolve().parents[3] / DEFAULT_BUNDLE_DIR


def create_app(bundle: ModelBundle | None = None) -> FastAPI:
    bundle = bundle or load_bundle(bundle_dir())
    app = FastAPI(title="AshAway AI inference", version=bundle.version)
    add_request_tracing(app, SERVICE)

    @app.get("/health")
    def health():
        return {"service": SERVICE, "status": "ok", "model_version": bundle.version,
                "requests_served": app.state.requests_served}

    @app.get("/model")
    def model():
        """What a caller needs to use the model: its inputs and its risk cut-offs."""
        return {"version": bundle.version, "features": bundle.features,
                "medium_from": bundle.medium_from, "high_from": bundle.high_from}

    @app.post("/predict")
    def predict(body: PredictRequest):
        for i, row in enumerate(body.rows):
            missing = [f for f in bundle.features if f not in row]
            if missing:
                return JSONResponse(error_body("missing_features", f"Row {i} lacks {', '.join(missing)}.", SERVICE), 422)
            bad = [f for f in bundle.features if not math.isfinite(row[f])]
            if bad:
                # A gap must be handled before the model, never guessed here (NFR5).
                return JSONResponse(error_body("not_finite", f"Row {i} has no usable value for {', '.join(bad)}.", SERVICE), 422)
        frame = pd.DataFrame(body.rows)[bundle.features]
        out = {"model_version": bundle.version, "probabilities": [float(p) for p in bundle.predict(frame)]}
        if body.explain:
            out["contributions"] = bundle.contributions(frame).astype(float).to_dict(orient="records")
        return out

    return app


def main(argv: list[str] | None = None) -> None:
    serve(create_app, SERVICE, argv)


if __name__ == "__main__":
    main(sys.argv[1:])
