from datetime import datetime, timezone

from app.option_scanner import choose_expiry, select_long_option


def test_option_expiry_skips_contracts_near_expiry():
    now = datetime(2026, 11, 17, 6, tzinfo=timezone.utc)
    contracts = [
        {"expiry": "2026-11-18"},
        {"expiry": "2026-11-19"},
        {"expiry": "2026-11-26"},
    ]
    assert choose_expiry(contracts, now) == "2026-11-19"


def test_bullish_signal_selects_long_call_with_liquidity_and_spread_checks():
    contracts = [
        {"instrument_key": "NSE_FO|C1", "instrument_type": "CE", "lot_size": 25,
         "expiry": "2026-11-26", "trading_symbol": "ABC 100 CE"},
        {"instrument_key": "NSE_FO|P1", "instrument_type": "PE", "lot_size": 25,
         "expiry": "2026-11-26", "trading_symbol": "ABC 100 PE"},
    ]
    chain = [{
        "strike_price": 100,
        "underlying_spot_price": 101,
        "call_options": {"instrument_key": "NSE_FO|C1", "market_data": {
            "bid_price": 9.8, "ask_price": 10.0, "ltp": 9.9, "volume": 500, "oi": 2000,
        }, "option_greeks": {"delta": 0.52}},
        "put_options": {"instrument_key": "NSE_FO|P1", "market_data": {
            "bid_price": 8.0, "ask_price": 8.1, "volume": 500, "oi": 2000,
        }, "option_greeks": {"delta": -0.48}},
    }]
    chosen = select_long_option(chain, contracts, "BUY")
    assert chosen["instrument_key"] == "NSE_FO|C1"
    assert chosen["option_type"] == "CE"
    assert chosen["lot_size"] == 25


def test_bearish_signal_selects_put_and_rejects_illiquid_or_wide_contracts():
    contracts = [{"instrument_key": "NSE_FO|P1", "instrument_type": "PE", "lot_size": 25}]
    illiquid = [{"strike_price": 100, "underlying_spot_price": 100,
                 "put_options": {"instrument_key": "NSE_FO|P1", "market_data": {
                     "bid_price": 9, "ask_price": 12, "volume": 0, "oi": 10000,
                 }, "option_greeks": {"delta": -0.5}}}]
    assert select_long_option(illiquid, contracts, "SELL") is None


def test_option_selector_fails_closed_for_unknown_direction_or_contract():
    assert select_long_option([], [], "HOLD") is None


def test_option_candidate_maps_bearish_underlying_signal_to_long_put(monkeypatch):
    from app import main
    from app.paper_strategies import Setup

    captured = {}
    monkeypatch.setitem(main.state.option_contracts, "NSE_FO|P1", {})
    monkeypatch.setitem(main.state.ticks, "NSE_FO|P1", {})
    contract = {"instrument_key": "NSE_FO|P1", "instrument_type": "PE", "lot_size": 25,
                "expiry": "2026-11-26", "trading_symbol": "NIFTY 25000 PE",
                "option_type": "PE", "bid": 10.0, "ask": 10.2, "ltp": 10.1,
                "volume": 500, "open_interest": 2000, "spread_pct": 1.98, "delta": -0.5,
                "strike_price": 25000}
    monkeypatch.setattr(main, "UPSTOX_ACCESS_TOKEN", "test-token")
    monkeypatch.setattr(main, "fetch_option_chain", lambda *args: ("2026-11-26", [contract], []))
    monkeypatch.setattr(main, "select_long_option", lambda *args: contract)
    monkeypatch.setattr(main.feed, "subscribe", lambda keys: None)
    monkeypatch.setattr(main, "_record_strategy_candidate",
                        lambda key, setup, tick, metadata: captured.update(
                            key=key, setup=setup, tick=tick, metadata=metadata) or {"status": "PENDING"})
    setup = Setup("donchian_20_breakout", "SELL", 25000, 25100, 24800,
                  "Bearish underlying setup", 70, "2026-11-17T05:00:00+00:00")

    result = main._record_option_candidate("NSE_INDEX|Nifty 50", setup, {"ltp": 25000})

    assert result["status"] == "PENDING"
    assert captured["key"] == "NSE_FO|P1"
    assert captured["setup"].side == "BUY"
    assert captured["metadata"]["option_type"] == "PE"
