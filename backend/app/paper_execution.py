"""Conservative paper fills and configurable execution-cost estimates.

These estimates are for research only. They do not reproduce a broker's order
book, queue position, partial fills, market impact, or contract note exactly.
"""
from __future__ import annotations

from .config import (
    PAPER_FALLBACK_SPREAD_BPS, PAPER_SLIPPAGE_BPS,
    PAPER_GLOBAL_FALLBACK_SPREAD_BPS, PAPER_GLOBAL_SLIPPAGE_BPS,
    PAPER_GLOBAL_COST_RATE_BPS, PAPER_BROKERAGE_PER_ORDER,
    PAPER_EQUITY_BROKERAGE_RATE, PAPER_EQUITY_EXCHANGE_RATE,
    PAPER_OPTIONS_EXCHANGE_RATE, PAPER_STT_EQUITY_INTRADAY_RATE,
    PAPER_STT_OPTIONS_SELL_RATE, PAPER_STAMP_BUY_RATE,
    PAPER_SEBI_RATE_PER_CRORE, PAPER_GST_RATE,
)

NET_TAKE_PROFIT_FRACTION = 0.08


def opposite_side(side: str) -> str:
    return "SELL" if str(side).upper() == "BUY" else "BUY"


def simulated_market_fill(side: str, quote: dict, *, currency: str = "INR") -> tuple[float, dict]:
    """Fill a marketable paper order at the quote side plus adverse slippage."""
    side = str(side).upper()
    if side not in {"BUY", "SELL"}:
        raise ValueError("Paper fill side must be BUY or SELL.")
    reference = float(quote.get("ltp") or quote.get("price") or 0)
    if reference <= 0:
        raise ValueError("A positive quote is required for a paper fill.")
    bid = quote.get("bid")
    ask = quote.get("ask")
    try:
        bid, ask = float(bid), float(ask)
        has_book = 0 < bid <= ask
    except (TypeError, ValueError):
        has_book = False
    if has_book:
        spread = ask - bid
        base = ask if side == "BUY" else bid
        spread_source = "best_bid_ask"
        fallback_half_spread = spread / 2
        slip_bps = PAPER_GLOBAL_SLIPPAGE_BPS if currency == "USD" else PAPER_SLIPPAGE_BPS
    else:
        spread_bps = PAPER_GLOBAL_FALLBACK_SPREAD_BPS if currency == "USD" else PAPER_FALLBACK_SPREAD_BPS
        fallback_half_spread = reference * spread_bps / 20000
        base = reference + fallback_half_spread if side == "BUY" else reference - fallback_half_spread
        spread_source = "estimated_fallback"
        slip_bps = PAPER_GLOBAL_SLIPPAGE_BPS if currency == "USD" else PAPER_SLIPPAGE_BPS
    slippage = reference * slip_bps / 10000
    fill = base + slippage if side == "BUY" else base - slippage
    return round(max(fill, 0.000001), 6), {
        "reference_price": reference,
        "spread_source": spread_source,
        "estimated_half_spread": round(fallback_half_spread, 6),
        "slippage_bps": slip_bps,
        "estimated_slippage": round(slippage, 6),
    }


def estimate_execution_cost(price: float, quantity: int, *, side: str,
                            asset_class: str, currency: str = "INR") -> float:
    """Estimate one-leg broker and market costs on the executed turnover."""
    turnover = abs(float(price) * int(quantity))
    if turnover <= 0:
        return 0.0
    if currency.upper() == "USD":
        return round(turnover * PAPER_GLOBAL_COST_RATE_BPS / 10000, 4)

    kind = str(asset_class or "equity").lower()
    side = str(side).upper()
    is_option = kind in {"option", "options"}
    is_future = kind in {"future", "futures"}
    if is_option:
        brokerage = PAPER_BROKERAGE_PER_ORDER
        exchange = turnover * PAPER_OPTIONS_EXCHANGE_RATE
        stt = turnover * PAPER_STT_OPTIONS_SELL_RATE if side == "SELL" else 0.0
    elif is_future:
        brokerage = min(PAPER_BROKERAGE_PER_ORDER, turnover * 0.0005)
        exchange = turnover * 0.0000183
        stt = turnover * 0.0005 if side == "SELL" else 0.0
    else:
        brokerage = min(PAPER_BROKERAGE_PER_ORDER, turnover * PAPER_EQUITY_BROKERAGE_RATE)
        exchange = turnover * PAPER_EQUITY_EXCHANGE_RATE
        stt = turnover * PAPER_STT_EQUITY_INTRADAY_RATE if side == "SELL" else 0.0

    sebi = turnover * PAPER_SEBI_RATE_PER_CRORE / 10_000_000
    stamp = turnover * PAPER_STAMP_BUY_RATE if side == "BUY" else 0.0
    gst = (brokerage + exchange) * PAPER_GST_RATE
    return round(brokerage + exchange + sebi + stamp + stt + gst, 2)


