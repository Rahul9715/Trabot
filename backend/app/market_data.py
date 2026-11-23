"""Timestamp helpers for market-data freshness checks."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def provider_timestamp(value: Any) -> str | None:
    """Normalize Upstox epoch timestamps (seconds or milliseconds) to UTC ISO-8601."""
    if value is None or value == "":
        return None
    try:
        numeric = float(value)
        if numeric > 10_000_000_000:  # millisecond epoch
            numeric /= 1000
        return datetime.fromtimestamp(numeric, timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError, OverflowError):
            return None


def quote_timestamp(tick: dict[str, Any] | None) -> datetime | None:
    """Use provider feed time when present, falling back to local receive time."""
    if not tick:
        return None
    for field in ("provider_received_at", "received_at"):
        value = tick.get(field)
        if not value:
            continue
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except (TypeError, ValueError, OverflowError):
            continue
    return None


def quote_age_seconds(tick: dict[str, Any] | None, now: datetime | None = None) -> float:
    timestamp = quote_timestamp(tick)
    if timestamp is None:
        return float("inf")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return (current.astimezone(timezone.utc) - timestamp).total_seconds()
