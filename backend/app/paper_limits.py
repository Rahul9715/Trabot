"""Persistent, validated limits for the local paper simulators."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from threading import RLock

DEFAULT_LIMITS = {"max_open_positions": 10, "max_trades_per_day": 15, "max_risk_per_trade": None}
MAX_OPEN_POSITIONS_ALLOWED = 50
MAX_TRADES_PER_DAY_ALLOWED = 100
_lock = RLock()


def validate_limits(value: dict) -> dict[str, int | float | None]:
    if not isinstance(value, dict):
        raise ValueError("Paper trade limits must be an object.")
    try:
        open_positions = int(value["max_open_positions"])
        trades_per_day = int(value["max_trades_per_day"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Set both simultaneous-position and daily-trade limits.") from exc
    if not 1 <= open_positions <= MAX_OPEN_POSITIONS_ALLOWED:
        raise ValueError(f"Simultaneous positions must be between 1 and {MAX_OPEN_POSITIONS_ALLOWED}.")
    if not 1 <= trades_per_day <= MAX_TRADES_PER_DAY_ALLOWED:
        raise ValueError(f"Daily trade entries must be between 1 and {MAX_TRADES_PER_DAY_ALLOWED}.")
    raw_risk = value.get("max_risk_per_trade")
    try:
        risk = None if raw_risk in (None, "") else float(raw_risk)
    except (TypeError, ValueError) as exc:
        raise ValueError("Per-trade risk must be a positive INR amount or blank for the 5% default.") from exc
    if risk is not None and (not 0 < risk < 1_000_000_000):
        raise ValueError("Per-trade risk must be greater than ₹0 and less than ₹1,000,000,000.")
    return {"max_open_positions": open_positions, "max_trades_per_day": trades_per_day,
            "max_risk_per_trade": risk}


def load_limits(path: str | Path, fallback: dict | None = None) -> dict[str, int]:
    safe_fallback = validate_limits(fallback or DEFAULT_LIMITS)
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return validate_limits(payload)
    except FileNotFoundError:
        return safe_fallback
    except (OSError, json.JSONDecodeError, ValueError):
        return safe_fallback


def save_limits(path: str | Path, value: dict) -> dict[str, int]:
    limits = validate_limits(value)
    target = Path(path)
    with _lock:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".paper-limits-", suffix=".tmp", dir=target.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump({"version": 2, **limits}, stream, separators=(",", ":"))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return limits
