"""USD-denominated, local-only paper trading for Twelve Data instruments."""
from __future__ import annotations

import asyncio
import math
import secrets
import threading
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .audit import record_event, audit_health
from .config import (
    PAPER_GLOBAL_DAILY_LOSS_LIMIT_USD,
    PAPER_GLOBAL_MAX_TRADES_PER_DAY,
    PAPER_GLOBAL_MAX_HOLD_MINUTES,
    PAPER_GLOBAL_MAX_RISK_USD,
    PAPER_GLOBAL_STARTING_CAPITAL_USD,
)
from .paper_strategies import MinuteBarBook, evaluate_strategies
from .state import state
from .twelve_data_feed import configured_instruments

NY = ZoneInfo("America/New_York")
_book = MinuteBarBook(session_timezone="America/New_York")
_processed: dict[str, str] = {}
_seen_bars: set[tuple[str, str]] = set()
GLOBAL_ORDER_GATE = threading.RLock()


def is_market_open(instrument: dict, now: datetime, *, for_entry: bool = False) -> bool:
    """Conservative weekday sessions; reject weekends and equity after-hours.

    Twelve Data symbols may represent different venues/contracts. Equities use
    regular NYSE/Nasdaq hours. Spot FX and spot commodity pairs use the common
    Sunday 17:00–Friday 17:00 New York 24/5 window; provider ticks are still
    required, so this does not invent quotes or claim venue-specific schedules.
    """
    local = now.astimezone(NY)
    minute = local.hour * 60 + local.minute
    if instrument.get("asset_class") == "equity":
        start, end = 9 * 60 + 30, 16 * 60 - (10 if for_entry else 0)
        return local.weekday() < 5 and start <= minute < end
    if local.weekday() == 5:
        return False
    if local.weekday() == 6:
        return minute >= 17 * 60
    if local.weekday() == 4:
        return minute < (17 * 60 - (10 if for_entry else 0))
    return True


def global_account() -> dict:
    today = datetime.now(NY).date().isoformat()
    if state.global_daily_date != today:
        state.global_daily_date = today
        state.global_daily_realised_pnl_usd = 0.0
        state.global_daily_loss_baseline_usd = 0.0
        state.global_daily_loss_lock = False
    today_orders = []
    for order in state.orders:
        if order.get("currency") != "USD":
            continue
        try:
            if datetime.fromisoformat(order["created_at"]).astimezone(NY).date().isoformat() == today:
                today_orders.append(order)
        except (KeyError, TypeError, ValueError):
            continue
    open_orders = [o for o in state.orders if o.get("currency") == "USD" and o.get("status") == "OPEN"]
    unrealised = 0.0
    stale_positions = []
    for order in open_orders:
        tick = state.ticks.get(order.get("instrument_token"))
        if tick and _fresh_tick(tick, datetime.now(timezone.utc)):
            direction = 1 if order.get("side") == "BUY" else -1
            unrealised += (float(tick["ltp"]) - float(order.get("actual_entry", order["entry"]))) * int(order["quantity"]) * direction
        else:
            stale_positions.append(str(order.get("symbol", "unknown")))
    daily = state.global_daily_realised_pnl_usd + unrealised
    if daily - state.global_daily_loss_baseline_usd <= -PAPER_GLOBAL_DAILY_LOSS_LIMIT_USD and not state.global_daily_loss_lock:
        state.global_daily_loss_lock = True
        state.global_autonomous_mode = False
        record_event("GLOBAL_DAILY_LOSS_LOCK_TRIGGERED", {
            "daily_pnl_usd": round(daily, 2),
            "baseline_usd": state.global_daily_loss_baseline_usd,
            "limit_usd": PAPER_GLOBAL_DAILY_LOSS_LIMIT_USD,
            "autonomy_revoked": True,
        })
    return {
        "currency": "USD", "starting_capital": PAPER_GLOBAL_STARTING_CAPITAL_USD,
        "realised_pnl": round(state.global_daily_realised_pnl_usd, 2),
        "unrealised_pnl": round(unrealised, 2), "daily_pnl": round(daily, 2),
        "daily_loss_limit": PAPER_GLOBAL_DAILY_LOSS_LIMIT_USD,
        "daily_loss_baseline": round(state.global_daily_loss_baseline_usd, 2),
        "max_risk_per_trade": PAPER_GLOBAL_MAX_RISK_USD,
        "max_trades_per_day": PAPER_GLOBAL_MAX_TRADES_PER_DAY,
        "daily_loss_lock": state.global_daily_loss_lock,
        "open_positions": len(open_orders), "orders_today": len(today_orders),
        "stale_open_positions": stale_positions,
    }


