import json
import pytest

from app.exit_settings import (
    DEFAULT_EXIT_SETTINGS,
    active_take_profit_fraction,
    load_exit_settings,
    save_exit_settings,
    validate_exit_settings,
)


def test_gain_exit_is_disabled_by_default():
    assert DEFAULT_EXIT_SETTINGS == {"enabled": False, "target_percent": 8.0}
    assert active_take_profit_fraction(DEFAULT_EXIT_SETTINGS) is None


@pytest.mark.parametrize("value", [0, 0.099, 100.01, float("nan"), float("inf"), "bad"])
def test_rejects_invalid_gain_threshold(value):
    with pytest.raises(ValueError):
        validate_exit_settings({"enabled": True, "target_percent": value})


def test_persists_user_toggle_and_percentage_across_restart(tmp_path):
    path = tmp_path / "paper_exit_settings.json"
    saved = save_exit_settings(path, {"enabled": True, "target_percent": 5.5})
    assert saved == {"enabled": True, "target_percent": 5.5}
    assert load_exit_settings(path) == saved
    assert active_take_profit_fraction(saved) == pytest.approx(0.055)
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 1


def test_disabling_gain_exit_keeps_custom_threshold_but_disables_trigger(tmp_path):
    path = tmp_path / "paper_exit_settings.json"
    saved = save_exit_settings(path, {"enabled": False, "target_percent": 12})
    assert load_exit_settings(path) == saved
    assert active_take_profit_fraction(saved) is None
