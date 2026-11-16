from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app import twelve_data_feed
from app import global_paper
from app.global_paper import global_account, is_market_open
from app.paper_strategies import MinuteBarBook
from app.risk import current_daily_pnl
from app.state import state


def test_equity_session_uses_regular_nyse_hours_and_no_weekends():
    equity = {"asset_class": "equity"}
    # 10:00 ET on a Tuesday
    assert is_market_open(equity, datetime(2026, 11, 17, 15, 0, tzinfo=timezone.utc), for_entry=True)
    # 09:20 ET and Saturday are closed for entries
    assert not is_market_open(equity, datetime(2026, 11, 17, 14, 20, tzinfo=timezone.utc), for_entry=True)
    assert not is_market_open(equity, datetime(2026, 11, 21, 15, 0, tzinfo=timezone.utc), for_entry=True)


def test_fx_and_spot_commodity_sessions_are_weekdays_not_24_7():
    fx = {"asset_class": "currency"}
    commodity = {"asset_class": "commodity"}
    assert is_market_open(fx, datetime(2026, 11, 17, 2, 0, tzinfo=timezone.utc))
    assert is_market_open(commodity, datetime(2026, 11, 17, 2, 0, tzinfo=timezone.utc))
    # Sunday 16:00 ET is before the broad FX open; Saturday is closed.
    assert not is_market_open(fx, datetime(2026, 11, 22, 21, 0, tzinfo=timezone.utc))
    assert not is_market_open(commodity, datetime(2026, 11, 22, 21, 0, tzinfo=timezone.utc))
    assert not is_market_open(fx, datetime(2026, 11, 21, 15, 0, tzinfo=timezone.utc))


def test_global_feed_normalizes_price_quote_without_exposing_provider_key(monkeypatch):
    feed = twelve_data_feed.TwelveDataFeed()
    feed.by_symbol = {"aapl": {"symbol": "AAPL", "instrument_token": "TD_US_EQ|AAPL",
                               "asset_class": "equity", "market_region": "US",
                               "exchange": "NASDAQ/NYSE", "currency": "USD"}}
    old_ticks = state.ticks.copy()
    try:
        feed._on_message(None, '{"event":"price","symbol":"AAPL","price":123.45,"timestamp":1794942000}')
        tick = state.ticks["TD_US_EQ|AAPL"]
        assert tick["ltp"] == 123.45
        assert tick["data_source"] == "Twelve Data"
        assert tick["currency"] == "USD"
        assert tick["provider_timestamp"].endswith("+00:00")
    finally:
        state.ticks.clear()
        state.ticks.update(old_ticks)


def test_us_bar_book_resets_at_new_york_calendar_day():
    book = MinuteBarBook(session_timezone="America/New_York")
    # 23:59 ET then 00:00 ET: the latter starts a new session history.
    book.add_tick("TD_US_EQ|AAPL", 100, datetime(2026, 11, 17, 4, 59, 10, tzinfo=timezone.utc))
    book.add_tick("TD_US_EQ|AAPL", 101, datetime(2026, 11, 17, 5, 0, 10, tzinfo=timezone.utc))
    assert book.bars("TD_US_EQ|AAPL") == []


def test_usd_account_does_not_mix_inr_orders_or_pnl():
    old_orders = state.orders[:]
    old_realised = state.global_daily_realised_pnl_usd
    old_day = state.global_daily_date
    old_inr_realised = state.daily_realised_pnl
    try:
        state.global_daily_date = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
        state.global_daily_realised_pnl_usd = 12.5
        state.orders[:] = [
            {"currency": "USD", "status": "CLOSED", "created_at": datetime.now(ZoneInfo("America/New_York")).isoformat()},
            {"currency": "INR", "status": "OPEN", "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        account = global_account()
        assert account["currency"] == "USD"
        assert account["realised_pnl"] == 12.5
        assert account["daily_pnl"] == 12.5
        assert account["orders_today"] == 1
        assert account["open_positions"] == 0
        state.daily_realised_pnl = 4.0
        assert current_daily_pnl(state) == 4.0
    finally:
        state.orders[:] = old_orders
        state.global_daily_realised_pnl_usd = old_realised
        state.global_daily_date = old_day
        state.daily_realised_pnl = old_inr_realised


def test_global_loss_lock_revokes_global_autonomy_without_touching_kill_switch(monkeypatch):
    old_realised = state.global_daily_realised_pnl_usd
    old_baseline = state.global_daily_loss_baseline_usd
    old_date = state.global_daily_date
    old_lock = state.global_daily_loss_lock
    old_global_auto = state.global_autonomous_mode
    old_kill = state.kill_switch
    try:
        state.global_daily_date = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
        state.global_daily_realised_pnl_usd = -11
        state.global_daily_loss_baseline_usd = 0
        state.global_daily_loss_lock = False
        state.global_autonomous_mode = True
        state.kill_switch = False
        monkeypatch.setattr(global_paper, "PAPER_GLOBAL_DAILY_LOSS_LIMIT_USD", 10)
        monkeypatch.setattr(global_paper, "record_event", lambda *args, **kwargs: None)
        account = global_account()
        assert account["daily_loss_lock"] is True
        assert state.global_autonomous_mode is False
        assert state.kill_switch is False
    finally:
        state.global_daily_realised_pnl_usd = old_realised
        state.global_daily_loss_baseline_usd = old_baseline
        state.global_daily_date = old_date
        state.global_daily_loss_lock = old_lock
        state.global_autonomous_mode = old_global_auto
        state.kill_switch = old_kill


def test_india_date_rollover_keeps_an_explicit_global_autonomy_permission():
    old_values = {
        "daily_date": state.daily_date,
        "daily_realised_pnl": state.daily_realised_pnl,
        "autonomous_daily_loss_limit": state.autonomous_daily_loss_limit,
        "autonomous_mode": state.autonomous_mode,
        "global_autonomous_mode": state.global_autonomous_mode,
        "operating_mode": state.operating_mode,
        "bot_enabled": state.bot_enabled,
        "kill_switch": state.kill_switch,
    }
    try:
        state.daily_date = "2000-01-01"
        state.daily_realised_pnl = -55
        state.autonomous_daily_loss_limit = 300
        state.autonomous_mode = True
        state.global_autonomous_mode = True
        state.operating_mode = "FULL"
        state.bot_enabled = True
        state.kill_switch = False
        state.reset_daily_counters_if_needed()
        assert state.autonomous_mode is True
        assert state.operating_mode == "FULL"
        assert state.autonomous_daily_loss_limit == 300
        assert state.daily_realised_pnl == 0
        assert state.kill_switch is False
    finally:
        state.daily_date = old_values["daily_date"]
        state.daily_realised_pnl = old_values["daily_realised_pnl"]
        state.autonomous_daily_loss_limit = old_values["autonomous_daily_loss_limit"]
        state.autonomous_mode = old_values["autonomous_mode"]
        state.global_autonomous_mode = old_values["global_autonomous_mode"]
        state.operating_mode = old_values["operating_mode"]
        state.bot_enabled = old_values["bot_enabled"]
        state.kill_switch = old_values["kill_switch"]
