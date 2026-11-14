import json
import sqlite3
from pathlib import Path
import app.audit as audit


def test_hash_chain_and_append_only(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "DB_PATH", tmp_path / "audit.db")
    audit.record_event("TEST_ONE", {"value": 1})
    audit.record_event("TEST_TWO", {"value": 2})
    result = audit.verify_chain()
    assert result["valid"] is True
    assert result["verified_events"] == 2
    with sqlite3.connect(audit.DB_PATH) as c:
        try:
            c.execute("DELETE FROM audit_events WHERE seq=1")
            assert False, "append-only trigger should reject deletes"
        except sqlite3.DatabaseError:
            pass
    assert audit.verify_chain()["valid"] is True


def test_event_payload_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "DB_PATH", tmp_path / "audit.db")
    audit.record_event("TRADE_CANDIDATE_CREATED", {"confidence": 83, "entry": 100}, entity_id="candidate-0001")
    events = audit.list_events(10)
    assert events[0]["payload"]["confidence"] == 83
    assert events[0]["entity_id"] == "candidate-0001"