def _manage_position(order: dict, tick: dict, now: datetime) -> None:
    if order.get("status") != "OPEN":
        return
    price = float(tick["ltp"])
    side = order["side"]
    stop = float(order.get("actual_stop_loss", order["stop_loss"]))
    target = float(order.get("actual_target", order["target"]))
    opened = datetime.fromisoformat(order["created_at"])
    reason = None
    if side == "BUY" and price <= stop or side == "SELL" and price >= stop:
        reason = "Automatic stop-loss; exit at observed Twelve Data quote"
    elif side == "BUY" and price >= target or side == "SELL" and price <= target:
        reason = "Automatic target; exit at observed Twelve Data quote"
    elif (now - opened).total_seconds() >= PAPER_GLOBAL_MAX_HOLD_MINUTES * 60:
        reason = "Maximum global paper holding time reached; exit at observed quote"
    if reason:
        direction = 1 if side == "BUY" else -1
        pnl = round((price - float(order.get("actual_entry", order["entry"]))) * int(order["quantity"]) * direction, 2)
        changes = {"actual_exit": price, "gross_pnl": pnl, "charges": 0.0,
                   "net_pnl": pnl, "realised_pnl": pnl, "status": "CLOSED",
                   "exit_reason": reason, "closed_at": datetime.now(timezone.utc).isoformat(),
                   "paper_costs_note": "Commissions, spread, slippage, financing and taxes are not modeled."}
        record_event("GLOBAL_PAPER_TRADE_CLOSED", {"before": order.copy(), "changes": changes}, entity_id=order["signal_id"])
        order.update(changes)
        state.global_daily_realised_pnl_usd += pnl


def _fresh_tick(tick: dict, now: datetime) -> bool:
    try:
        received = datetime.fromisoformat(str(tick["received_at"]))
        if received.tzinfo is None:
            received = received.replace(tzinfo=timezone.utc)
        provider = datetime.fromisoformat(str(tick.get("provider_timestamp", tick["received_at"])))
        if provider.tzinfo is None:
            provider = provider.replace(tzinfo=timezone.utc)
        age = (now - received.astimezone(timezone.utc)).total_seconds()
        provider_age = (now - provider.astimezone(timezone.utc)).total_seconds()
        return 0 <= age <= 10 and 0 <= provider_age <= 30
    except (KeyError, ValueError, TypeError):
        return False


