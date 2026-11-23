"""I10: the three servers running at once, each on its own port, talking over real HTTP.

Each server runs in its own thread with a real socket, exactly as it would as a
separate process; only the outside world is replayed (recorded feeds, fixed clock).
"""
import socket
import threading
import time

import httpx
import numpy as np
import pytest
import uvicorn

from ashaway.services import ai, interface, orchestrator

from conftest import FIXED_NOW, FIRMS_TEST_KEY, ReplayFetch

RHODES = {"place": "rhodes", "start": "2023-07-18", "end": "2023-07-24"}


class LiveServer:
    def __init__(self, app):
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        self.url = f"http://127.0.0.1:{sock.getsockname()[1]}"
        self.server = uvicorn.Server(uvicorn.Config(app, log_level="warning", lifespan="off"))
        self.thread = threading.Thread(target=self.server.run, kwargs={"sockets": [sock]}, daemon=True)
        self.thread.start()
        deadline = time.monotonic() + 10
        while not self.server.started:
            assert time.monotonic() < deadline, "server did not start"
            time.sleep(0.01)

    def stop(self):
        self.server.should_exit = True
        self.thread.join(5)


def closed_port_url():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    url = f"http://127.0.0.1:{sock.getsockname()[1]}"
    sock.close()  # nothing listens here any more
    return url


@pytest.fixture
def system(bundle, tmp_path):
    """Start AI, orchestrator and interface servers. `ai_up=False` leaves the AI server out."""
    running = []

    def start(ai_up=True, down=()):
        ai_url = closed_port_url()
        if ai_up:
            running.append(LiveServer(ai.create_app(bundle)))
            ai_url = running[-1].url
        orch = LiveServer(orchestrator.create_app(ai_url, fetch=ReplayFetch(down), clock=lambda: FIXED_NOW,
                                                  firms_key=FIRMS_TEST_KEY, log_path=tmp_path / "updates.jsonl"))
        running.append(orch)
        front = LiveServer(interface.create_app(orch.url, db_path=tmp_path / "interface.sqlite3"))
        running.append(front)
        return {"interface": front.url, "orchestrator": orch.url, "ai": ai_url}

    yield start
    for server in reversed(running):
        server.stop()


def served(url):
    return httpx.get(f"{url}/health").json()["requests_served"]


def test_I10_request_travels_interface_orchestrator_ai_and_back(system, make_assessor):
    urls = system()
    r = httpx.post(f"{urls['interface']}/api/assess", json=RHODES, timeout=60)
    assert r.status_code == 200
    body = r.json()
    a = body["assessment"]
    assert (a["status"], a["level"], len(a["days"])) == ("assessed", "high", 7)
    # One request id, followed through all three servers.
    assert body["trace"]["interface"]["request_id"] == body["trace"]["orchestrator"]["request_id"] == r.headers["X-Request-ID"]
    assert body["trace"]["orchestrator"]["ai_calls"] >= 2
    assert served(urls["orchestrator"]) == 1 and served(urls["ai"]) >= 2
    # Same answer as the single-process version tested in Task 5.
    local = make_assessor().assess(RHODES["place"], RHODES["start"], RHODES["end"])
    np.testing.assert_allclose([d["probability"] for d in a["days"]], [d.probability for d in local.days], rtol=0, atol=1e-12)
    # Stored by the interface server.
    stored = httpx.get(f"{urls['interface']}/api/assessments/{body['id']}").json()
    assert (stored["outcome"], stored["level"]) == ("assessed", "high")


def test_I10_bad_request_stops_at_the_interface(system):
    urls = system()
    r = httpx.post(f"{urls['interface']}/api/assess", json={**RHODES, "place": "atlantis"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "unsupported_place"
    assert served(urls["orchestrator"]) == 0 and served(urls["ai"]) == 0


def test_I10_ai_server_down_gives_503_without_a_risk_level(system):
    urls = system(ai_up=False)
    r = httpx.post(f"{urls['interface']}/api/assess", json=RHODES, timeout=60)
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "ai_unavailable"
    assert "assessment" not in r.json()
    assert httpx.get(f"{urls['interface']}/health").json()["orchestrator"] == {"status": "degraded", "ai": "unavailable"}


def test_I10_orchestrator_down_gives_503(system, tmp_path):
    urls = system()
    front = LiveServer(interface.create_app(closed_port_url(), db_path=tmp_path / "alone.sqlite3"))
    try:
        r = httpx.post(f"{front.url}/api/assess", json=RHODES)
        assert r.status_code == 503 and r.json()["error"]["code"] == "orchestrator_unavailable"
    finally:
        front.stop()
    assert served(urls["ai"]) == 0


def test_I10_failed_feed_warning_reaches_the_traveller(system):
    urls = system(down=["weather"])
    body = httpx.post(f"{urls['interface']}/api/assess", json=RHODES, timeout=60).json()
    a = body["assessment"]
    assert (a["status"], a["level"]) == ("insufficient evidence", None)
    assert any("Open-Meteo weather" in w for w in a["warnings"])
    # Only the model's description is fetched; with no weather there is nothing to score.
    assert body["trace"]["orchestrator"]["ai_calls"] == 1


def test_I10_compare_and_feedback_across_the_servers(system):
    urls = system()
    rows = httpx.post(f"{urls['interface']}/api/compare", timeout=60,
                      json={"places": ["rhodes", "chania"], "start": "2023-07-18", "end": "2023-07-24"}).json()["rows"]
    assert [row["destination"] for row in rows] == ["Rhodes", "Chania"]
    assessment_id = httpx.post(f"{urls['interface']}/api/assess", json=RHODES, timeout=60).json()["id"]
    r = httpx.post(f"{urls['interface']}/api/assessments/{assessment_id}/feedback", json={"verdict": "risk_too_high"})
    assert r.status_code == 201 and r.json()["model_version"] == "live-v1"
