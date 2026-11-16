"""Deterministic, price-only strategy rules for the experimental paper engine.

These are candidate-generation rules, not claims of profitability. They require
completed one-minute bars created from the configured live feed; no price data
is synthesized to warm up indicators.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
import math
from typing import Iterable
from zoneinfo import ZoneInfo

BAR_SECONDS = 60
HISTORY_BARS = 250


@dataclass(frozen=True)
class Bar:
    started_at: datetime
    opened: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class Setup:
    strategy: str
    side: str
    entry: float
    stop_loss: float
    target: float
    rationale: str
    score: float
    bar_time: str


class MinuteBarBook:
    """Build completed minute OHLC bars from actual timestamped LTP updates."""

    def __init__(self, max_bars: int = HISTORY_BARS, session_timezone: str = "Asia/Kolkata"):
        self.history: dict[str, deque[Bar]] = {}
        self.current: dict[str, Bar] = {}
        self.sessions: dict[str, object] = {}
        self.max_bars = max_bars
        self.session_timezone = session_timezone

    def add_tick(self, instrument: str, price: float, timestamp: datetime) -> Bar | None:
        if not math.isfinite(price) or price <= 0:
            return None
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        timestamp = timestamp.astimezone(timezone.utc)
        session_date = timestamp.astimezone(ZoneInfo(self.session_timezone)).date()
        if self.sessions.get(instrument) != session_date:
            self.sessions[instrument] = session_date
            self.history[instrument] = deque(maxlen=self.max_bars)
            self.current.pop(instrument, None)
        minute = timestamp.replace(second=0, microsecond=0)
        bars = self.history.setdefault(instrument, deque(maxlen=self.max_bars))
        current = self.current.get(instrument)
        if current is None:
            self.current[instrument] = Bar(minute, price, price, price, price)
            return None
        if minute < current.started_at:
            return None
        if minute == current.started_at:
            self.current[instrument] = Bar(
                current.started_at, current.opened, max(current.high, price),
                min(current.low, price), price,
            )
            return None
        bars.append(current)
        self.current[instrument] = Bar(minute, price, price, price, price)
        return current

    def bars(self, instrument: str) -> list[Bar]:
        return list(self.history.get(instrument, ()))


def _ema(values: list[float], period: int) -> list[float]:
    if len(values) < period:
        return []
    alpha = 2.0 / (period + 1)
    result = [sum(values[:period]) / period]
    for value in values[period:]:
        result.append(alpha * value + (1 - alpha) * result[-1])
    return result


def _true_ranges(bars: list[Bar]) -> list[float]:
    ranges = []
    prior_close = bars[0].close
    for bar in bars[1:]:
        ranges.append(max(bar.high - bar.low, abs(bar.high - prior_close), abs(bar.low - prior_close)))
        prior_close = bar.close
    return ranges


def _atr(bars: list[Bar], period: int = 14) -> float | None:
    ranges = _true_ranges(bars)
    if len(ranges) < period:
        return None
    return sum(ranges[-period:]) / period


def _rsi(values: list[float], period: int = 14) -> list[float]:
    if len(values) <= period:
        return []
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    gains = [max(change, 0.0) for change in changes]
    losses = [max(-change, 0.0) for change in changes]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    output = [100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)]
    for gain, loss in zip(gains[period:], losses[period:]):
        avg_gain = ((period - 1) * avg_gain + gain) / period
        avg_loss = ((period - 1) * avg_loss + loss) / period
        output.append(100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss))
    return output


def _setup(strategy: str, side: str, entry: float, atr: float, rationale: str,
           score: float, bar: Bar, stop_atr: float = 1.5, reward_risk: float = 2.0) -> Setup | None:
    if not math.isfinite(atr) or atr <= 0:
        return None
    risk = atr * stop_atr
    stop = entry - risk if side == "BUY" else entry + risk
    target = entry + risk * reward_risk if side == "BUY" else entry - risk * reward_risk
    if stop <= 0 or target <= 0:
        return None
    return Setup(strategy, side, entry, stop, target, rationale, score, bar.started_at.isoformat())


def evaluate_strategies(bars: Iterable[Bar]) -> list[Setup]:
    """Return deterministic rules that fired on the last completed bar.

    Rules: 8/21 EMA crossover, 20-bar Donchian breakout, and 14-period RSI
    re-entry from an extreme. The numeric score is a rule-strength label, not
    a calibrated win probability. One bar has a deterministic one-setup-per-
    strategy limit; portfolio risk controls are enforced by the caller.
    """
    rows = list(bars)
    if len(rows) < 30:
        return []
    closes = [bar.close for bar in rows]
    atr = _atr(rows)
    if atr is None or atr <= 0:
        return []
    last = rows[-1]
    results: list[Setup] = []

    fast = _ema(closes, 8)
    slow = _ema(closes, 21)
    if fast and slow:
        # EMA arrays begin at different indices; compare the current values and
        # derive the previous slow EMA from the matching preceding close window.
        fast_prev = _ema(closes[:-1], 8)
        slow_prev = _ema(closes[:-1], 21)
        if fast_prev and slow_prev:
            if fast_prev[-1] <= slow_prev[-1] and fast[-1] > slow[-1]:
                setup = _setup("ema_8_21_crossover", "BUY", last.close, atr,
                               "Completed 1m close crossed above the 8/21 EMA pair; stop 1.5 ATR, target 2R.", 65, last)
                if setup: results.append(setup)
            elif fast_prev[-1] >= slow_prev[-1] and fast[-1] < slow[-1]:
                setup = _setup("ema_8_21_crossover", "SELL", last.close, atr,
                               "Completed 1m close crossed below the 8/21 EMA pair; stop 1.5 ATR, target 2R.", 65, last)
                if setup: results.append(setup)

    prior = rows[-21:-1]
    if len(prior) == 20:
        upper = max(bar.high for bar in prior)
        lower = min(bar.low for bar in prior)
        if last.close > upper:
            setup = _setup("donchian_20_breakout", "BUY", last.close, atr,
                           "Completed 1m close broke the prior 20-bar high; stop 1.5 ATR, target 2R.", 70, last)
            if setup: results.append(setup)
        elif last.close < lower:
            setup = _setup("donchian_20_breakout", "SELL", last.close, atr,
                           "Completed 1m close broke the prior 20-bar low; stop 1.5 ATR, target 2R.", 70, last)
            if setup: results.append(setup)

    rsi = _rsi(closes, 14)
    if len(rsi) >= 2:
        previous, current = rsi[-2], rsi[-1]
        if previous < 30 <= current:
            setup = _setup("rsi_14_reentry", "BUY", last.close, atr,
                           f"RSI(14) re-entered above 30 ({current:.1f}) on a completed 1m bar; stop 1.5 ATR, target 2R.", 60, last)
            if setup: results.append(setup)
        elif previous > 70 >= current:
            setup = _setup("rsi_14_reentry", "SELL", last.close, atr,
                           f"RSI(14) re-entered below 70 ({current:.1f}) on a completed 1m bar; stop 1.5 ATR, target 2R.", 60, last)
            if setup: results.append(setup)
    return results