def _create_candidate(instrument: dict, setup, tick: dict) -> dict:
    token = instrument["instrument_token"]
    symbol = instrument["symbol"]
    candidate_id = f"global-paper-{secrets.token_hex(12)}"
    candidate = {
        "candidate_id": candidate_id, "symbol": symbol, "instrument_token": token,
        "asset_class": instrument["asset_class"], "market_region": instrument["market_region"],
        "exchange": tick.get("exchange") or instrument["exchange"], "currency": "USD",
        "side": setup.side, "entry": setup.entry, "stop_loss": setup.stop_loss,
        "target": setup.target, "confidence": setup.score,
        "rationale": setup.rationale + " Rule score is not a win probability.",
        "target_rationale": "Fixed 2R target from the observed one-minute ATR.",
        "stop_loss_rationale": "1.5 times observed one-minute ATR; gaps can exceed the stop.",
        "evidence": {"strategy": setup.strategy, "strategy_version": "paper-rules-v1",
                     "bar_time": setup.bar_time, "quote_time": tick.get("provider_timestamp"),
                     "quote": float(tick["ltp"]), "data_source": "Twelve Data",
                     "interval": "1m bars aggregated from live quote updates",
                     "currency": "USD", "limitations": [
                         "Local paper simulation only", "No provider-plan entitlement guarantee",
                         "No venue holiday calendar", "No fees, spread, slippage or financing model",
                         "FX and spot commodity symbol sessions are approximated as 24/5"]},
        "strategy_version": "paper-rules-v1", "review_1": {}, "review_2": {},
        "status": "PENDING", "created_at": datetime.now(timezone.utc).isoformat(),
    }
    record_event("GLOBAL_TRADE_CANDIDATE_CREATED", candidate, entity_id=candidate_id)
    state.candidates[candidate_id] = candidate
    state.global_strategy_last_action = f"Suggestion created: {setup.strategy} {setup.side} {symbol} (USD)."

    if not (state.bot_enabled and not state.kill_switch and state.execution_mode == "PAPER"
            and state.operating_mode == "FULL" and state.autonomous_mode and state.global_autonomous_mode):
        return candidate
    if state.global_daily_loss_lock:
        candidate.update({"status": "AUTO_REJECTED", "decision_reason": "Global USD daily loss lock is active."})
        return candidate
    if global_account()["orders_today"] >= PAPER_GLOBAL_MAX_TRADES_PER_DAY:
        candidate.update({"status": "AUTO_REJECTED", "decision_reason": "Global USD daily paper trade limit reached."})
        return candidate
    risk_distance = abs(float(setup.entry) - float(setup.stop_loss))
    risk_budget = min(PAPER_GLOBAL_MAX_RISK_USD, PAPER_GLOBAL_DAILY_LOSS_LIMIT_USD / 5)
    notional_cap = PAPER_GLOBAL_STARTING_CAPITAL_USD * 0.2
    quantity = min(math.floor(risk_budget / risk_distance), math.floor(notional_cap / float(setup.entry))) if risk_distance > 0 else 0
    if quantity < 1:
        candidate.update({"status": "AUTO_REJECTED", "decision_reason": "Stop distance or USD notional cap prevents a valid whole-unit paper position."})
        record_event("GLOBAL_AUTO_PAPER_ENTRY_REJECTED", {"candidate_id": candidate_id, "reason": candidate["decision_reason"]}, entity_id=candidate_id)
        return candidate
    tick_age = datetime.now(timezone.utc)
    if not _fresh_tick(tick, tick_age) or not is_market_open(instrument, tick_age, for_entry=True):
        candidate.update({"status": "AUTO_REJECTED", "decision_reason": "Quote became stale or the instrument session closed before paper entry."})
        return candidate
    if not audit_health().get("available"):
        candidate.update({"status": "AUTO_REJECTED", "decision_reason": "Audit ledger is unavailable; paper entry failed closed."})
        return candidate
    order = {
        "signal_id": candidate_id, "symbol": symbol, "instrument_token": token,
        "asset_class": instrument["asset_class"], "market_region": instrument["market_region"],
        "exchange": candidate["exchange"], "currency": "USD", "side": setup.side,
        "entry": float(setup.entry), "stop_loss": float(setup.stop_loss), "target": float(setup.target),
        "quantity": quantity, "product": "D", "rationale": candidate["rationale"],
        "confidence": setup.score, "evidence": candidate["evidence"], "status": "OPEN",
        "mode": "PAPER", "risk_usd": round(risk_distance * quantity, 2),
        "suggested_entry": float(setup.entry), "suggested_stop_loss": float(setup.stop_loss),
        "suggested_target": float(setup.target), "actual_entry": float(tick["ltp"]),
        "actual_stop_loss": float(setup.stop_loss), "actual_target": float(setup.target),
        "actual_exit": None, "realised_pnl": None, "created_at": datetime.now(timezone.utc).isoformat(),
    }
    record_event("GLOBAL_PAPER_ORDER_INTENT", order, entity_id=candidate_id)
    with GLOBAL_ORDER_GATE:
        current_tick = state.ticks.get(token)
        now = datetime.now(timezone.utc)
        if (state.kill_switch or not state.bot_enabled or not state.autonomous_mode
                or not state.global_autonomous_mode or state.operating_mode != "FULL"
                or state.execution_mode != "PAPER"):
            candidate.update({"status": "AUTO_REJECTED", "decision_reason": "Trading permission changed before paper entry."})
            return candidate
        if (not current_tick or not _fresh_tick(current_tick, now)
                or not is_market_open(instrument, now, for_entry=True)
                or abs(float(current_tick["ltp"]) - float(setup.entry)) > float(setup.entry) * 0.0025):
            candidate.update({"status": "AUTO_REJECTED", "decision_reason": "Quote became stale, moved beyond entry tolerance, or session closed before paper entry."})
            return candidate
        current_price = float(current_tick["ltp"])
        if (setup.side == "BUY" and not float(setup.stop_loss) < current_price < float(setup.target)
                or setup.side == "SELL" and not float(setup.target) < current_price < float(setup.stop_loss)):
            candidate.update({"status": "AUTO_REJECTED", "decision_reason": "Latest quote invalidated the stop or target before paper entry."})
            return candidate
        current_unit_risk = abs(current_price - float(setup.stop_loss))
        quantity = min(math.floor(risk_budget / current_unit_risk), math.floor(notional_cap / current_price)) if current_unit_risk > 0 else 0
        if quantity < 1:
            candidate.update({"status": "AUTO_REJECTED", "decision_reason": "Latest quote exceeds the configured USD risk or notional cap."})
            return candidate
        order.update({"quantity": quantity, "risk_usd": round(current_unit_risk * quantity, 2),
                      "actual_entry": current_price})
        if global_account()["daily_loss_lock"] or global_account()["orders_today"] >= PAPER_GLOBAL_MAX_TRADES_PER_DAY:
            candidate.update({"status": "AUTO_REJECTED", "decision_reason": "Global USD daily risk or trade limit reached before paper entry."})
            return candidate
        if any(o.get("status") == "OPEN" and o.get("currency") == "USD" for o in state.orders):
            candidate.update({"status": "AUTO_REJECTED", "decision_reason": "One global USD paper position is already open."})
            return candidate
        state.orders.append(order)
    try:
        record_event("GLOBAL_PAPER_ORDER_ACCEPTED", order, entity_id=candidate_id)
    except Exception:
        with GLOBAL_ORDER_GATE:
            if order in state.orders:
                state.orders.remove(order)
        raise
    candidate.update({"status": "AUTO_EXECUTED", "order_id": candidate_id,
                      "decision_reason": "Automatically submitted to the local USD paper simulator."})
    state.global_strategy_last_action = f"Paper position opened: {setup.side} {symbol}, {quantity} units (USD)."
    return candidate


