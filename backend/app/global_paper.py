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
    PAPER_GLOBAL_MAX_HOLD_MINUTES,
    PAPER_GLOBAL_MAX_RISK_USD,
    PAPER_GLOBAL_STARTING_CAPITAL_USD,
    GLOBAL_PAPER_WARMUP_STORE_PATH,
    PAPER_LEARNING_STORE_PATH,
    TRABOT_MODEL_DIR,
    INTELLIGENCE_MAX_AGE_MINUTES,
)
from .paper_strategies import MinuteBarBook, Setup, evaluate_strategies
from .state import state
from .twelve_data_feed import configured_instruments
from .strategy_learning import record_outcome, cumulative_realised, summary as strategy_learning_summary, autonomous_block
from .paper_execution import (simulated_market_fill, estimate_execution_cost,
                              round_trip_cost_estimate, opposite_side,
                              allocated_trade_capital, estimated_net_close,
                              projected_net_at_target)
from .exit_settings import active_take_profit_fraction

NY = ZoneInfo("America/New_York")
_book = MinuteBarBook(session_timezone="America/New_York", storage_path=GLOBAL_PAPER_WARMUP_STORE_PATH)
_processed: dict[str, str] = {}
_seen_bars: set[tuple[str, str]] = set()
GLOBAL_ORDER_GATE = threading.RLock()


def _profit_exit_fraction() -> float | None:
    return active_take_profit_fraction({
        "enabled": state.profit_exit_enabled,
        "target_percent": state.profit_exit_target_percent,
    })


def _record_candidate_status(candidate: dict) -> None:
    try:
        record_event("TRADE_CANDIDATE_STATUS_UPDATED", dict(candidate),
                     entity_id=str(candidate.get("candidate_id", "")))
    except Exception as exc:
        state.global_strategy_error = f"Candidate status history could not be saved: {exc}"


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
            mark = float(tick["ltp"])
            exit_fill, _ = simulated_market_fill(opposite_side(str(order.get("side", "BUY"))), tick, currency="USD")
            gross = (exit_fill - float(order.get("actual_entry", order["entry"]))) * int(order["quantity"]) * direction
            unrealised += gross - round_trip_cost_estimate(order, exit_fill)
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
        "current_capital": round(PAPER_GLOBAL_STARTING_CAPITAL_USD + cumulative_realised(PAPER_LEARNING_STORE_PATH, "USD", state.orders) + unrealised, 2),
        "cumulative_realised_pnl": cumulative_realised(PAPER_LEARNING_STORE_PATH, "USD", state.orders),
        "realised_pnl": round(state.global_daily_realised_pnl_usd, 2),
        "unrealised_pnl": round(unrealised, 2), "daily_pnl": round(daily, 2),
        "daily_loss_limit": PAPER_GLOBAL_DAILY_LOSS_LIMIT_USD,
        "daily_loss_baseline": round(state.global_daily_loss_baseline_usd, 2),
        "max_risk_per_trade": PAPER_GLOBAL_MAX_RISK_USD,
        "max_trades_per_day": state.max_trades_per_day,
        "max_open_positions": state.max_open_positions,
        "daily_loss_lock": state.global_daily_loss_lock,
        "open_positions": len(open_orders), "orders_today": len(today_orders),
        "stale_open_positions": stale_positions,
    }


