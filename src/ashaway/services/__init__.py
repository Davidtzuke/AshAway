"""AshAway as three logical servers (Task 6).

    interface     :8000  takes requests from travellers, checks them, stores them
    orchestrator  :8001  gathers evidence and coordinates the work
    ai            :8002  the only process that loads the model

A request always travels interface -> orchestrator -> ai and back. The interface
has no address for the AI server, so it cannot skip the orchestrator.

This module holds what all three share. It must stay light: the interface
imports it, and the interface never loads the model or pandas.
"""
from __future__ import annotations

import argparse
import logging
import os
import time
import uuid
from typing import Callable

REQUEST_ID = "X-Request-ID"
DEFAULT_PORTS = {"interface": 8000, "orchestrator": 8001, "ai": 8002}


def default_url(service: str) -> str:
    """Where a service is found, from ASHAWAY_<NAME>_URL or the local default."""
    return os.environ.get(f"ASHAWAY_{service.upper()}_URL", f"http://127.0.0.1:{DEFAULT_PORTS[service]}")


def error_body(code: str, message: str, service: str) -> dict:
    """One error shape for every server, so a client can always read `error.code`."""
    return {"error": {"code": code, "message": message, "service": service}}


def add_request_tracing(app, service: str) -> None:
    """Give every request an id, pass it back in the response, and log one line per request.

    A caller's X-Request-ID is reused, so one traveller's request can be followed
    through all three servers' logs. Health checks are not counted.
    """
    log = logging.getLogger(f"ashaway.{service}")
    app.state.requests_served = 0

    @app.middleware("http")
    async def trace(request, call_next):
        request_id = request.headers.get(REQUEST_ID) or uuid.uuid4().hex[:12]
        request.state.request_id = request_id
        started = time.perf_counter()
        response = await call_next(request)
        if request.url.path != "/health":
            app.state.requests_served += 1
        response.headers[REQUEST_ID] = request_id
        log.info("%s %s %s -> %s in %.0f ms", request_id, request.method, request.url.path,
                 response.status_code, 1000 * (time.perf_counter() - started))
        return response


def serve(make_app: Callable, service: str, argv: list[str] | None = None) -> None:
    """Command-line entry point shared by the three servers."""
    import uvicorn

    ap = argparse.ArgumentParser(prog=f"ashaway-{service}", description=f"Run the AshAway {service} server.")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=DEFAULT_PORTS[service])
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format=f"%(asctime)s [{service}] %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # our own line per request is enough
    uvicorn.run(make_app(), host=args.host, port=args.port, log_level="warning", access_log=False)
