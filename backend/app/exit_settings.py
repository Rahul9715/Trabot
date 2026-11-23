"""Validated, durable user preferences for optional paper-profit exits."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from threading import RLock

DEFAULT_EXIT_SETTINGS = {"enabled": False, "target_percent": 8.0}
_lock = RLock()


def validate_exit_settings(value: dict) -> dict[str, bool | float]:
    if not isinstance(value, dict):
        raise ValueError("Paper exit settings must be an object.")
    enabled = value.get("enabled", DEFAULT_EXIT_SETTINGS["enabled"])
    if not isinstance(enabled, bool):
        raise ValueError("Gain exit enabled must be true or false.")
    try:
        target_percent = float(value.get("target_percent", DEFAULT_EXIT_SETTINGS["target_percent"]))
    except (TypeError, ValueError) as exc:
        raise ValueError("Gain target must be a number between 0.1% and 100%.") from exc
    if not 0.1 <= target_percent <= 100 or not target_percent < float("inf"):
        raise ValueError("Gain target must be between 0.1% and 100%.")
    return {"enabled": enabled, "target_percent": round(target_percent, 4)}


def load_exit_settings(path: str | Path) -> dict[str, bool | float]:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return validate_exit_settings(raw)
    except (FileNotFoundError, OSError, json.JSONDecodeError, ValueError):
        return dict(DEFAULT_EXIT_SETTINGS)


def save_exit_settings(path: str | Path, value: dict) -> dict[str, bool | float]:
    settings = validate_exit_settings(value)
    target = Path(path)
    with _lock:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".paper-exit-", suffix=".tmp", dir=target.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump({"version": 1, **settings}, stream, separators=(",", ":"))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return settings


def active_take_profit_fraction(settings: dict) -> float | None:
    """Return a fractional capital threshold, or None when disabled."""
    normalized = validate_exit_settings(settings)
    if not normalized["enabled"]:
        return None
    return float(normalized["target_percent"]) / 100.0
