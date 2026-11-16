from datetime import datetime, timedelta, timezone

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
    setups = evaluate_strategies(_bars(values))
    sell = [setup for setup in setups if setup.strategy == "donchian_20_breakout" and setup.side == "SELL"]
    assert len(sell) == 1
    assert sell[0].stop_loss > sell[0].entry > sell[0].target


def test_rsi_reentry_rule_generates_opposite_direction_setup():
    # Long downswing followed by a single sharp recovery crosses RSI back above 30.
    values = [100 - i for i in range(29)] + [171]
    setups = evaluate_strategies(_bars(values))
    assert any(setup.strategy == "rsi_14_reentry" and setup.side == "BUY" for setup in setups)

