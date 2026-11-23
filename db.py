"""Робота з базою заявок (SQLite)."""
import sqlite3
from datetime import datetime
from typing import Optional

from config import DB_PATH, STATUSES

_conn: Optional[sqlite3.Connection] = None


def connect() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute(
            """
            CREATE TABLE IF NOT EXISTS leads (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                name           TEXT NOT NULL,
                phone          TEXT NOT NULL,
                service        TEXT NOT NULL,
                preferred_time TEXT,
                comment        TEXT,
                source         TEXT NOT NULL,          -- telegram | website
                tg_user_id     INTEGER,
                tg_username    TEXT,
                status         TEXT NOT NULL DEFAULT 'new',
                created_at     TEXT NOT NULL,
                updated_at     TEXT NOT NULL
            )
            """
        )
        _conn.commit()
    return _conn


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def create_lead(
    *,
    name: str,
    phone: str,
    service: str,
    preferred_time: str = "",
    comment: str = "",
    source: str,
    tg_user_id: Optional[int] = None,
    tg_username: Optional[str] = None,
) -> dict:
    conn = connect()
    now = _now()
    cur = conn.execute(
        """
        INSERT INTO leads (name, phone, service, preferred_time, comment, source,
                           tg_user_id, tg_username, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'new', ?, ?)
        """,
        (name, phone, service, preferred_time, comment, source,
         tg_user_id, tg_username, now, now),
    )
    conn.commit()
    return get_lead(cur.lastrowid)


def get_lead(lead_id: int) -> Optional[dict]:
    row = connect().execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    return dict(row) if row else None


def list_leads(status: Optional[str] = None, limit: int = 200) -> list[dict]:
    conn = connect()
    if status:
        rows = conn.execute(
            "SELECT * FROM leads WHERE status = ? ORDER BY id DESC LIMIT ?", (status, limit)
        )
    else:
        rows = conn.execute("SELECT * FROM leads ORDER BY id DESC LIMIT ?", (limit,))
    return [dict(r) for r in rows]


def set_status(lead_id: int, status: str) -> Optional[dict]:
    if status not in STATUSES:
        raise ValueError(f"Невідомий статус: {status}")
    conn = connect()
    conn.execute(
        "UPDATE leads SET status = ?, updated_at = ? WHERE id = ?", (status, _now(), lead_id)
    )
    conn.commit()
    return get_lead(lead_id)


def stats() -> dict:
    conn = connect()
    counts = {key: 0 for key in STATUSES}
    for row in conn.execute("SELECT status, COUNT(*) AS n FROM leads GROUP BY status"):
        counts[row["status"]] = row["n"]
    today = datetime.now().date().isoformat()
    counts["today"] = conn.execute(
        "SELECT COUNT(*) FROM leads WHERE created_at LIKE ?", (today + "%",)
    ).fetchone()[0]
    counts["total"] = sum(counts[key] for key in STATUSES)
    return counts
