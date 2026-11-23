import asyncio
import json
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


def test_paper_limits_update_dashboard_state_and_persist(tmp_path, monkeypatch):
    from app.schemas import PaperTradeLimits

    monkeypatch.setattr(audit, "DB_PATH", tmp_path / "limits-audit.db")
    monkeypatch.setattr(main, "PAPER_TRADE_LIMITS_PATH", str(tmp_path / "limits.json"))
    monkeypatch.setattr(main, "UPSTOX_ACCESS_TOKEN", "")
    monkeypatch.setattr(main, "TWELVE_DATA_API_KEY", "")
    monkeypatch.setattr(main, "AI_API_KEY", "")
    audit.init_audit()
    main.state.execution_mode = "PAPER"
    main.state.approval = main._paper_approval(["RELIANCE"], 300)
    response = main.update_paper_trade_limits(PaperTradeLimits(max_open_positions=7, max_trades_per_day=12))
    assert response["persisted"] is True
    assert main.state.max_open_positions == 7
    assert main.state.max_trades_per_day == 12
    assert main.state.approval["max_open_positions"] == 7
    assert main.state.approval["max_trades"] == 12
    with pytest.raises(Exception):
        PaperTradeLimits(max_open_positions=51, max_trades_per_day=12)


def test_paper_gain_exit_setting_persists_and_is_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "DB_PATH", tmp_path / "gain-exit-audit.db")
    monkeypatch.setattr(main, "PAPER_EXIT_SETTINGS_PATH", str(tmp_path / "exit-settings.json"))
    audit.init_audit()
    client = TestClient(main.app)
    main.state.execution_mode = "PAPER"
    main.state.profit_exit_enabled = False
    main.state.profit_exit_target_percent = 8.0
    response = client.get("/api/paper-exit-settings")
    assert response.status_code == 200
    assert response.json()["active"] is False
    assert response.json()["target_percent"] == 8.0

    response = client.post("/api/paper-exit-settings", json={"enabled": True, "target_percent": 6.5})
    assert response.status_code == 200
    assert response.json()["active"] is True
    assert main.state.profit_exit_target_percent == 6.5
    assert json.loads((tmp_path / "exit-settings.json").read_text())["enabled"] is True

    rejected = client.post("/api/paper-exit-settings", json={"enabled": True, "target_percent": 0})
    assert rejected.status_code == 422
    assert main.state.profit_exit_target_percent == 6.5


def test_pending_option_quote_becomes_reviewable_in_semi_mode(monkeypatch):
    from datetime import datetime, timezone

    key = "NSE_FO|option-test"
    candidate = {"candidate_id": "candidate-option", "instrument_token": key,
                 "status": "PENDING_OPTION_QUOTE", "entry": 100.0, "stop_loss": 70.0,
                 "target": 160.0, "symbol": "TEST 100 CE", "rationale": "test",
                 "evidence": {"strategy": "ema_8_21_crossover"}}
    main.state.option_contracts[key] = {"lot_size": 1}
    main.state.operating_mode = "SEMI"
    main.state.execution_mode = "PAPER"
    monkeypatch.setattr(main, "autonomous_block", lambda *_args: None)
    monkeypatch.setattr(main, "upsert_candidate", lambda *_args: None)
    main._submit_pending_option_candidate(candidate, {
        "ltp": 102.0, "received_at": datetime.now(timezone.utc).isoformat(),
        "source": "Upstox V3 WebSocket",
    })
    assert candidate["status"] == "PENDING"
    assert candidate["entry"] == 102.0
    assert candidate["decision_reason"] == "Fresh streamed option quote received; ready for human review."


