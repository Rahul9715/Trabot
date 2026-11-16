import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Event

from fastapi.testclient import TestClient
import app.audit as audit
import app.main as main
from app.state import RuntimeState


def test_kill_switch_defaults_released_and_stays_released_after_daily_rollover():
    runtime = RuntimeState()
    assert runtime.kill_switch is False
    runtime.daily_date = "2000-01-01"
    runtime.kill_switch = False
    runtime.reset_daily_counters_if_needed()
    assert runtime.kill_switch is False
    assert runtime.bot_enabled is False


def test_live_mode_acknowledgement_requires_exact_i_agree(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "DB_PATH", tmp_path / "live-mode-audit.db")
    audit.init_audit()
    client = TestClient(main.app)
    main.state.execution_mode = "PAPER"
    rejected = client.post("/api/execution-mode", json={"mode": "LIVE", "confirmation": "I AGREEE"})
    assert rejected.status_code == 400
    assert main.state.execution_mode == "PAPER"
    selected = client.post("/api/execution-mode", json={"mode": "LIVE", "confirmation": "I AGREE"})
    assert selected.status_code == 200
    assert selected.json()["execution_mode"] == "LIVE_SELECTED"
    assert selected.json()["live_orders_enabled"] is False


def test_live_order_route_remains_fail_closed_after_live_mode_selection(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "DB_PATH", tmp_path / "live-order-audit.db")
    audit.init_audit()
    monkeypatch.setattr(main, "LIVE_TRADING_ENABLED", True)
    monkeypatch.setattr(main, "LIVE_TRADING_ACK", "I AGREE")
    monkeypatch.setattr(main, "UPSTOX_MODE", "live")
    client = TestClient(main.app)
    payload = {
        "signal_id": "live-signal-0001", "symbol": "RELIANCE",
        "instrument_token": "NSE_EQ|INE002A01018", "side": "BUY",
        "entry": 1000, "stop_loss": 980, "target": 1060, "quantity": 1,
    }
    response = client.post("/api/orders/live?ack=I%20AGREE", json=payload)
    assert response.status_code == 501
    assert "unimplemented" in response.json()["detail"].lower()


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


def test_kill_switch_remains_responsive_during_slow_research(tmp_path, monkeypatch):
    from app.ai_provider import AIResult

    monkeypatch.setattr(audit, "DB_PATH", tmp_path / "concurrent-audit.db")
    audit.init_audit()
    monkeypatch.setattr(main, "AI_API_KEY", "test-key")
    monkeypatch.setattr(main, "RESEARCH_SEARCH_PROVIDER", "none")
    monkeypatch.setattr(main, "INTELLIGENCE_AUTO_REFRESH", False)
    entered = Event()
    release = Event()

    def slow_research(*_args, **_kwargs):
        entered.set()
        assert release.wait(5), "research test was not released"
        return AIResult("Research done", [], "test", "test-model", False, False), [], False, None

    monkeypatch.setattr(main, "_run_research", slow_research)
    with TestClient(main.app) as client, ThreadPoolExecutor(max_workers=2) as pool:
        research_future = pool.submit(client.post, "/api/research", json={"question": "Assess Indian markets"})
        assert entered.wait(2), "research endpoint did not start"
        kill_response = client.post("/api/kill-switch")
        assert kill_response.status_code == 200
        assert kill_response.json()["kill_switch"] is True
        release.set()
        assert research_future.result(timeout=5).status_code == 200


def test_lifespan_starts_configured_upstox_feed_and_research_worker(monkeypatch):
    monkeypatch.setattr(main, "UPSTOX_ACCESS_TOKEN", "test-token")
    monkeypatch.setattr(main, "UPSTOX_INSTRUMENT_KEYS", ["NSE_INDEX|Nifty 50"])
    monkeypatch.setattr(main, "INTELLIGENCE_AUTO_REFRESH", False)
    started = []
    monkeypatch.setattr(main.feed, "start", lambda keys: started.extend(keys))
    monkeypatch.setattr(main.feed, "stop", lambda: None)
    with TestClient(main.app) as client:
        status = client.get("/api/status").json()
        assert started == ["NSE_INDEX|Nifty 50"]
        assert status["feed_token_configured"] is True
        assert status["feed_instrument_count"] == 1
        assert status["intelligence_auto_refresh"] is False
        assert status["intelligence_refresh_interval_minutes"] >= 5


def test_feed_connection_explains_missing_local_access_token(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "DB_PATH", tmp_path / "feed-config-audit.db")
    audit.init_audit()
    monkeypatch.setattr(main, "UPSTOX_ACCESS_TOKEN", "")
    monkeypatch.setattr(main, "INTELLIGENCE_AUTO_REFRESH", False)
    with TestClient(main.app) as client:
        response = client.post("/api/market/connect", json={})
    assert response.status_code == 409
    assert "UPSTOX_ACCESS_TOKEN" in response.json()["detail"]
    assert "restart FastAPI" in response.json()["detail"]


def test_periodic_intelligence_worker_runs_immediately_and_records_health(monkeypatch):
    monkeypatch.setattr(main, "INTELLIGENCE_AUTO_REFRESH", True)
    completed = Event()
    calls = []

    def fake_refresh(_request):
        calls.append(True)
        completed.set()

    monkeypatch.setattr(main, "refresh_intelligence", fake_refresh)

    async def run_one_iteration():
        task = asyncio.create_task(main._intelligence_worker())
        assert await asyncio.to_thread(completed.wait, 2), "background refresh did not start immediately"
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    asyncio.run(run_one_iteration())
    assert calls == [True]
    assert main.state.intelligence_worker_status == "RUNNING"
    assert main.state.intelligence_worker_last_run


def test_successful_manual_refresh_clears_stale_worker_error(tmp_path, monkeypatch):
    from app.ai_provider import AIResult

    monkeypatch.setattr(audit, "DB_PATH", tmp_path / "manual-refresh-audit.db")
    audit.init_audit()
    monkeypatch.setattr(main, "AI_API_KEY", "test-key")
    monkeypatch.setattr(main, "RESEARCH_SEARCH_PROVIDER", "none")
    monkeypatch.setattr(main, "INTELLIGENCE_AUTO_REFRESH", False)
    main.state.intelligence_worker_error = "previous SearXNG outage"
    result = AIResult("Current intelligence", [], "test", "test-model", False, False)
    monkeypatch.setattr(main, "_run_research", lambda *_args, **_kwargs: (result, [], False, None))
    with TestClient(main.app) as client:
        response = client.post("/api/intelligence/refresh", json={"extra_context": ""})
    assert response.status_code == 200
    assert main.state.intelligence_worker_error is None