def round_trip_cost_estimate(order: dict, exit_reference: float) -> float:
    """Estimated accrued entry cost plus the cost of closing at the given mark."""
    exit_side = opposite_side(str(order.get("side", "BUY")))
    entry_fee = float(order.get("entry_charges", 0) or 0)
    exit_fee = estimate_execution_cost(
        exit_reference, int(order.get("quantity", 0) or 0), side=exit_side,
        asset_class=str(order.get("asset_class", "equity")),
        currency=str(order.get("currency", "INR")),
    )
    return round(entry_fee + exit_fee, 2)


def allocated_trade_capital(order: dict, *, entry_price: float | None = None,
                            quantity: int | None = None,
                            entry_charges: float | None = None) -> float:
    """Capital base for trade returns: long notional/premium, short stop-risk."""
    entry = float(entry_price if entry_price is not None else order.get("actual_entry", order.get("entry", 0)) or 0)
    qty = int(quantity if quantity is not None else order.get("quantity", 0) or 0)
    fees = float(entry_charges if entry_charges is not None else order.get("entry_charges", 0) or 0)
    if str(order.get("side", "BUY")).upper() == "BUY":
        deployed = entry * qty
    else:
        stop = float(order.get("actual_stop_loss", order.get("stop_loss", entry)) or entry)
        deployed = abs(entry - stop) * qty
    return round(max(0.0, deployed) + max(0.0, fees), 2)


def estimated_net_close(order: dict, quote: dict) -> tuple[float, float, dict, float]:
    """Estimate net P&L and exit costs using the same marketable paper fill model."""
    side = str(order.get("side", "BUY")).upper()
    exit_side = opposite_side(side)
    currency = str(order.get("currency", "INR"))
    price, model = simulated_market_fill(exit_side, quote, currency=currency)
    direction = 1 if side == "BUY" else -1
    entry = float(order.get("actual_entry", order.get("entry", 0)) or 0)
    quantity = int(order.get("quantity", 0) or 0)
    gross = (price - entry) * quantity * direction
    exit_charges = estimate_execution_cost(
        price, quantity, side=exit_side,
        asset_class=str(order.get("asset_class", "equity")), currency=currency,
    )
    net = round(gross - float(order.get("entry_charges", 0) or 0) - exit_charges, 2)
    return net, price, model, exit_charges


def projected_net_at_target(order: dict, entry_quote: dict, target: float) -> tuple[float, float]:
    """Estimate a new entry's net target P&L and allocated capital after all modeled costs."""
    side = str(order.get("side", "BUY")).upper()
    currency = str(order.get("currency", "INR"))
    quantity = int(order.get("quantity", 0) or 0)
    entry_price, _ = simulated_market_fill(side, entry_quote, currency=currency)
    entry_charges = estimate_execution_cost(
        entry_price, quantity, side=side,
        asset_class=str(order.get("asset_class", "equity")), currency=currency,
    )
    projected_order = {**order, "actual_entry": entry_price, "entry": entry_price,
                       "entry_charges": entry_charges}
    target_quote = {"ltp": float(target)}
    net, _, _, _ = estimated_net_close(projected_order, target_quote)
    capital = allocated_trade_capital(projected_order)
    return net, capital
