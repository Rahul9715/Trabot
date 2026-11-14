from fastapi.testclient import TestClient
import app.audit as audit
import app.main as main


def test_candidate_decision_is_audited(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "DB_PATH", tmp_path / "api-audit.db")
    audit.init_audit()
    client = TestClient(main.app)
    payload = {
        "candidate_id": "candidate-0001", "symbol": "RELIANCE",
        "instrument_token": "NSE_EQ|INE002A01018", "side": "BUY",
        "entry": 1000, "stop_loss": 980, "target": 1060,
        "confidence": 82, "rationale": "Test rationale",
        "strategy_version": "test-v1"
    }
    assert client.post("/api/candidates", json=payload).status_code == 200
    decision = client.post("/api/candidates/candidate-0001/decision", json={"decision":"REJECTED", "reason":"Test rejection"})
    assert decision.status_code == 200
    assert decision.json()["status"] == "REJECTED"
    assert audit.verify_chain()["valid"] is True
    types = [e["event_type"] for e in audit.list_events(20)]
    assert "TRADE_CANDIDATE_CREATED" in types
    assert "TRADE_CANDIDATE_DECISION" in types


def test_paper_trade_close_records_actual_exit_and_pnl(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "DB_PATH", tmp_path / "close-audit.db")
    audit.init_audit()
    client = TestClient(main.app)
    main.state.orders.clear()
    main.state.daily_realised_pnl = 0.0
    main.state.orders.append({
        "signal_id": "trade-000001", "symbol": "RELIANCE", "side": "BUY",
        "quantity": 2, "entry": 100, "actual_entry": 101,
        "status": "OPEN", "mode": "PAPER"
    })
    response = client.patch("/api/orders/trade-000001", json={"actual_exit": 111, "charges": 2.5, "exit_reason": "Test target"})
    assert response.status_code == 200
    trade = response.json()
    assert trade["actual_exit"] == 111
    assert trade["gross_pnl"] == 20
    assert trade["net_pnl"] == 17.5
    assert trade["status"] == "CLOSED"
    assert audit.verify_chain()["valid"] is True


def test_daily_loss_reset_keeps_cumulative_pnl_and_does_not_reenable_autonomy(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "DB_PATH", tmp_path / "reset-audit.db")
    audit.init_audit()
    client = TestClient(main.app)
    main.state.daily_realised_pnl = -250.0
    main.state.daily_loss_baseline = 0.0
    main.state.daily_loss_lock = True
    main.state.autonomous_mode = False
    response = client.post("/api/daily-lock/reset", json={})
    assert response.status_code == 200
    body = response.json()
    assert body["reset"] is True
    assert body["cumulative_daily_pnl"] == -250.0
    assert main.state.daily_realised_pnl == -250.0
    assert main.state.daily_loss_baseline == -250.0
    assert main.state.daily_loss_lock is False
    assert main.state.autonomous_mode is False
    assert audit.verify_chain()["valid"] is True
