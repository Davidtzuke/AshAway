"""The interface server's storage: one SQLite file (Task 6, T20).

Every request is kept with its outcome, so the team can see what was asked and
what AshAway answered (NFR3). Nothing about the traveller is stored: no name,
account, IP address or browser details (NFR7).
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS assessments (
    id            TEXT PRIMARY KEY,
    created_at    TEXT NOT NULL,
    request_id    TEXT NOT NULL,
    destination   TEXT NOT NULL,
    start_date    TEXT NOT NULL,
    end_date      TEXT NOT NULL,
    outcome       TEXT NOT NULL,  -- assessed, insufficient evidence, rejected, unavailable
    level         TEXT,
    model_version TEXT,
    detail        TEXT NOT NULL   -- the full answer, or the error, as JSON
);
CREATE TABLE IF NOT EXISTS feedback (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    assessment_id TEXT NOT NULL REFERENCES assessments(id),
    created_at    TEXT NOT NULL,
    verdict       TEXT NOT NULL,
    comment       TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db, db:
            db.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    def add(self, assessment_id: str, request_id: str, destination: str, start: str, end: str,
            outcome: str, detail: dict, level: str | None = None, model_version: str | None = None) -> None:
        with closing(self._connect()) as db, db:
            db.execute(
                "INSERT INTO assessments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (assessment_id, _now(), request_id, destination, start, end, outcome, level, model_version, json.dumps(detail)),
            )

    def get(self, assessment_id: str) -> dict | None:
        with closing(self._connect()) as db:
            row = db.execute("SELECT * FROM assessments WHERE id = ?", (assessment_id,)).fetchone()
        if row is None:
            return None
        out = dict(row)
        out["detail"] = json.loads(out["detail"])
        return out

    def recent(self, limit: int = 20) -> list[dict]:
        with closing(self._connect()) as db:
            rows = db.execute(
                "SELECT id, created_at, destination, start_date, end_date, outcome, level, model_version "
                "FROM assessments ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def add_feedback(self, assessment_id: str, verdict: str, comment: str | None) -> None:
        with closing(self._connect()) as db, db:
            db.execute("INSERT INTO feedback (assessment_id, created_at, verdict, comment) VALUES (?, ?, ?, ?)",
                       (assessment_id, _now(), verdict, comment))

    def feedback_for(self, assessment_id: str) -> list[dict]:
        with closing(self._connect()) as db:
            rows = db.execute("SELECT verdict, comment, created_at FROM feedback WHERE assessment_id = ? ORDER BY id",
                              (assessment_id,)).fetchall()
        return [dict(r) for r in rows]