def _manage_position(order: dict, tick: dict, now: datetime, instrument: dict) -> None:
    if order.get("status") != "OPEN":
        return
    price = float(tick["ltp"])
    side = order["side"]
    stop = float(order.get("actual_stop_loss", order["stop_loss"]))
    target = float(order.get("actual_target", order["target"]))
    opened = datetime.fromisoformat(order["created_at"])
    net_mark, _, _, _ = estimated_net_close(order, tick)
    capital_base = float(order.get("allocated_capital") or allocated_trade_capital(order))
    target_fraction = _profit_exit_fraction()
    profit_target_hit = target_fraction is not None and capital_base > 0 and net_mark >= capital_base * target_fraction
    reason = None
    if side == "BUY" and price <= stop or side == "SELL" and price >= stop:
        reason = "Automatic stop-loss; exit at observed Twelve Data quote"
    elif profit_target_hit:
        reason = f"{state.profit_exit_target_percent:g}% net-profit target reached after estimated costs"
    elif side == "BUY" and price >= target or side == "SELL" and price <= target:
        reason = "Automatic target; exit at observed Twelve Data quote"
    elif _two_minutes_before_market_close(instrument, now):
        reason = "Scheduled paper exit two minutes before market close"
    elif (now - opened).total_seconds() >= PAPER_GLOBAL_MAX_HOLD_MINUTES * 60:
        reason = "Maximum global paper holding time reached; exit at observed quote"
    if reason:
        direction = 1 if side == "BUY" else -1
        exit_side = opposite_side(side)
        fill, fill_model = simulated_market_fill(exit_side, tick, currency="USD")
        gross = round((fill - float(order.get("actual_entry", order["entry"]))) * int(order["quantity"]) * direction, 2)
        exit_charges = estimate_execution_cost(fill, int(order["quantity"]), side=exit_side,
                                               asset_class=str(order.get("asset_class", "equity")), currency="USD")
        charges = round(float(order.get("entry_charges", 0) or 0) + exit_charges, 4)
        pnl = round(gross - charges, 2)
        changes = {"actual_exit": fill, "gross_pnl": gross, "exit_charges": exit_charges, "charges": charges,
                   "net_pnl": pnl, "realised_pnl": pnl, "status": "CLOSED",
                   "allocated_capital": capital_base,
                   "net_return_pct": round(pnl / capital_base * 100, 4) if capital_base > 0 else 0.0,
                   "exit_reason": reason, "closed_at": datetime.now(timezone.utc).isoformat(),
                   "exit_fill_model": fill_model,
                   "paper_costs_note": "Estimated spread, slippage and transaction costs; actual broker fills and fees may differ."}
        changes["last_action_at"] = changes["closed_at"]
        record_event("GLOBAL_PAPER_TRADE_CLOSED", {"before": order.copy(), "changes": changes}, entity_id=order["signal_id"])
        order.update(changes)
        state.global_daily_realised_pnl_usd += pnl
        try:
            record_outcome(PAPER_LEARNING_STORE_PATH, order, TRABOT_MODEL_DIR)
        except Exception as exc:
            state.last_error = f"Strategy learning outcome could not be saved: {exc}"
        if profit_target_hit:
            _submit_global_profit_reentry(order, tick, now, instrument)


def _submit_global_profit_reentry(order: dict, tick: dict, now: datetime, instrument: dict) -> None:
    """Create a same-direction re-entry only if the enabled target remains viable."""
    target_fraction = _profit_exit_fraction()
    if target_fraction is None:
        return
    if not state.bot_enabled or state.kill_switch or state.execution_mode != "PAPER":
        return
    account = global_account()
    if (account["daily_loss_lock"] or account["orders_today"] >= state.max_trades_per_day
            or account["open_positions"] >= state.max_open_positions):
        return
    side = str(order.get("side", "BUY")).upper()
    stop = float(order.get("actual_stop_loss", order.get("stop_loss", 0)))
    target = float(order.get("actual_target", order.get("target", 0)))
    entry = float(tick.get("ltp", 0) or 0)
    if entry <= 0 or (side == "BUY" and not stop < entry < target) or (side == "SELL" and not target < entry < stop):
        return
    entry_fill, _ = simulated_market_fill(side, tick, currency="USD")
    unit_risk = abs(entry_fill - stop)
    risk_budget = min(PAPER_GLOBAL_MAX_RISK_USD, PAPER_GLOBAL_STARTING_CAPITAL_USD * 0.05)
    notional_cap = PAPER_GLOBAL_STARTING_CAPITAL_USD * 0.2
    quantity = min(math.floor(risk_budget / unit_risk), math.floor(notional_cap / entry_fill)) if unit_risk > 0 else 0
    if quantity < 1:
        return
    projected_order = {**order, "currency": "USD", "actual_entry": entry_fill,
                       "actual_stop_loss": stop, "entry_charges": 0, "quantity": quantity}
    projected_net, projected_capital = projected_net_at_target(projected_order, tick, target)
    if projected_capital <= 0 or projected_net < projected_capital * target_fraction:
        return
    evidence = dict(order.get("evidence") or {})
    evidence.update({"profit_reentry": True, "profit_reentry_from": order.get("signal_id"),
                     "profit_reentry_cycle": int(order.get("profit_reentry_cycle", 0) or 0) + 1,
                     "net_take_profit_fraction": target_fraction,
                     "net_take_profit_percent": state.profit_exit_target_percent})
    strategy = str(evidence.get("strategy", "paper_strategy"))
    reentry = Setup(
        strategy=strategy, side=side, entry=entry_fill, stop_loss=stop, target=target,
        rationale=f"Fresh global paper re-entry after booking a {state.profit_exit_target_percent:g}% net-profit cycle; remaining strategy target supports another such cycle.",
        score=float(order.get("confidence", 0) or 0), bar_time=now.isoformat(),
        features={**(evidence.get("features") or {}), "profit_reentry": 1.0},
    )
    reentry_candidate = _create_candidate(instrument, reentry, tick)
    if reentry_candidate.get("candidate_id"):
        reentry_candidate.setdefault("evidence", {}).update({
            "profit_reentry_from": order.get("signal_id"),
            "projected_net_pnl_usd": round(projected_net, 2),
            "projected_allocated_capital_usd": round(projected_capital, 2),
            "profit_reentry_cycle": evidence["profit_reentry_cycle"],
        })
        _record_candidate_status(reentry_candidate)


