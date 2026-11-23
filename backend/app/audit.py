"""Append-only SQLite audit ledger with a SHA-256 hash chain."""
from __future__ import annotations
import hashlib, json, os, sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(os.getenv("AUDIT_DB_PATH", "./data/audit.db"))
GENESIS = "0" * 64


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_audit():
    with _connect() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS audit_events (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL UNIQUE,
            occurred_at TEXT NOT NULL,
            event_type TEXT NOT NULL,
            actor TEXT NOT NULL,
            entity_id TEXT,
            payload_json TEXT NOT NULL,
            previous_hash TEXT NOT NULL,
            event_hash TEXT NOT NULL UNIQUE
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_events(occurred_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_events(entity_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_audit_type_seq ON audit_events(event_type, seq)")
        c.execute("""CREATE TRIGGER IF NOT EXISTS audit_no_update
            BEFORE UPDATE ON audit_events BEGIN SELECT RAISE(ABORT, 'audit ledger is append-only'); END""")
        c.execute("""CREATE TRIGGER IF NOT EXISTS audit_no_delete
            BEFORE DELETE ON audit_events BEGIN SELECT RAISE(ABORT, 'audit ledger is append-only'); END""")


def record_event(event_type: str, payload: dict | list | str | None = None,
                 actor: str = "system", entity_id: str | None = None) -> dict:
    import uuid
    init_audit()
    occurred = datetime.now(timezone.utc).isoformat()
    event_id = str(uuid.uuid4())
    payload_json = json.dumps(payload or {}, sort_keys=True, separators=(",", ":"), default=str)
    with _connect() as c:
        c.execute("BEGIN IMMEDIATE")
        row = c.execute("SELECT event_hash FROM audit_events ORDER BY seq DESC LIMIT 1").fetchone()
        previous = row["event_hash"] if row else GENESIS
        canonical = "|".join((event_id, occurred, event_type, actor, entity_id or "", payload_json, previous))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        c.execute("""INSERT INTO audit_events
            (event_id, occurred_at, event_type, actor, entity_id, payload_json, previous_hash, event_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (event_id, occurred, event_type, actor, entity_id, payload_json, previous, digest))
        c.commit()
    return {"event_id": event_id, "occurred_at": occurred, "event_hash": digest}


def list_events(limit: int = 100, before_seq: int | None = None):
    init_audit()
    with _connect() as c:
        if before_seq is None:
            rows = c.execute("SELECT * FROM audit_events ORDER BY seq DESC LIMIT ?", (limit,)).fetchall()
        else:
            rows = c.execute("SELECT * FROM audit_events WHERE seq < ? ORDER BY seq DESC LIMIT ?", (before_seq, limit)).fetchall()
    out=[]
    for r in rows:
        d=dict(r); d["payload"] = json.loads(d.pop("payload_json")); out.append(d)
    return out


def list_events_by_type(event_types: list[str], limit: int = 100000):
    """Read ordered lifecycle records for durable trade and candidate history."""
    types = list(dict.fromkeys(str(value) for value in event_types if value))
    if not types:
        return []
    init_audit()
    placeholders = ",".join("?" for _ in types)
    bounded_limit = max(1, min(int(limit), 250000))
    with _connect() as c:
        rows = c.execute(
            f"SELECT * FROM audit_events WHERE event_type IN ({placeholders}) ORDER BY seq DESC LIMIT ?",
            (*types, bounded_limit),
        ).fetchall()
    out = []
    for row in reversed(rows):
        item = dict(row)
        item["payload"] = json.loads(item.pop("payload_json"))
        out.append(item)
    return out


def verify_chain():
    init_audit()
    previous = GENESIS
    count = 0
    with _connect() as c:
        rows = c.execute("SELECT * FROM audit_events ORDER BY seq ASC").fetchall()
    for r in rows:
        canonical = "|".join((r["event_id"], r["occurred_at"], r["event_type"], r["actor"], r["entity_id"] or "", r["payload_json"], previous))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        if r["previous_hash"] != previous or r["event_hash"] != digest:
            return {"valid": False, "verified_events": count, "failed_seq": r["seq"]}
        previous = digest; count += 1
    return {"valid": True, "verified_events": count, "head_hash": previous}


def audit_health():
    try:
        init_audit()
        with _connect() as c:
            result = c.execute("PRAGMA quick_check").fetchone()[0]
            c.execute("SELECT 1 FROM audit_events LIMIT 1").fetchone()
        return {"available": result == "ok", "quick_check": result}
    except Exception as exc:
        return {"available": False, "error": str(exc)}