def submit_approved_candidate(candidate: dict) -> dict:
    """Submit a human-approved global suggestion to the local USD simulator."""
    if state.execution_mode != "PAPER" or not state.bot_enabled or state.kill_switch:
        raise ValueError("Paper execution, a running agent, and a released kill switch are required.")
    if state.operating_mode == "FULL":
        raise ValueError("Manual approval is disabled while full autonomy is selected.")
    instrument = next((row for row in configured_instruments()
                      if row["instrument_token"] == candidate.get("instrument_token")), None)
    if not instrument:
        raise ValueError("The candidate symbol is no longer configured in the Twelve Data paper feed.")
    token = instrument["instrument_token"]
    tick = state.ticks.get(token)
    now = datetime.now(timezone.utc)
    if not tick or not _fresh_tick(tick, now) or not is_market_open(instrument, now, for_entry=True):
        raise ValueError("A fresh in-session Twelve Data quote is required to approve this paper entry.")
    entry, stop, target = (float(candidate[k]) for k in ("entry", "stop_loss", "target"))
    ltp = float(tick["ltp"])
    tolerance = entry * 0.0025
    if abs(ltp - entry) > tolerance:
        raise ValueError("Quote moved more than 0.25% from the suggestion entry; refresh the suggestion.")
    direction = candidate["side"]
    if direction == "BUY" and not stop < ltp < target or direction == "SELL" and not target < ltp < stop:
        raise ValueError("Current quote invalidated the suggested stop or target.")
    unit_risk = abs(ltp - stop)
    quantity = min(math.floor(min(PAPER_GLOBAL_MAX_RISK_USD, PAPER_GLOBAL_DAILY_LOSS_LIMIT_USD / 5) / unit_risk),
                   math.floor(PAPER_GLOBAL_STARTING_CAPITAL_USD * 0.2 / ltp)) if unit_risk > 0 else 0
    if quantity < 1:
        raise ValueError("USD stop-risk and notional limits prevent a whole-unit position.")
    if global_account()["daily_loss_lock"]:
        raise ValueError("Global USD daily loss lock is active.")
    if global_account()["orders_today"] >= PAPER_GLOBAL_MAX_TRADES_PER_DAY:
        raise ValueError("Global USD daily paper trade limit reached.")
    order = {
        "signal_id": candidate["candidate_id"], "symbol": instrument["symbol"],
        "instrument_token": token, "asset_class": instrument["asset_class"],
        "market_region": instrument["market_region"], "exchange": tick.get("exchange") or instrument["exchange"],
        "currency": "USD", "side": direction, "entry": entry, "stop_loss": stop,
        "target": target, "quantity": quantity, "product": "D",
        "rationale": candidate.get("rationale", ""), "confidence": candidate.get("confidence", 0),
        "evidence": candidate.get("evidence", {}), "status": "OPEN", "mode": "PAPER",
        "risk_usd": round(unit_risk * quantity, 2), "suggested_entry": entry,
        "suggested_stop_loss": stop, "suggested_target": target, "actual_entry": ltp,
        "actual_stop_loss": stop, "actual_target": target, "actual_exit": None,
        "realised_pnl": None, "created_at": now.isoformat(),
    }
    record_event("GLOBAL_PAPER_ORDER_INTENT", order, entity_id=candidate["candidate_id"])
    with GLOBAL_ORDER_GATE:
        current_tick = state.ticks.get(token)
        now = datetime.now(timezone.utc)
        if (state.kill_switch or not state.bot_enabled or state.execution_mode != "PAPER"
                or state.operating_mode == "FULL"):
            raise ValueError("Trading permission changed before paper entry.")
        if (not current_tick or not _fresh_tick(current_tick, now)
                or not is_market_open(instrument, now, for_entry=True)
                or abs(float(current_tick["ltp"]) - ltp) > ltp * 0.0025):
            raise ValueError("Quote became stale, moved beyond entry tolerance, or session closed before paper entry.")
        ltp = float(current_tick["ltp"])
        if direction == "BUY" and not stop < ltp < target or direction == "SELL" and not target < ltp < stop:
            raise ValueError("Latest quote invalidated the suggested stop or target before paper entry.")
        unit_risk = abs(ltp - stop)
        quantity = min(math.floor(min(PAPER_GLOBAL_MAX_RISK_USD, PAPER_GLOBAL_DAILY_LOSS_LIMIT_USD / 5) / unit_risk),
                       math.floor(PAPER_GLOBAL_STARTING_CAPITAL_USD * 0.2 / ltp)) if unit_risk > 0 else 0
        if quantity < 1:
            raise ValueError("Latest quote exceeds the configured USD risk or notional cap.")
        order.update({"quantity": quantity, "risk_usd": round(unit_risk * quantity, 2), "actual_entry": ltp})
        if global_account()["daily_loss_lock"] or global_account()["orders_today"] >= PAPER_GLOBAL_MAX_TRADES_PER_DAY:
            raise ValueError("Global USD daily risk or trade limit reached before paper entry.")
        if any(o.get("status") == "OPEN" and o.get("currency") == "USD" for o in state.orders):
            raise ValueError("One global USD paper position is already open.")
        state.orders.append(order)
    try:
        record_event("GLOBAL_PAPER_ORDER_ACCEPTED", order, entity_id=candidate["candidate_id"])
    except Exception:
        with GLOBAL_ORDER_GATE:
            if order in state.orders:
                state.orders.remove(order)
        raise
    return order