def _two_minutes_before_market_close(instrument: dict, now: datetime) -> bool:
    """Flatten before the regular US equity close or the modeled 24/5 week close."""
    local = now.astimezone(NY)
    minute = local.hour * 60 + local.minute
    if instrument.get("asset_class") == "equity":
        return local.weekday() < 5 and minute >= 16 * 60 - 2
    # FX and spot commodity hours are approximated as Sunday 17:00 to Friday 17:00 NY.
    return local.weekday() == 4 and minute >= 17 * 60 - 2


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


def _global_autonomy_ready(now: datetime) -> bool:
    """Require current source-backed intelligence before global auto entries."""
    if not state.intelligence_updated_at or not state.intelligence_sources:
        return False
    try:
        updated = datetime.fromisoformat(str(state.intelligence_updated_at))
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        age = (now - updated.astimezone(timezone.utc)).total_seconds()
        return 0 <= age <= INTELLIGENCE_MAX_AGE_MINUTES * 60
    except (TypeError, ValueError):
        return False


def _create_candidate_impl(instrument: dict, setup, tick: dict) -> dict:
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
                     "decision_factors": [setup.rationale,
                         f"Completed-bar entry {setup.entry:.6f}; stop distance {abs(setup.entry - setup.stop_loss):.6f}; target distance {abs(setup.target - setup.entry):.6f}.",
                         f"Risk/reward target is {abs(setup.target - setup.entry) / max(abs(setup.entry - setup.stop_loss), 1e-12):.2f}:1; score {setup.score:.0f} is a rule-strength label, not a probability."],
                     "features": setup.features,
                     "historical_strategy_review": next((row for row in strategy_learning_summary(PAPER_LEARNING_STORE_PATH)["strategies"] if row["strategy"] == setup.strategy and row["asset_class"] == instrument["asset_class"]), None),
                     "bar_time": setup.bar_time, "quote_time": tick.get("provider_timestamp"),
                     "quote": float(tick["ltp"]), "data_source": "Twelve Data",
                     "interval": "1m bars aggregated from live quote updates",
                     "currency": "USD", "limitations": [
                         "Local paper simulation only", "No provider-plan entitlement guarantee",
                         "No venue holiday calendar", "Estimated spread, slippage and transaction costs may differ from broker execution",
                         "FX and spot commodity symbol sessions are approximated as 24/5"]},
        "strategy_version": "paper-rules-v1", "review_1": {}, "review_2": {},
        "status": "PENDING", "created_at": datetime.now(timezone.utc).isoformat(),
        "decision_reason": "Setup met the named price rule; pending review or paper-risk checks.",
    }
    record_event("GLOBAL_TRADE_CANDIDATE_CREATED", candidate, entity_id=candidate_id)
    state.candidates[candidate_id] = candidate
    state.global_strategy_last_action = f"Suggestion created: {setup.strategy} {setup.side} {symbol} (USD)."

    if not (state.bot_enabled and not state.kill_switch and state.execution_mode == "PAPER"
            and state.operating_mode == "FULL" and state.autonomous_mode and state.global_autonomous_mode):
        return candidate
    if not _global_autonomy_ready(datetime.now(timezone.utc)):
        candidate.update({"status": "PENDING",
                          "decision_reason": "Autonomy is armed; waiting for fresh source-backed intelligence before any paper entry."})
        return candidate
    if state.global_daily_loss_lock:
        candidate.update({"status": "AUTO_REJECTED", "decision_reason": "Global USD daily loss lock is active."})
        return candidate
    learning_pause = autonomous_block(PAPER_LEARNING_STORE_PATH, setup.strategy, instrument["asset_class"])
    if learning_pause:
        candidate.update({"status": "AUTO_REJECTED", "decision_reason": learning_pause})
        record_event("GLOBAL_PAPER_STRATEGY_LEARNING_GUARD", {"candidate_id": candidate_id, "reason": learning_pause}, entity_id=candidate_id)
        return candidate
    if global_account()["orders_today"] >= state.max_trades_per_day:
        candidate.update({"status": "AUTO_REJECTED", "decision_reason": "Global USD daily paper trade limit reached."})
        return candidate
    if global_account()["open_positions"] >= state.max_open_positions:
        candidate.update({"status": "AUTO_REJECTED", "decision_reason": "Global USD simultaneous paper-position limit reached."})
        return candidate
    risk_distance = abs(float(setup.entry) - float(setup.stop_loss))
    risk_budget = min(PAPER_GLOBAL_MAX_RISK_USD, PAPER_GLOBAL_STARTING_CAPITAL_USD * 0.05)
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
    created_at = datetime.now(timezone.utc).isoformat()
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
        "actual_exit": None, "realised_pnl": None, "created_at": created_at,
        "last_action_at": created_at,
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
        fill_price, fill_model = simulated_market_fill(setup.side, current_tick, currency="USD")
        if (setup.side == "BUY" and not float(setup.stop_loss) < fill_price < float(setup.target)
                or setup.side == "SELL" and not float(setup.target) < fill_price < float(setup.stop_loss)):
            candidate.update({"status": "AUTO_REJECTED", "decision_reason": "Latest quote invalidated the stop or target before paper entry."})
            return candidate
        current_unit_risk = abs(fill_price - float(setup.stop_loss))
        quantity = min(math.floor(risk_budget / current_unit_risk), math.floor(notional_cap / fill_price)) if current_unit_risk > 0 else 0
        if quantity < 1:
            candidate.update({"status": "AUTO_REJECTED", "decision_reason": "Latest quote exceeds the configured USD risk or notional cap."})
            return candidate
        entry_charges = estimate_execution_cost(fill_price, quantity, side=setup.side,
                                                asset_class=str(instrument["asset_class"]), currency="USD")
        order.update({"quantity": quantity, "risk_usd": round(current_unit_risk * quantity, 2),
                      "actual_entry": fill_price, "entry_charges": entry_charges,
                      "charges": entry_charges, "entry_fill_model": fill_model,
                      "paper_costs_note": "Estimated spread, slippage and transaction costs; actual broker fills and fees may differ."})
        order["allocated_capital"] = allocated_trade_capital(order)
        target_fraction = _profit_exit_fraction()
        order["profit_exit_target_percent"] = state.profit_exit_target_percent if target_fraction is not None else None
        order["net_profit_target_amount"] = round(order["allocated_capital"] * target_fraction, 2) if target_fraction is not None else None
        order["profit_reentry_cycle"] = int((order.get("evidence") or {}).get("profit_reentry_cycle", 0) or 0)
        if global_account()["daily_loss_lock"] or global_account()["orders_today"] >= state.max_trades_per_day:
            candidate.update({"status": "AUTO_REJECTED", "decision_reason": "Global USD daily risk or trade limit reached before paper entry."})
            return candidate
        if global_account()["open_positions"] >= state.max_open_positions:
            candidate.update({"status": "AUTO_REJECTED", "decision_reason": "Global USD simultaneous paper-position limit reached."})
            return candidate
        if any(o.get("status") == "OPEN" and o.get("currency") == "USD" and o.get("instrument_token") == token for o in state.orders):
            candidate.update({"status": "AUTO_REJECTED", "decision_reason": "A USD paper position is already open for this symbol."})
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


