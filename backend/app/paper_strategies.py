"""Deterministic, price-only strategy rules for the experimental paper engine.

These are candidate-generation rules, not claims of profitability. They require
completed one-minute bars created from the configured live feed; no price data
is synthesized to warm up indicators.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

BAR_SECONDS = 60
HISTORY_BARS = 250
STRATEGY_NAMES = [
    "ema_8_21_crossover",
    "ema_5_13_crossover",
    "donchian_20_breakout",
    "donchian_10_breakout",
    "rsi_14_reentry",
    "bollinger_20_reentry",
    "macd_12_26_9_crossover",
]


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
    features: dict[str, float] = field(default_factory=dict)


class MinuteBarBook:
    """Build completed minute OHLC bars from actual timestamped LTP updates."""

    def __init__(self, max_bars: int = HISTORY_BARS, session_timezone: str = "Asia/Kolkata",
                 storage_path: str | Path | None = None):
        self.history: dict[str, deque[Bar]] = {}
        self.current: dict[str, Bar] = {}
        self.sessions: dict[str, object] = {}
        self.max_bars = max_bars
        self.session_timezone = session_timezone
        self.storage_path = Path(storage_path) if storage_path else None
        self._storage_lock = threading.RLock()
        if self.storage_path:
            self._load_persisted()

    def _load_persisted(self) -> None:
        """Restore only valid completed bars; current partial bars are never persisted."""
        try:
            payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(payload, dict) or payload.get("version") != 1:
            return
        today = datetime.now(ZoneInfo(self.session_timezone)).date()
        for instrument, values in payload.get("instruments", {}).items():
            if not isinstance(instrument, str) or not isinstance(values, list):
                continue
            restored: list[Bar] = []
            for row in values[-self.max_bars:]:
                try:
                    started_at = datetime.fromisoformat(row["started_at"])
                    if started_at.tzinfo is None:
                        continue
                    started_at = started_at.astimezone(timezone.utc)
                    if started_at.astimezone(ZoneInfo(self.session_timezone)).date() != today:
                        continue
                    prices = [float(row[key]) for key in ("opened", "high", "low", "close")]
                    if not all(math.isfinite(value) and value > 0 for value in prices):
                        continue
                    opened, high, low, close = prices
                    if low > min(opened, close) or high < max(opened, close) or high < low:
                        continue
                    restored.append(Bar(started_at, opened, high, low, close))
                except (KeyError, TypeError, ValueError, IndexError):
                    continue
            if restored:
                self.history[instrument] = deque(restored, maxlen=self.max_bars)
                self.sessions[instrument] = today

    def _persist(self) -> None:
        if not self.storage_path:
            return
        with self._storage_lock:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            instruments = {}
            for instrument, bars in self.history.items():
                instruments[instrument] = [{
                    "started_at": bar.started_at.isoformat(), "opened": bar.opened,
                    "high": bar.high, "low": bar.low, "close": bar.close,
                } for bar in bars]
            payload = {"version": 1, "session_timezone": self.session_timezone,
                       "saved_at": datetime.now(timezone.utc).isoformat(),
                       "instruments": instruments}
            fd, temporary = tempfile.mkstemp(prefix=".warmup-", suffix=".tmp", dir=self.storage_path.parent)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump(payload, stream, separators=(",", ":"))
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.storage_path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)

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
            self._persist()
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
        self._persist()
        self.current[instrument] = Bar(minute, price, price, price, price)
        return current

    def bars(self, instrument: str) -> list[Bar]:
        return list(self.history.get(instrument, ()))

    def counts(self) -> dict[str, int]:
        return {instrument: len(bars) for instrument, bars in self.history.items()}


def _ema(values: list[float], period: int) -> list[float]:
    if len(values) < period:
        return []
    alpha = 2.0 / (period + 1)
    result = [sum(values[:period]) / period]
    for value in values[period:]:
        result.append(alpha * value + (1 - alpha) * result[-1])
    return result


def _bands(values: list[float], period: int = 20) -> tuple[float, float, float] | None:
    if len(values) < period:
        return None
    window = values[-period:]
    mean = sum(window) / period
    variance = sum((value - mean) ** 2 for value in window) / period
    deviation = math.sqrt(variance)
    return mean - 2 * deviation, mean, mean + 2 * deviation


def _macd_histogram(values: list[float]) -> list[float]:
    """MACD(12,26,9) histogram, aligned only where both EMAs exist."""
    fast = _ema(values, 12)
    slow = _ema(values, 26)
    if not fast or not slow:
        return []
    start = 25
    macd = [fast[index - 11] - slow[index - 25] for index in range(start, len(values))]
    signal = _ema(macd, 9)
    if not signal:
        return []
    return [line - sig for line, sig in zip(macd[8:], signal)]


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


def _feature_snapshot(bars: list[Bar], atr: float) -> dict[str, float]:
    """Compact, price-only state at the signal bar; no future bars are used."""
    closes = [bar.close for bar in bars]
    last = bars[-1]
    returns = [(right / left) - 1 for left, right in zip(closes[-21:-1], closes[-20:]) if left > 0]
    volatility = math.sqrt(sum(value * value for value in returns) / len(returns)) if returns else 0.0
    bands = _bands(closes[-20:], 20)
    rsi_values = _rsi(closes, 14)
    macd_values = _macd_histogram(closes)
    ranges = bars[-20:]
    recent_steps = [abs(right - left) for left, right in zip(closes[-11:-1], closes[-10:])]
    directional_efficiency = (abs(closes[-1] - closes[-11]) / sum(recent_steps)
                              if recent_steps and sum(recent_steps) > 0 else 0.0)
    body = last.close - last.opened
    features = {
        "return_1_pct": (closes[-1] / closes[-2] - 1) * 100 if closes[-2] else 0,
        "return_5_pct": (closes[-1] / closes[-6] - 1) * 100 if closes[-6] else 0,
        "return_15_pct": (closes[-1] / closes[-16] - 1) * 100 if closes[-16] else 0,
        "atr_pct": atr / last.close * 100 if last.close else 0,
        "realized_volatility_20_pct": volatility * 100,
        "ema_8_21_gap_pct": (_ema(closes, 8)[-1] / _ema(closes, 21)[-1] - 1) * 100,
        "ema_5_13_gap_pct": (_ema(closes, 5)[-1] / _ema(closes, 13)[-1] - 1) * 100,
        "rsi_14": rsi_values[-1] if rsi_values else 50.0,
        "bollinger_zscore": ((last.close - bands[1]) / ((bands[2] - bands[1]) / 2)
                             if bands and bands[2] != bands[1] else 0.0),
        "macd_histogram_pct": (macd_values[-1] / last.close * 100 if macd_values and last.close else 0.0),
        "range_20_pct": ((max(bar.high for bar in ranges) - min(bar.low for bar in ranges)) / last.close * 100
                         if last.close else 0.0),
        "directional_efficiency_10": directional_efficiency,
        "signal_bar_body_pct": body / last.close * 100 if last.close else 0.0,
        "signal_bar_range_pct": (last.high - last.low) / last.close * 100 if last.close else 0.0,
        "signal_bar_close_location": ((last.close - last.low) / (last.high - last.low)
                                       if last.high > last.low else 0.5),
    }
    return {key: float(value) for key, value in features.items() if math.isfinite(value)}


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
           score: float, bar: Bar, stop_atr: float = 1.5, reward_risk: float = 2.0,
           features: dict[str, float] | None = None) -> Setup | None:
    if not math.isfinite(atr) or atr <= 0:
        return None
    risk = atr * stop_atr
    stop = entry - risk if side == "BUY" else entry + risk
    target = entry + risk * reward_risk if side == "BUY" else entry - risk * reward_risk
    if stop <= 0 or target <= 0:
        return None
    return Setup(strategy, side, entry, stop, target, rationale, score, bar.started_at.isoformat(), features or {})


def evaluate_strategies(bars: Iterable[Bar]) -> list[Setup]:
    """Return deterministic rules that fired on the last completed bar.

    Rules: 8/21 and 5/13 EMA crosses, 20- and 10-bar Donchian breakouts,
    14-period RSI re-entry, 20-period Bollinger re-entry, and MACD(12,26,9)
    histogram crossover. The numeric score is a rule-strength label, not
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
    features = _feature_snapshot(rows, atr)
    last = rows[-1]
    results: list[Setup] = []

    # Compare each EMA pair at the same completed-bar indices.
    for fast_period, slow_period, strategy, score in (
        (8, 21, "ema_8_21_crossover", 65),
        (5, 13, "ema_5_13_crossover", 62),
    ):
        fast, slow = _ema(closes, fast_period), _ema(closes, slow_period)
        previous_fast = _ema(closes[:-1], fast_period)
        previous_slow = _ema(closes[:-1], slow_period)
        if not (fast and slow and previous_fast and previous_slow):
            continue
        side = None
        if previous_fast[-1] <= previous_slow[-1] and fast[-1] > slow[-1]:
            side = "BUY"
        elif previous_fast[-1] >= previous_slow[-1] and fast[-1] < slow[-1]:
            side = "SELL"
        if side:
            setup = _setup(strategy, side, last.close, atr,
                           f"Completed 1m close crossed {('above' if side == 'BUY' else 'below')} the {fast_period}/{slow_period} EMA pair; stop 1.5 ATR, target 2R.",
                           score, last, features=features)
            if setup:
                results.append(setup)

    for period, strategy, score in ((20, "donchian_20_breakout", 70),
                                    (10, "donchian_10_breakout", 64)):
        prior = rows[-(period + 1):-1]
        if len(prior) != period:
            continue
        upper = max(bar.high for bar in prior)
        lower = min(bar.low for bar in prior)
        breakout_extension = (last.close - upper) / atr if last.close > upper else (lower - last.close) / atr if last.close < lower else 0.0
        close_location = features.get("signal_bar_close_location", 0.5)
        side = None
        if (last.close > upper and breakout_extension >= 0.05 and close_location >= 0.60
                and features.get("directional_efficiency_10", 0.0) >= 0.20):
            side = "BUY"
        elif (last.close < lower and breakout_extension >= 0.05 and close_location <= 0.40
                and features.get("directional_efficiency_10", 0.0) >= 0.20):
            side = "SELL"
        if side:
            setup = _setup(strategy, side, last.close, atr,
                           f"Completed 1m close broke the prior {period}-bar {'high' if side == 'BUY' else 'low'} by {breakout_extension:.2f} ATR; close location and 10-bar directional efficiency passed noise filters; stop 1.5 ATR, target 2R.",
                           score, last, features=features)
            if setup:
                results.append(setup)

    # Re-entry uses a band calculated before the previous bar, excluding both
    # signal bars from the threshold.
    prior_bands = _bands(closes[-22:-2], 20)
    if prior_bands:
        lower_band, _, upper_band = prior_bands
        previous_close = closes[-2]
        side = "BUY" if previous_close < lower_band <= last.close else "SELL" if previous_close > upper_band >= last.close else None
        if side:
            setup = _setup("bollinger_20_reentry", side, last.close, atr,
                           f"Price re-entered the prior 20-bar {'lower' if side == 'BUY' else 'upper'} Bollinger band; stop 1.5 ATR, target 2R.",
                           58, last, features=features)
            if setup:
                results.append(setup)

    rsi = _rsi(closes, 14)
    if len(rsi) >= 2:
        previous, current = rsi[-2], rsi[-1]
        side = "BUY" if previous < 30 <= current else "SELL" if previous > 70 >= current else None
        if side:
            threshold = 30 if side == "BUY" else 70
            setup = _setup("rsi_14_reentry", side, last.close, atr,
                           f"RSI(14) re-entered across {threshold} ({current:.1f}) on a completed 1m bar; stop 1.5 ATR, target 2R.",
                           60, last, features=features)
            if setup:
                results.append(setup)

    macd = _macd_histogram(closes)
    if len(macd) >= 2:
        previous, current = macd[-2], macd[-1]
        side = "BUY" if previous <= 0 < current else "SELL" if previous >= 0 > current else None
        if side:
            setup = _setup("macd_12_26_9_crossover", side, last.close, atr,
                           f"MACD(12,26,9) histogram crossed {'above' if side == 'BUY' else 'below'} zero on a completed 1m bar; stop 1.5 ATR, target 2R.",
                           61, last, features=features)
            if setup:
                results.append(setup)
    return results