async def worker() -> None:
    while True:
        try:
            global_account()  # rolls the separate USD paper day and enforces its loss lock
            instruments = {row["instrument_token"]: row for row in configured_instruments()}
            state.global_strategy_status = "RUNNING" if instruments else "NO_CONFIGURED_SYMBOLS"
            if not instruments:
                state.global_strategy_last_action = "Add opt-in Twelve Data symbols in backend/.env and restart FastAPI."
            elif not any(state.ticks.get(token) for token in instruments) and state.global_strategy_last_scan is None:
                state.global_strategy_last_action = "Global symbols configured; waiting for fresh in-session Twelve Data quotes."
            for token, instrument in instruments.items():
                tick = state.ticks.get(token)
                if not tick:
                    continue
                received = str(tick.get("received_at") or "")
                if not received or _processed.get(token) == received:
                    continue
                _processed[token] = received
                now = datetime.fromisoformat(received).astimezone(timezone.utc)
                if not _fresh_tick(tick, datetime.now(timezone.utc)):
                    state.global_strategy_last_action = f"Ignoring stale or future quote for {instrument['symbol']}."
                    continue
                for order in list(state.orders):
                    if order.get("currency") == "USD" and order.get("instrument_token") == token:
                        _manage_position(order, tick, now)
                if not is_market_open(instrument, now):
                    continue
                bar = _book.add_tick(token, float(tick["ltp"]), now)
                if bar is None:
                    continue
                state.global_strategy_last_scan = datetime.now(timezone.utc).isoformat()
                if not state.bot_enabled or state.kill_switch or state.execution_mode != "PAPER":
                    continue
                if not is_market_open(instrument, now, for_entry=True):
                    state.global_strategy_last_action = f"Outside entry window for {instrument['symbol']}."
                    continue
                if not audit_health().get("available"):
                    state.global_strategy_last_action = "Audit ledger unavailable; global scans are fail-closed."
                    continue
                key = (token, bar.started_at.isoformat())
                if key in _seen_bars:
                    continue
                _seen_bars.add(key)
                bars = _book.bars(token)
                setups = evaluate_strategies(bars)
                if not setups:
                    state.global_strategy_last_action = f"{instrument['symbol']}: no rule triggered ({len(bars)}/30 completed 1m bars)."
                    continue
                setup = max(setups, key=lambda item: item.score)
                offset = float(tick["ltp"]) - setup.entry
                setup = setup.__class__(setup.strategy, setup.side, float(tick["ltp"]),
                                        setup.stop_loss + offset, setup.target + offset,
                                        setup.rationale, setup.score, setup.bar_time)
                _create_candidate(instrument, setup, tick)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            state.global_strategy_status = "ERROR"
            state.global_strategy_error = f"{type(exc).__name__}: {exc}"
        await asyncio.sleep(0.5)
