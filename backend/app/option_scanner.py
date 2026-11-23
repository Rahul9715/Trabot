"""Fail-closed Upstox option contract discovery and long-option selection.

Directional stock/index signals map to long calls (bullish) or long puts
(bearish). Naked short options are intentionally not represented here.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

API_ROOT = "https://api.upstox.com/v2"
IST = ZoneInfo("Asia/Kolkata")


def choose_expiry(contracts: list[dict], now: datetime | None = None) -> str | None:
    """Choose the nearest listed expiry with at least two calendar days left."""
    now = now or datetime.now(IST)
    today = now.astimezone(IST).date()
    expiries = set()
    for contract in contracts:
        try:
            expiry = date.fromisoformat(str(contract.get("expiry", "")))
        except ValueError:
            continue
        if expiry >= today + timedelta(days=2):
            expiries.add(expiry)
    return min(expiries).isoformat() if expiries else None


def select_long_option(chain_rows: list[dict], contracts: list[dict], direction: str,
                       *, max_spread_pct: float = 5.0, min_open_interest: int = 1000,
                       min_volume: int = 100) -> dict | None:
    """Select a liquid near-ATM long call/put from real option-chain quotes."""
    option_type = "CE" if direction == "BUY" else "PE" if direction == "SELL" else None
    if option_type is None:
        return None
    contract_map = {
        str(row.get("instrument_key")): row for row in contracts
        if row.get("instrument_key") and row.get("instrument_type") == option_type
    }
    choices = []
    for row in chain_rows:
        option = row.get("call_options" if option_type == "CE" else "put_options") or {}
        key = str(option.get("instrument_key", ""))
        contract = contract_map.get(key)
        market = option.get("market_data") or {}
        greeks = option.get("option_greeks") or {}
        try:
            bid, ask = float(market["bid_price"]), float(market["ask_price"])
            volume, oi = int(market.get("volume", 0)), int(market.get("oi", 0))
            delta = abs(float(greeks["delta"]))
            spot = float(row["underlying_spot_price"])
            strike = float(row["strike_price"])
            lot_size = int(contract["lot_size"])
        except (KeyError, TypeError, ValueError):
            continue
        if (not contract or not all(x > 0 for x in (bid, ask, spot, strike, lot_size))
                or ask < bid or volume < min_volume or oi < min_open_interest
                or not 0.25 <= delta <= 0.75):
            continue
        spread_pct = (ask - bid) / ((ask + bid) / 2) * 100
        if spread_pct > max_spread_pct:
            continue
        # Prefer roughly 0.50 absolute delta and a strike close to spot; spread
        # is a tie-breaker. No probability-of-profit field is used as a promise.
        score = abs(delta - 0.50) + abs(strike - spot) / max(spot, 1) + spread_pct / 100
        choices.append((score, {
            **contract,
            "option_type": option_type,
            "bid": bid,
            "ask": ask,
            "ltp": float(market.get("ltp") or ask),
            "volume": volume,
            "open_interest": oi,
            "spread_pct": spread_pct,
            "delta": float(greeks["delta"]),
            "underlying_spot": spot,
        }))
    return min(choices, key=lambda item: item[0])[1] if choices else None


def fetch_option_chain(underlying_key: str, access_token: str,
                       now: datetime | None = None) -> tuple[str, list[dict], list[dict]]:
    """Get the closest safe expiry and live chain; raises sanitized errors."""
    if not access_token:
        raise RuntimeError("UPSTOX_ACCESS_TOKEN is required to read option contracts.")
    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
    try:
        with httpx.Client(timeout=12) as client:
            contracts_response = client.get(f"{API_ROOT}/option/contract", params={"instrument_key": underlying_key}, headers=headers)
            contracts_response.raise_for_status()
            contracts = contracts_response.json().get("data", [])
            expiry = choose_expiry(contracts, now)
            if not expiry:
                raise RuntimeError("No listed option expiry remains at least two calendar days away.")
            chain_response = client.get(f"{API_ROOT}/option/chain", params={
                "instrument_key": underlying_key, "expiry_date": expiry,
            }, headers=headers)
            chain_response.raise_for_status()
            chain = chain_response.json().get("data", [])
    except (httpx.HTTPError, ValueError) as exc:
        raise RuntimeError(f"Upstox option-chain request failed: {type(exc).__name__}.") from exc
    if not isinstance(contracts, list) or not isinstance(chain, list):
        raise RuntimeError("Upstox returned an invalid option-chain response.")
    contracts = [row for row in contracts if isinstance(row, dict) and row.get("expiry") == expiry]
    return expiry, contracts, [row for row in chain if isinstance(row, dict)]
