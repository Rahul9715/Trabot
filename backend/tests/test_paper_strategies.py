from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.paper_strategies import Bar, MinuteBarBook, evaluate_strategies


def _bars(closes):
    start = datetime(2026, 1, 5, 4, 0, tzinfo=timezone.utc)
    return [Bar(start + timedelta(minutes=i), price, price + 0.5, price - 0.5, price)
            for i, price in enumerate(closes)]


def test_minute_bar_book_uses_observed_ticks_and_closes_on_minute_change():
    book = MinuteBarBook()
    first = datetime(2026, 1, 5, 4, 0, 1, tzinfo=timezone.utc)
    assert book.add_tick("NSE_EQ|TEST", 100, first) is None
    assert book.add_tick("NSE_EQ|TEST", 102, first + timedelta(seconds=20)) is None
    completed = book.add_tick("NSE_EQ|TEST", 101, first + timedelta(minutes=1))
    assert completed == Bar(first.replace(second=0, microsecond=0), 100, 102, 100, 102)
    assert book.bars("NSE_EQ|TEST") == [completed]


def test_strategies_wait_for_real_warmup_bars():
    assert evaluate_strategies(_bars([100 + i * 0.1 for i in range(29)])) == []


def test_donchian_breakout_uses_previous_bars_not_current_bar():
    rows = _bars([100 + i * 0.02 for i in range(29)] + [105])
    rows[-1] = Bar(rows[-1].started_at, 104.3, 105.2, 104.1, 105)
    setups = evaluate_strategies(rows)
    breakout = [setup for setup in setups if setup.strategy == "donchian_20_breakout"]
    assert len(breakout) == 1
    assert breakout[0].side == "BUY"
    assert breakout[0].target > breakout[0].entry > breakout[0].stop_loss
    assert breakout[0].score == 70


def test_ema_crossover_generates_directional_setup():
    values = [130 - i for i in range(29)] + [160]
    setups = evaluate_strategies(_bars(values))
    assert any(setup.strategy == "ema_8_21_crossover" and setup.side == "BUY" for setup in setups)


def test_donchian_breakdown_generates_sell_setup():
    values = [100 + i * 0.02 for i in range(29)] + [95]
    rows = _bars(values)
    rows[-1] = Bar(rows[-1].started_at, 95.7, 95.9, 94.8, 95)
    setups = evaluate_strategies(rows)
    sell = [setup for setup in setups if setup.strategy == "donchian_20_breakout" and setup.side == "SELL"]
    assert len(sell) == 1
    assert sell[0].stop_loss > sell[0].entry > sell[0].target


def test_rsi_reentry_rule_generates_opposite_direction_setup():
    # Long downswing followed by a single sharp recovery crosses RSI back above 30.
    values = [100 - i for i in range(29)] + [171]
    setups = evaluate_strategies(_bars(values))
    assert any(setup.strategy == "rsi_14_reentry" and setup.side == "BUY" for setup in setups)


def test_fast_ema_and_shorter_donchian_rules_expand_coverage():
    values = [130 - i for i in range(29)] + [160]
    rows = _bars(values)
    rows[-1] = Bar(rows[-1].started_at, 158, 160.2, 157.8, 160)
    setups = evaluate_strategies(rows)
    assert any(setup.strategy == "ema_5_13_crossover" and setup.side == "BUY" for setup in setups)
    assert any(setup.strategy == "donchian_10_breakout" and setup.side == "BUY" for setup in setups)


def test_donchian_ignores_marginal_choppy_breakout_without_candle_confirmation():
    rows = _bars([100 + (0.03 if i % 2 else -0.03) for i in range(29)] + [100.08])
    setups = evaluate_strategies(rows)
    assert not any(setup.strategy.startswith("donchian_") for setup in setups)


def test_bollinger_reentry_rule_generates_a_long_candidate():
    values = [100.0] * 28 + [80.0, 100.0]
    setups = evaluate_strategies(_bars(values))
    assert any(setup.strategy == "bollinger_20_reentry" and setup.side == "BUY" for setup in setups)


def test_macd_rule_waits_for_signal_history_then_detects_crossover():
    values = [100.0] * 30 + [100 - i for i in range(1, 10)] + [130.0]
    setups = evaluate_strategies(_bars(values))
    assert any(setup.strategy == "macd_12_26_9_crossover" and setup.side == "BUY" for setup in setups)


def test_short_signals_are_generated_for_downside_crossovers_and_reentries():
    values = [100.0 + i for i in range(29)] + [70.0]
    rows = _bars(values)
    rows[-1] = Bar(rows[-1].started_at, 71.0, 71.2, 69.8, 70.0)
    setups = evaluate_strategies(rows)
    assert any(setup.strategy == "ema_8_21_crossover" and setup.side == "SELL" for setup in setups)
    assert any(setup.strategy == "donchian_20_breakout" and setup.side == "SELL" for setup in setups)
    assert any(setup.strategy == "donchian_10_breakout" and setup.side == "SELL" for setup in setups)
    assert any(setup.strategy == "rsi_14_reentry" and setup.side == "SELL" for setup in setups)


def test_bollinger_upper_band_reentry_generates_a_short_candidate():
    values = [100.0] * 28 + [120.0, 100.0]
    setups = evaluate_strategies(_bars(values))
    assert any(setup.strategy == "bollinger_20_reentry" and setup.side == "SELL" for setup in setups)


def test_completed_warmup_bars_survive_book_restart_for_same_session(tmp_path):
    path = tmp_path / "warmup.json"
    local_now = datetime.now(ZoneInfo("Asia/Kolkata")).replace(hour=10, minute=0, second=10, microsecond=0)
    first = local_now.astimezone(timezone.utc)
    book = MinuteBarBook(storage_path=path)
    book.add_tick("NSE_EQ|TEST", 100, first)
    closed = book.add_tick("NSE_EQ|TEST", 101, first + timedelta(minutes=1))
    assert closed is not None

    restarted = MinuteBarBook(storage_path=path)
    assert restarted.bars("NSE_EQ|TEST") == [closed]


def test_persisted_warmup_does_not_carry_into_a_new_local_session(tmp_path):
    path = tmp_path / "warmup.json"
    local_now = datetime.now(ZoneInfo("Asia/Kolkata")).replace(hour=10, minute=0, second=10, microsecond=0)
    previous_day = (local_now - timedelta(days=1)).astimezone(timezone.utc)
    book = MinuteBarBook(storage_path=path)
    book.add_tick("NSE_EQ|TEST", 100, previous_day)
    book.add_tick("NSE_EQ|TEST", 101, previous_day + timedelta(minutes=1))

    restarted = MinuteBarBook(storage_path=path)
    assert restarted.bars("NSE_EQ|TEST") == []