def _create_candidate(instrument: dict, setup, tick: dict) -> dict:
    candidate = _create_candidate_impl(instrument, setup, tick)
    if candidate:
        _record_candidate_status(candidate)
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
    fill_price, fill_model = simulated_market_fill(direction, tick, currency="USD")
    if direction == "BUY" and not stop < fill_price < target or direction == "SELL" and not target < fill_price < stop:
        raise ValueError("Current quote invalidated the suggested stop or target.")
    unit_risk = abs(fill_price - stop)
    quantity = min(math.floor(min(PAPER_GLOBAL_MAX_RISK_USD, PAPER_GLOBAL_STARTING_CAPITAL_USD * 0.05) / unit_risk),
                   math.floor(PAPER_GLOBAL_STARTING_CAPITAL_USD * 0.2 / fill_price)) if unit_risk > 0 else 0
    if quantity < 1:
        raise ValueError("USD stop-risk and notional limits prevent a whole-unit position.")
    if global_account()["daily_loss_lock"]:
        raise ValueError("Global USD daily loss lock is active.")
    if global_account()["orders_today"] >= state.max_trades_per_day:
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
        "suggested_stop_loss": stop, "suggested_target": target, "actual_entry": fill_price,
        "actual_stop_loss": stop, "actual_target": target, "actual_exit": None,
        "realised_pnl": None, "created_at": now.isoformat(), "last_action_at": now.isoformat(),
        "entry_charges": estimate_execution_cost(fill_price, quantity, side=direction,
                                                   asset_class=instrument["asset_class"], currency="USD"),
        "entry_fill_model": fill_model,
        "paper_costs_note": "Estimated spread, slippage and transaction costs; actual broker fills and fees may differ.",
    }
    order["allocated_capital"] = allocated_trade_capital(order)
    target_fraction = _profit_exit_fraction()
    order["profit_exit_target_percent"] = state.profit_exit_target_percent if target_fraction is not None else None
    order["net_profit_target_amount"] = round(order["allocated_capital"] * target_fraction, 2) if target_fraction is not None else None
    order["profit_reentry_cycle"] = int((order.get("evidence") or {}).get("profit_reentry_cycle", 0) or 0)
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
        fill_price, fill_model = simulated_market_fill(direction, current_tick, currency="USD")
        if direction == "BUY" and not stop < fill_price < target or direction == "SELL" and not target < fill_price < stop:
            raise ValueError("Latest quote invalidated the suggested stop or target before paper entry.")
        unit_risk = abs(fill_price - stop)
        quantity = min(math.floor(min(PAPER_GLOBAL_MAX_RISK_USD, PAPER_GLOBAL_STARTING_CAPITAL_USD * 0.05) / unit_risk),
                       math.floor(PAPER_GLOBAL_STARTING_CAPITAL_USD * 0.2 / fill_price)) if unit_risk > 0 else 0
        if quantity < 1:
            raise ValueError("Latest quote exceeds the configured USD risk or notional cap.")
        entry_charges = estimate_execution_cost(fill_price, quantity, side=direction,
                                                asset_class=instrument["asset_class"], currency="USD")
        order.update({"quantity": quantity, "risk_usd": round(unit_risk * quantity, 2),
                      "actual_entry": fill_price, "entry_charges": entry_charges,
                      "charges": entry_charges, "entry_fill_model": fill_model})
        order["allocated_capital"] = allocated_trade_capital(order)
        target_fraction = _profit_exit_fraction()
        order["profit_exit_target_percent"] = state.profit_exit_target_percent if target_fraction is not None else None
        order["net_profit_target_amount"] = round(order["allocated_capital"] * target_fraction, 2) if target_fraction is not None else None
        order["profit_reentry_cycle"] = int((order.get("evidence") or {}).get("profit_reentry_cycle", 0) or 0)
        if global_account()["daily_loss_lock"] or global_account()["orders_today"] >= state.max_trades_per_day:
            raise ValueError("Global USD daily risk or trade limit reached before paper entry.")
        if global_account()["open_positions"] >= state.max_open_positions:
            raise ValueError("Global USD simultaneous paper-position limit reached.")
        if any(o.get("status") == "OPEN" and o.get("currency") == "USD" and o.get("instrument_token") == token for o in state.orders):
            raise ValueError("A USD paper position is already open for this symbol.")
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
                        _manage_position(order, tick, now, instrument)
                if not is_market_open(instrument, now):
                    continue
                # JSON persistence can fsync large warm-up histories; keep that
                # disk work off the FastAPI loop so controls stay responsive.
                bar = await asyncio.to_thread(_book.add_tick, token, float(tick["ltp"]), now)
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
                if (state.operating_mode == "FULL" and state.autonomous_mode
                        and state.global_autonomous_mode
                        and not _global_autonomy_ready(datetime.now(timezone.utc))):
                    state.global_strategy_last_action = "Global autonomy is armed; waiting for fresh source-backed intelligence before evaluating entries."
                    continue
                key = (token, bar.started_at.isoformat())
                if key in _seen_bars:
                    continue
                _seen_bars.add(key)
                recent = False
                cutoff = now.timestamp() - 5 * 60
                for candidate in state.candidates.values():
                    if candidate.get("instrument_token") != token or candidate.get("status") in {"EXPIRED", "REJECTED", "WATCHLIST"}:
                        continue
                    try:
                        recent = datetime.fromisoformat(str(candidate.get("created_at", ""))).timestamp() >= cutoff
                    except (TypeError, ValueError):
                        recent = False
                    if recent:
                        break
                if recent:
                    state.global_strategy_last_action = f"Repeated setup suppressed for {instrument['symbol']}; a recent suggestion or decision is within the 5-minute cooldown."
                    continue
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
