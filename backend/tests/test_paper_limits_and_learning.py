import json

import pytest

from app.paper_limits import load_limits, save_limits, validate_limits
from app.strategy_learning import autonomous_block, cumulative_realised, record_outcome, summary


def test_paper_trade_limits_default_validate_and_persist(tmp_path):
    path = tmp_path / "limits.json"
    assert load_limits(path) == {"max_open_positions": 10, "max_trades_per_day": 15,
                                 "max_risk_per_trade": None}
    saved = save_limits(path, {"max_open_positions": 7, "max_trades_per_day": 22,
                               "max_risk_per_trade": None})
    assert saved == load_limits(path)
    assert json.loads(path.read_text()) == {"version": 2, **saved}


@pytest.mark.parametrize("limits", [
    {"max_open_positions": 0, "max_trades_per_day": 15},
    {"max_open_positions": 51, "max_trades_per_day": 15},
    {"max_open_positions": 10, "max_trades_per_day": 101},
])
def test_paper_trade_limits_reject_out_of_range_values(limits):
    with pytest.raises(ValueError):
        validate_limits(limits)


def test_learning_ledger_is_deduplicated_and_pauses_only_after_minimum_sample(tmp_path):
    path = tmp_path / "learning.json"
    first = {"signal_id": "trade-0", "status": "CLOSED", "currency": "INR",
             "evidence": {"strategy": "ema_test"}, "entry": 100, "stop_loss": 90,
             "quantity": 1, "actual_exit": 90, "net_pnl": -10, "exit_reason": "stop"}
    for index in range(20):
        trade = {**first, "signal_id": f"trade-{index}", "actual_exit": 90, "net_pnl": -10}
        record_outcome(path, trade)
    record_outcome(path, first)
    assert summary(path)["closed_trades"] == 20
    assert autonomous_block(path, "ema_test", "equity")
    assert cumulative_realised(path, "INR") == -200


def test_learning_does_not_pause_before_twenty_closed_trades(tmp_path):
    path = tmp_path / "learning.json"
    for index in range(19):
        record_outcome(path, {
            "signal_id": f"trade-{index}", "status": "CLOSED", "currency": "USD",
            "asset_class": "equity", "evidence": {"strategy": "ema_test"},
            "entry": 100, "stop_loss": 90, "quantity": 1, "actual_exit": 90,
            "net_pnl": -10, "exit_reason": "stop",
        })
    assert autonomous_block(path, "ema_test", "equity") is None