def test_pending_option_without_quote_expires_and_releases_subscription(monkeypatch):
    from datetime import datetime, timedelta, timezone

    key = "NSE_FO|never-quoted"
    candidate_id = "candidate-no-option-quote"
    main.state.candidates.clear()
    main.state.candidates[candidate_id] = {
        "candidate_id": candidate_id, "instrument_token": key,
        "status": "PENDING_OPTION_QUOTE",
        "created_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
    }
    released = []
    monkeypatch.setattr(main, "record_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main, "upsert_candidate", lambda *_args: None)
    monkeypatch.setattr(main, "_release_option_key", released.append)
    assert main.expire_pending_candidates() == 1
    assert main.state.candidates[candidate_id]["status"] == "EXPIRED"
    assert released == [key]


def test_unaffordable_option_lot_releases_subscription(monkeypatch):
    from datetime import datetime, timezone

    key = "NSE_FO|too-expensive"
    candidate = {"candidate_id": "candidate-too-expensive", "instrument_token": key,
                 "status": "PENDING_OPTION_QUOTE", "entry": 100.0, "stop_loss": 70.0,
                 "target": 160.0, "symbol": "TEST 100 CE", "rationale": "test",
                 "confidence": 70, "evidence": {"strategy": "ema_8_21_crossover"}}
    main.state.option_contracts[key] = {"lot_size": 1000}
    main.state.operating_mode = "FULL"
    main.state.execution_mode = "PAPER"
    main.state.autonomous_mode = True
    main.state.bot_enabled = True
    main.state.kill_switch = False
    main.state.autonomous_daily_loss_limit = 300
    main.state.max_trades_per_day = 15
    released = []
    monkeypatch.setattr(main, "readiness", lambda: {"ready": True})
    monkeypatch.setattr(main, "autonomous_block", lambda *_args: None)
    monkeypatch.setattr(main, "upsert_candidate", lambda *_args: None)
    monkeypatch.setattr(main, "record_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main, "_release_option_key", released.append)
    main._submit_pending_option_candidate(candidate, {
        "ltp": 100.0, "received_at": datetime.now(timezone.utc).isoformat(),
        "source": "Upstox V3 WebSocket",
    })
    assert candidate["status"] == "AUTO_REJECTED"
    assert released == [key]


def test_account_exposes_current_capital_from_saved_realised_and_open_pnl(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    from app.strategy_learning import record_outcome

    monkeypatch.setattr(audit, "DB_PATH", tmp_path / "capital-audit.db")
    monkeypatch.setattr(main, "PAPER_LEARNING_STORE_PATH", str(tmp_path / "learning.json"))
    monkeypatch.setattr(main, "UPSTOX_ACCESS_TOKEN", "")
    monkeypatch.setattr(main, "TWELVE_DATA_API_KEY", "")
    monkeypatch.setattr(main, "AI_API_KEY", "")
    audit.init_audit()
    record_outcome(str(tmp_path / "learning.json"), {
        "signal_id": "closed-capital-trade", "status": "CLOSED", "currency": "INR",
        "entry": 100, "stop_loss": 90, "quantity": 1, "actual_exit": 80,
        "net_pnl": -20, "evidence": {"strategy": "test", "asset_class": "equity"},
    })
    main.state.orders.clear()
    main.state.orders.append({"signal_id": "open-capital-trade", "status": "OPEN", "currency": "INR",
                              "instrument_token": "NSE_EQ|CAPITAL", "side": "BUY", "quantity": 2,
                              "entry": 100, "actual_entry": 100})
    main.state.ticks["NSE_EQ|CAPITAL"] = {"ltp": 105, "received_at": datetime.now(timezone.utc).isoformat()}
    main.state.daily_realised_pnl = 0
    main.state.daily_date = datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()
    response = main.account()
    assert response["current_capital"] == pytest.approx(9989.48)
    assert response["cumulative_realised_pnl"] == -20
    # Open P&L is net of the modeled paper exit costs, matching current capital.
    assert response["unrealised_pnl"] == pytest.approx(9.48)


def test_orders_show_actual_prices_symbol_and_mark_to_market_pnl(tmp_path, monkeypatch):
    from datetime import datetime, timezone

    monkeypatch.setattr(audit, "DB_PATH", tmp_path / "orders-history.db")
    audit.init_audit()
    monkeypatch.setattr(main, "UPSTOX_SYMBOL_BY_KEY", {"NSE_EQ|CAPITAL": "ACME"})
    main.state.orders[:] = [
        {"signal_id": "closed-order", "status": "CLOSED", "currency": "INR", "side": "BUY",
         "instrument_token": "NSE_EQ|CAPITAL", "symbol": "CAPITAL", "quantity": 2,
         "entry": 100, "actual_entry": 101, "actual_exit": 111, "net_pnl": 20},
        {"signal_id": "open-order", "status": "OPEN", "currency": "INR", "side": "BUY",
         "instrument_token": "NSE_EQ|CAPITAL", "symbol": "CAPITAL", "quantity": 2,
         "entry": 100, "actual_entry": 100},
    ]
    main.state.ticks["NSE_EQ|CAPITAL"] = {"ltp": 103, "received_at": datetime.now(timezone.utc).isoformat()}
    rows = main.orders()
    assert rows[0]["symbol"] == "ACME"
    assert rows[0]["actual_entry"] == 101
    assert rows[0]["display_exit_price"] == 111
    assert rows[0]["display_pnl"] == 20
    assert rows[1]["display_exit_price"] == pytest.approx(102.897)
    assert rows[1]["display_pnl"] == pytest.approx(5.49)


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
    # Paper exits model adverse slippage and estimated charges against the quote.
    assert trade["actual_exit"] == pytest.approx(110.889)
    assert trade["gross_pnl"] == pytest.approx(19.78)
    assert trade["net_pnl"] == pytest.approx(19.45)
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
    assert accepted.json()["risk_rupees"] == pytest.approx(2.1)
    index_payload = {**payload, "signal_id": "paper-index-0001", "symbol": "Nifty 50",
                     "instrument_token": "NSE_INDEX|Nifty 50"}
    rejected = client.post("/api/orders/paper", json=index_payload)
    assert rejected.status_code == 400
    assert "NSE_EQ" in rejected.json()["detail"]


def test_full_autonomy_is_blocked_for_default_index_only_subscription(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "DB_PATH", tmp_path / "index-autonomy-audit.db")
    monkeypatch.setattr(main, "UPSTOX_INSTRUMENT_KEYS", ["NSE_INDEX|Nifty 50", "NSE_INDEX|Nifty Bank"])
    monkeypatch.setattr(main, "UPSTOX_OPTION_UNDERLYING_KEYS", [])
    monkeypatch.setattr(main, "configured_instruments", lambda: [])
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
    monkeypatch.setattr(main, "_in_indian_cash_session", lambda _now: True)
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
    assert order["actual_exit"] == pytest.approx(96.903)
    assert order["realised_pnl"] == pytest.approx(-6.47)
    assert main.state.daily_realised_pnl == pytest.approx(-6.47)
    assert any(event["event_type"] == "PAPER_TRADE_CLOSED" for event in audit.list_events(20))


def test_optional_gain_exit_obeys_toggle_and_user_threshold(monkeypatch):
    from datetime import datetime, timezone

    closed_reasons = []
    order = {"signal_id": "gain-exit-order-1", "instrument_token": "NSE_EQ|TEST",
             "status": "OPEN", "side": "BUY", "entry": 100.0, "actual_entry": 100.0,
             "stop_loss": 50.0, "target": 200.0, "actual_stop_loss": 50.0,
             "actual_target": 200.0, "quantity": 100, "allocated_capital": 10000.0,
             "entry_charges": 0.0, "created_at": datetime.now(timezone.utc).isoformat(),
             "asset_class": "equity", "currency": "INR"}
    monkeypatch.setattr(main, "_in_indian_cash_session", lambda now: True)
    monkeypatch.setattr(main, "_close_paper_position",
                        lambda current, tick, reason, **kwargs: closed_reasons.append(reason))
    monkeypatch.setattr(main, "_submit_profit_reentry_if_viable", lambda *args: False)
    now = datetime.now(timezone.utc)
    tick = {"ltp": 120.0, "bid": 120.0, "ask": 120.0}

    main.state.profit_exit_enabled = False
    main.state.profit_exit_target_percent = 8.0
    monkeypatch.setattr(main.state, "orders", [order])
    main._manage_paper_exits("NSE_EQ|TEST", tick, now)
    assert closed_reasons == []

    main.state.profit_exit_enabled = True
    main.state.profit_exit_target_percent = 20.0
    main._manage_paper_exits("NSE_EQ|TEST", tick, now)
    assert closed_reasons == []

    main.state.profit_exit_target_percent = 5.0
    main._manage_paper_exits("NSE_EQ|TEST", tick, now)
    assert closed_reasons == ["5% net-profit target reached after estimated costs"]


def test_optional_gain_exit_does_not_override_stop_or_strategy_target(monkeypatch):
    from datetime import datetime, timezone

    main.state.profit_exit_enabled = True
    main.state.profit_exit_target_percent = 1.0
    monkeypatch.setattr(main, "_in_indian_cash_session", lambda _now: True)
    closed = []
    monkeypatch.setattr(main, "_close_paper_position",
                        lambda order, _tick, reason, **_kwargs: closed.append((order, reason)))
    order = {"signal_id": "stop-priority", "instrument_token": "NSE_EQ|TEST",
             "status": "OPEN", "side": "BUY", "entry": 100.0, "actual_entry": 100.0,
             "stop_loss": 98.0, "actual_stop_loss": 98.0,
             "target": 104.0, "actual_target": 104.0, "quantity": 100,
             "allocated_capital": 10000.0, "created_at": datetime.now(timezone.utc).isoformat(),
             "asset_class": "equity", "currency": "INR"}
    main.state.orders[:] = [order]

    main._manage_paper_exits("NSE_EQ|TEST", {"ltp": 97.0}, datetime.now(timezone.utc))

    assert len(closed) == 1
    assert "stop-loss" in closed[0][1].lower()
    assert order["actual_stop_loss"] == 98.0
    assert order["actual_target"] == 104.0


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
    monkeypatch.setattr(main.state, "max_risk_per_trade", 50.0)
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

    assert candidate["status"] == "AUTO_EXECUTED", candidate.get("decision_reason")
    assert len(main.state.orders) == 1
    assert main.state.orders[0]["mode"] == "PAPER"
    assert main.state.orders[0]["quantity"] == 23
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
    monkeypatch.setattr(main.state, "max_risk_per_trade", 50.0)
    main.state.ticks = {"NSE_EQ|INE000TEST000": {
        "ltp": 100.0, "received_at": datetime.now(timezone.utc).isoformat()
    }}
    payload = {"candidate_id": "suggestion-0001", "symbol": "INE000TEST000",
               "instrument_token": "NSE_EQ|INE000TEST000", "side": "BUY",
               "entry": 100, "stop_loss": 98, "target": 104,
               "confidence": 70, "rationale": "Test-only rule signal",
               "strategy_version": "paper-rules-v1"}
    client = TestClient(main.app)
    created = client.post("/api/candidates", json=payload)
    approved = client.post("/api/candidates/suggestion-0001/decision",
                          json={"decision": "APPROVED", "reason": "test approval"})
    assert created.status_code == 200
    assert approved.status_code == 200
    assert approved.json()["status"] == "EXECUTED_PAPER", approved.json().get("decision_reason")
    assert len(main.state.orders) == 1
    assert main.state.orders[0]["mode"] == "PAPER"
    assert main.state.orders[0]["quantity"] == 23


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

