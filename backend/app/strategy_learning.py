"""Durable, auditable paper-trade outcomes used for conservative strategy review."""
from __future__ import annotations

import json
import hashlib
import os
import tempfile
from pathlib import Path
from threading import RLock

_lock = RLock()
MIN_ADAPTIVE_SAMPLE = 20


def _read(path: str | Path) -> list[dict]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        rows = payload.get("trades", []) if isinstance(payload, dict) and payload.get("version") == 1 else []
        return [row for row in rows if isinstance(row, dict) and row.get("signal_id")]
    except (OSError, json.JSONDecodeError, TypeError):
        return []


def _write_training_sample(directory: str | Path, row: dict) -> None:
    """Write one immutable, collision-resistant sample for cross-PC sync."""
    if not row.get("signal_id") or not row.get("features"):
        return
    sample = {key: row.get(key) for key in (
        "signal_id", "strategy", "strategy_version", "asset_class", "market_region",
        "currency", "side", "features", "rule_score", "reward_risk", "net_pnl", "closed_at",
    )}
    digest = hashlib.sha256(str(row["signal_id"]).encode("utf-8")).hexdigest()
    target = Path(directory) / "samples" / f"{digest}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(sample, stream, separators=(",", ":"), allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        try:
            target.unlink(missing_ok=True)
        finally:
            raise


def record_outcome(path: str | Path, order: dict, sample_dir: str | Path | None = None) -> None:
    """Append a closed trade once; keep compact decision context with its outcome."""
    evidence = order.get("evidence") if isinstance(order.get("evidence"), dict) else {}
    entry = float(order.get("actual_entry", order.get("entry", 0)) or 0)
    stop = float(order.get("actual_stop_loss", order.get("stop_loss", 0)) or 0)
    pnl = float(order.get("net_pnl", order.get("realised_pnl", 0)) or 0)
    quantity = max(1, int(order.get("quantity", 1) or 1))
    risk = abs(entry - stop) * quantity
    row = {
        "signal_id": str(order.get("signal_id", "")),
        "strategy": str(evidence.get("strategy") or order.get("strategy") or "unspecified"),
        "strategy_version": str(order.get("strategy_version") or evidence.get("strategy_version") or "unversioned"),
        "asset_class": str(order.get("asset_class", "equity")),
        "market_region": str(order.get("market_region", "India")),
        "currency": str(order.get("currency", "INR")),
        "side": str(order.get("side", "")),
        "rationale": str(order.get("rationale", ""))[:4000],
        "decision_factors": evidence.get("decision_factors", []),
        # Only information available at signal time is captured. Keeping the
        # feature vector beside the realized outcome enables later supervised
        # review without inventing historical indicator values.
        "features": evidence.get("features", {}) if isinstance(evidence.get("features"), dict) else {},
        "rule_score": float(order.get("confidence", 0) or 0),
        "reward_risk": (abs(float(order.get("target", 0) or 0) - entry) /
                        abs(entry - stop) if entry != stop else None),
        "entry": entry,
        "exit": float(order.get("actual_exit", 0) or 0),
        "net_pnl": round(pnl, 4),
        "r_multiple": round(pnl / risk, 4) if risk > 0 else None,
        "exit_reason": str(order.get("exit_reason", "")),
        "closed_at": str(order.get("closed_at", "")),
    }
    target = Path(path)
    with _lock:
        rows = _read(target)
        if not any(old.get("signal_id") == row["signal_id"] for old in rows):
            rows.append(row)
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix=".strategy-learning-", suffix=".tmp", dir=target.parent)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump({"version": 1, "trades": rows[-10000:]}, stream, separators=(",", ":"))
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, target)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        if sample_dir:
            _write_training_sample(sample_dir, row)


def summary(path: str | Path) -> dict:
    rows = _read(path)
    trainable = [row for row in rows if isinstance(row.get("features"), dict) and row["features"]]
    groups: dict[tuple[str, str, str], list[dict]] = {}
    for row in rows:
        key = (row.get("strategy", "unspecified"), row.get("asset_class", "equity"), row.get("currency", "INR"))
        groups.setdefault(key, []).append(row)
    strategies = []
    for (strategy, asset_class, currency), trades in sorted(groups.items()):
        pnls = [float(row.get("net_pnl", 0)) for row in trades]
        rs = [float(row["r_multiple"]) for row in trades if row.get("r_multiple") is not None]
        wins = sum(value > 0 for value in pnls)
        strategies.append({
            "strategy": strategy, "asset_class": asset_class, "currency": currency,
            "closed_trades": len(trades), "wins": wins, "losses": sum(value < 0 for value in pnls),
            "win_rate_pct": round(100 * wins / len(trades), 1) if trades else 0,
            "net_pnl": round(sum(pnls), 2), "average_r": round(sum(rs) / len(rs), 3) if rs else None,
            "adaptive_status": _status(len(trades), sum(rs) / len(rs) if rs else None),
        })
    return {"closed_trades": len(rows), "feature_complete_trades": len(trainable), "strategies": strategies,
            "learning_policy": "Descriptive history is always shown. Only after 20 closed trades per strategy does a non-positive average R block autonomous entries; suggestions remain visible for review."}


def cumulative_realised(path: str | Path, currency: str, runtime_orders: list[dict] | None = None) -> float:
    """Return unique realized P&L for an account from durable outcomes and this runtime."""
    rows = _read(path)
    voided = {str(order.get("signal_id", "")) for order in runtime_orders or []
              if order.get("status") == "VOIDED"}
    seen = {row["signal_id"] for row in rows}
    total = sum(float(row.get("net_pnl", 0) or 0) for row in rows
                if row.get("currency") == currency and str(row.get("signal_id", "")) not in voided)
    for order in runtime_orders or []:
        signal_id = str(order.get("signal_id", ""))
        if (order.get("status") == "CLOSED" and order.get("currency", "INR") == currency
                and signal_id not in seen):
            total += float(order.get("net_pnl", order.get("realised_pnl", 0)) or 0)
    return round(total, 2)


def _status(samples: int, average_r: float | None) -> str:
    if samples < MIN_ADAPTIVE_SAMPLE:
        return f"OBSERVE ({samples}/{MIN_ADAPTIVE_SAMPLE})"
    if average_r is not None and average_r <= 0:
        return "AUTONOMOUS ENTRY PAUSED: non-positive historical average R"
    return "MONITOR"


def autonomous_block(path: str | Path, strategy: str, asset_class: str | None = None) -> str | None:
    for item in summary(path)["strategies"]:
        if (item["strategy"] == strategy and (asset_class is None or item["asset_class"] == asset_class)
                and item["closed_trades"] >= MIN_ADAPTIVE_SAMPLE
                and item["adaptive_status"].startswith("AUTONOMOUS ENTRY PAUSED")):
            return item["adaptive_status"]
    return None
