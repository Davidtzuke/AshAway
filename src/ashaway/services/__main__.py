"""Start all three servers as separate processes on one machine (Task 6, T22).

    python -m ashaway.services            # AI :8002, orchestrator :8001, interface :8000

Each server is its own operating-system process. They find each other only
through the URLs given here. Press Ctrl+C to stop all three.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

import httpx

from . import DEFAULT_PORTS

ORDER = ["ai", "orchestrator", "interface"]  # each server needs the one before it


def wait_until_up(url: str, process: subprocess.Popen, seconds: float = 60) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline and process.poll() is None:
        try:
            if httpx.get(f"{url}/health", timeout=2).status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(0.3)
    return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ashaway.services", description="Start the three AshAway servers.")
    ap.add_argument("--replay", action="store_true",
                    help="use recorded 2023 weather instead of the internet (dates up to 31 July 2023; no FIRMS)")
    args = ap.parse_args(argv)
    urls = {s: f"http://127.0.0.1:{DEFAULT_PORTS[s]}" for s in ORDER}
    env = {**os.environ, "ASHAWAY_AI_URL": urls["ai"], "ASHAWAY_ORCHESTRATOR_URL": urls["orchestrator"]}
    if args.replay:
        env["ASHAWAY_REPLAY"] = "1"
        print("Replay mode: recorded 2023 weather, no internet needed. Try Rhodes, 18 to 24 July 2023.\n")
    processes = []
    try:
        for service in ORDER:
            cmd = [sys.executable, "-m", f"ashaway.services.{service}", "--port", str(DEFAULT_PORTS[service])]
            processes.append(subprocess.Popen(cmd, env=env))
            if not wait_until_up(urls[service], processes[-1]):
                print(f"The {service} server did not start. See the messages above.", file=sys.stderr)
                return 1
            print(f"{service:<13} running at {urls[service]}  (process {processes[-1].pid})")
        print(f"\nOpen {urls['interface']} in a browser. Press Ctrl+C to stop all three servers.\n")
        while all(p.poll() is None for p in processes):
            time.sleep(0.5)
        print("A server stopped unexpectedly, so the others are stopped too.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        for p in reversed(processes):
            p.terminate()
        for p in processes:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()


if __name__ == "__main__":
    sys.exit(main())
