import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import pytest
from fastapi import HTTPException

from fastapi.testclient import TestClient
import app.audit as audit
import app.main as main
from app.state import RuntimeState


def test_kill_switch_defaults_released_and_daily_rollover_preserves_its_state():
    runtime = RuntimeState()
    assert runtime.kill_switch is False
    runtime.daily_date = "2000-01-01"
    runtime.kill_switch = True
    runtime.reset_daily_counters_if_needed()
    assert runtime.kill_switch is True
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


def test_paper_order_accepts_only_configured_nse_equity_keys(tmp_path, monkeypatch):
    from datetime import datetime, timezone

    monkeypatch.setattr(audit, "DB_PATH", tmp_path / "paper-order-audit.db")
    monkeypatch.setattr(main, "UPSTOX_INSTRUMENT_KEYS", ["NSE_EQ|INE000TEST000"])
    audit.init_audit()
    main.state.execution_mode = "PAPER"
    main.state.bot_enabled = True
    main.state.kill_switch = False
    main.state.autonomous_mode = False
    main.state.approval = None
    main.state.orders.clear()
    main.state.daily_realised_pnl = 0.0
    main.state.ticks = {"NSE_EQ|INE000TEST000": {
        "ltp": 100.0, "received_at": datetime.now(timezone.utc).isoformat()
    }}
    client = TestClient(main.app)
    payload = {
        "signal_id": "paper-signal-0001", "symbol": "INE000TEST000",
        "instrument_token": "NSE_EQ|INE000TEST000", "side": "BUY",
        "entry": 100, "stop_loss": 98, "target": 104, "quantity": 1,
    }
    accepted = client.post("/api/orders/paper", json=payload)
    assert accepted.status_code == 200
    assert accepted.json()["mode"] == "PAPER"
    assert accepted.json()["risk_rupees"] == 2
    index_payload = {**payload, "signal_id": "paper-index-0001", "symbol": "Nifty 50",
                     "instrument_token": "NSE_INDEX|Nifty 50"}
    rejected = client.post("/api/orders/paper", json=index_payload)
    assert rejected.status_code == 400
    assert "NSE_EQ" in rejected.json()["detail"]


def test_full_autonomy_is_blocked_for_default_index_only_subscription(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "DB_PATH", tmp_path / "index-autonomy-audit.db")
    monkeypatch.setattr(main, "UPSTOX_INSTRUMENT_KEYS", ["NSE_INDEX|Nifty 50", "NSE_INDEX|Nifty Bank"])
    audit.init_audit()
    main.state.bot_enabled = True
    main.state.kill_switch = False
    client = TestClient(main.app)
    response = client.post("/api/bot/mode", json={"mode": "full", "max_daily_loss": 300})
    assert response.status_code == 409
    assert "NSE_EQ" in response.json()["detail"]
    assert main.state.autonomous_mode is False


def test_automatic_paper_exit_uses_observed_stop_breach_and_audits(tmp_path, monkeypatch):
    from datetime import datetime, timezone

    monkeypatch.setattr(audit, "DB_PATH", tmp_path / "paper-exit-audit.db")
    audit.init_audit()
    main.state.daily_realised_pnl = 0.0
    order = {"signal_id": "paper-exit-0001", "instrument_token": "NSE_EQ|TEST",
             "side": "BUY", "quantity": 2, "entry": 100, "actual_entry": 100,
             "stop_loss": 98, "actual_stop_loss": 98, "target": 104,
             "actual_target": 104, "status": "OPEN", "created_at": datetime.now(timezone.utc).isoformat()}
    main.state.orders.clear()
    main.state.orders.append(order)
    now = datetime.now(timezone.utc)
    main._manage_paper_exits("NSE_EQ|TEST", {"ltp": 97.0}, now)
    assert order["status"] == "CLOSED"
    assert order["actual_exit"] == 97.0
    assert order["realised_pnl"] == -6.0
    assert main.state.daily_realised_pnl == -6.0
    assert any(event["event_type"] == "PAPER_TRADE_CLOSED" for event in audit.list_events(20))


