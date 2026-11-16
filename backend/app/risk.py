from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from .config import MAX_OPEN_POSITIONS

def calculate_unrealised_pnl(orders, ticks):
    total = 0.0
    for order in orders:
        if order.get("status") != "OPEN" or order.get("currency", "INR") != "INR":
            continue
        tick = ticks.get(order.get("instrument_token"))
        if not tick:
            continue
        ltp = float(tick["ltp"])
        direction = 1 if order["side"] == "BUY" else -1
        total += (ltp - float(order.get("actual_entry", order["entry"]))) * int(order["quantity"]) * direction
    return total

def current_daily_pnl(state):
    return float(state.daily_realised_pnl) + calculate_unrealised_pnl(state.orders, state.ticks)

def validate(signal, approval, ticks, orders, daily_pnl):
    if not approval:
        raise ValueError("No approved daily strategy.")
    expiry = datetime.fromisoformat(approval["expires_at"].replace("Z", "+00:00"))
    if datetime.now(timezone.utc) >= expiry:
        raise ValueError("Strategy approval expired.")
    if signal.symbol.upper() not in [s.upper() for s in approval["symbols"]]:
        raise ValueError("Symbol not included in approved universe.")
    if len([o for o in orders if o["status"] == "OPEN" and o.get("currency", "INR") == "INR"]) >= MAX_OPEN_POSITIONS:
        raise ValueError("Maximum open positions reached.")
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    todays_orders = [
        o for o in orders
        if o.get("currency", "INR") == "INR"
        and datetime.fromisoformat(o["created_at"]).astimezone(ZoneInfo("Asia/Kolkata")).date() == today
    ]
    if len(todays_orders) >= approval["max_trades"]:
        raise ValueError("Approved daily trade count reached.")
    if daily_pnl <= -approval["max_daily_loss"]:
        raise ValueError("Daily loss limit reached.")
    if signal.side == "BUY":
        if not signal.stop_loss < signal.entry < signal.target:
            raise ValueError("BUY requires SL < entry < target.")
        per_share = signal.entry - signal.stop_loss
    else:
        if not signal.target < signal.entry < signal.stop_loss:
            raise ValueError("SELL requires target < entry < SL.")
        per_share = signal.stop_loss - signal.entry
    risk = per_share * signal.quantity
    if risk > approval["max_risk_per_trade"]:
        raise ValueError(f"Trade risk ₹{risk:.2f} exceeds approval.")
    tick = ticks.get(signal.instrument_token)
    if not tick:
        raise ValueError("No market quote available for this instrument.")
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(tick["received_at"])).total_seconds()
    if age > 3:
        raise ValueError("Market data is stale (>3 seconds). New orders blocked.")
    ltp = float(tick["ltp"])
    if abs(ltp - signal.entry) / signal.entry > 0.0025:
        raise ValueError("Live price moved outside 0.25% approved entry tolerance.")
    return round(risk, 2)