def test_autonomous_strategy_candidate_opens_only_a_local_paper_order(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    from app.paper_strategies import Setup

    monkeypatch.setattr(audit, "DB_PATH", tmp_path / "autonomous-paper-audit.db")
    monkeypatch.setattr(main, "UPSTOX_INSTRUMENT_KEYS", ["NSE_EQ|INE000TEST000"])
    monkeypatch.setattr(main, "upsert_candidate", lambda _candidate: None)
    audit.init_audit()
    main.state.execution_mode = "PAPER"
    main.state.bot_enabled = True
    main.state.kill_switch = False
    main.state.operating_mode = "FULL"
    main.state.autonomous_mode = True
    main.state.autonomous_daily_loss_limit = 300
    main.state.daily_loss_baseline = 0
    main.state.daily_loss_lock = False
    main.state.daily_realised_pnl = 0
    main.state.orders.clear()
    main.state.candidates.clear()
    stamp = datetime.now(timezone.utc).isoformat()
    main.state.connected = True
    main.state.last_feed_at = stamp
    main.state.intelligence_updated_at = stamp
    main.state.intelligence_sources = [{"url": "https://example.test/market-data"}]
    main.state.ticks = {"NSE_EQ|INE000TEST000": {"ltp": 100.0, "received_at": stamp}}
    main.state.approval = main._paper_approval(["INE000TEST000"], 300)
    setup = Setup("donchian_20_breakout", "BUY", 100.0, 98.0, 104.0,
                  "Test rule trigger", 70, stamp)

    candidate = main._record_strategy_candidate("NSE_EQ|INE000TEST000", setup,
                                                  main.state.ticks["NSE_EQ|INE000TEST000"])

    assert candidate["status"] == "AUTO_EXECUTED"
    assert len(main.state.orders) == 1
    assert main.state.orders[0]["mode"] == "PAPER"
    assert main.state.orders[0]["quantity"] == 25
    assert audit.verify_chain()["valid"] is True


def test_human_approved_suggestion_submits_risk_checked_paper_order(tmp_path, monkeypatch):
    from datetime import datetime, timezone

    monkeypatch.setattr(audit, "DB_PATH", tmp_path / "approved-suggestion-audit.db")
    monkeypatch.setattr(main, "UPSTOX_INSTRUMENT_KEYS", ["NSE_EQ|INE000TEST000"])
    monkeypatch.setattr(main, "upsert_candidate", lambda _candidate: None)
    audit.init_audit()
    main.state.execution_mode = "PAPER"
    main.state.bot_enabled = True
    main.state.kill_switch = False
    main.state.autonomous_mode = False
    main.state.approval = None
    main.state.orders.clear()
    main.state.candidates.clear()
    main.state.daily_realised_pnl = 0
    main.state.ticks = {"NSE_EQ|INE000TEST000": {
        "ltp": 100.0, "received_at": datetime.now(timezone.utc).isoformat()
    }}
    payload = {"candidate_id": "suggestion-0001", "symbol": "INE000TEST000",
               "instrument_token": "NSE_EQ|INE000TEST000", "side": "BUY",
               "entry": 100, "stop_loss": 98, "target": 104,
               "confidence": 70, "rationale": "Test-only rule signal",
               "strategy_version": "paper-rules-v1"}
    with TestClient(main.app) as client:
        created = client.post("/api/candidates", json=payload)
        approved = client.post("/api/candidates/suggestion-0001/decision",
                              json={"decision": "APPROVED", "reason": "test approval"})
    assert created.status_code == 200
    assert approved.status_code == 200
    assert approved.json()["status"] == "EXECUTED_PAPER"
    assert len(main.state.orders) == 1
    assert main.state.orders[0]["mode"] == "PAPER"


def test_kill_switch_blocks_order_paused_after_initial_gate(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    from app.schemas import Signal

    monkeypatch.setattr(audit, "DB_PATH", tmp_path / "kill-order-race-audit.db")
    monkeypatch.setattr(main, "UPSTOX_INSTRUMENT_KEYS", ["NSE_EQ|INE000TEST000"])
    audit.init_audit()
    main.state.execution_mode = "PAPER"
    main.state.bot_enabled = True
    main.state.kill_switch = False
    main.state.autonomous_mode = False
    main.state.approval = None
    main.state.orders.clear()
    main.state.ticks = {"NSE_EQ|INE000TEST000": {
        "ltp": 100.0, "received_at": datetime.now(timezone.utc).isoformat()
    }}
    intent_started = Event()
    release_intent = Event()
    original_record = main.record_event

    def pause_before_append(event_type, *args, **kwargs):
        if event_type == "PAPER_ORDER_INTENT":
            intent_started.set()
            assert release_intent.wait(3)
        return original_record(event_type, *args, **kwargs)

    monkeypatch.setattr(main, "record_event", pause_before_append)
    signal = Signal(signal_id="paper-race-signal-1", symbol="INE000TEST000",
                    instrument_token="NSE_EQ|INE000TEST000", side="BUY",
                    entry=100, stop_loss=98, target=104, quantity=1)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(main.paper_order, signal)
        assert intent_started.wait(2)
        main.kill()
        release_intent.set()
        with pytest.raises(HTTPException) as rejected:
            future.result(timeout=3)
        assert rejected.value.status_code == 403
    assert main.state.kill_switch is True
    assert main.state.orders == []


def test_kill_switch_blocks_inflight_bot_start(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "DB_PATH", tmp_path / "kill-start-race-audit.db")
    audit.init_audit()
    main.state.bot_enabled = False
    main.state.bot_status = "STOPPED"
    main.state.kill_switch = False
    intent_started = Event()
    release_intent = Event()
    original_record = main.record_event

    def pause_before_start(event_type, *args, **kwargs):
        if event_type == "BOT_START_REQUESTED":
            intent_started.set()
            assert release_intent.wait(3)
        return original_record(event_type, *args, **kwargs)

    monkeypatch.setattr(main, "record_event", pause_before_start)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(main.bot_control, main.BotControl(enabled=True))
        assert intent_started.wait(2)
        main.kill()
        release_intent.set()
        with pytest.raises(HTTPException) as rejected:
            future.result(timeout=3)
        assert rejected.value.status_code == 409
    assert main.state.kill_switch is True
    assert main.state.bot_enabled is False


def test_seen_bar_deduplication_is_bounded(monkeypatch):
    monkeypatch.setattr(main, "_PAPER_SEEN_BAR_LIMIT", 2)
    main._paper_seen_bars.clear()
    main._paper_seen_bar_order.clear()
    assert main._mark_paper_bar_seen(("NSE_EQ|A", "one")) is True
    assert main._mark_paper_bar_seen(("NSE_EQ|A", "one")) is False
    assert main._mark_paper_bar_seen(("NSE_EQ|A", "two")) is True
    assert main._mark_paper_bar_seen(("NSE_EQ|A", "three")) is True
    assert len(main._paper_seen_bars) == 2
    assert main._mark_paper_bar_seen(("NSE_EQ|A", "one")) is True
    main._paper_seen_bars.clear()
    main._paper_seen_bar_order.clear()


def test_disabling_autonomy_blocks_inflight_automated_paper_order(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    from app.schemas import Signal

    monkeypatch.setattr(audit, "DB_PATH", tmp_path / "autonomy-order-race-audit.db")
    monkeypatch.setattr(main, "UPSTOX_INSTRUMENT_KEYS", ["NSE_EQ|INE000TEST000"])
    audit.init_audit()
    main.state.execution_mode = "PAPER"
    main.state.bot_enabled = True
    main.state.kill_switch = False
    main.state.operating_mode = "FULL"
    main.state.autonomous_mode = True
    main.state.autonomous_daily_loss_limit = 300
    main.state.daily_loss_baseline = 0
    main.state.daily_loss_lock = False
    main.state.approval = main._paper_approval(["INE000TEST000"], 300)
    main.state.orders.clear()
    stamp = datetime.now(timezone.utc).isoformat()
    main.state.connected = True
    main.state.last_feed_at = stamp
    main.state.intelligence_updated_at = stamp
    main.state.intelligence_sources = [{"url": "https://example.test/source"}]
    main.state.ticks = {"NSE_EQ|INE000TEST000": {"ltp": 100.0, "received_at": stamp}}
    intent_started = Event()
    release_intent = Event()
    original_record = main.record_event

    def pause_before_append(event_type, *args, **kwargs):
        if event_type == "PAPER_ORDER_INTENT":
            intent_started.set()
            assert release_intent.wait(3)
        return original_record(event_type, *args, **kwargs)

    monkeypatch.setattr(main, "record_event", pause_before_append)
    signal = Signal(signal_id="paper-autonomy-race-1", symbol="INE000TEST000",
                    instrument_token="NSE_EQ|INE000TEST000", side="BUY",
                    entry=100, stop_loss=98, target=104, quantity=1)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(main._submit_paper_order, signal, autonomous_required=True)
        assert intent_started.wait(2)
        main.set_bot_mode(main.BotModeControl(mode="semi"))
        release_intent.set()
        with pytest.raises(HTTPException) as rejected:
            future.result(timeout=3)
        assert rejected.value.status_code == 403
    assert main.state.autonomous_mode is False
    assert main.state.orders == []


def test_stale_feed_is_reported_without_fabricating_paper_exit(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone

    monkeypatch.setattr(audit, "DB_PATH", tmp_path / "stale-position-audit.db")
    audit.init_audit()
    main.state.orders.clear()
    main.state.orders.append({"signal_id": "stale-position-001", "symbol": "TEST",
                              "instrument_token": "NSE_EQ|TEST", "status": "OPEN"})
    main.state.ticks = {"NSE_EQ|TEST": {"ltp": 100,
                         "received_at": (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()}}
    assert main._stale_open_positions() == ["TEST"]
    assert main.state.orders[0]["status"] == "OPEN"
    main.state.orders.clear()
    main.state.ticks.clear()


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
        assert status["paper_strategy_engine"]["mode"] == "paper_only"
        assert status["paper_strategy_engine"]["eligible_equity_instruments"] == 0
        assert "index-only" in status["paper_strategy_engine"]["last_action"]


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

