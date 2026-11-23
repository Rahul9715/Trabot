"""Manual, offline baseline trainer for feature-complete paper outcomes.

The fitted artifact is for shadow evaluation only. Nothing in this module is
called by strategy entry or risk-decision code.
"""
from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
import math
import os
from pathlib import Path
import tempfile
from threading import Lock
from typing import Any
from uuid import uuid4

from .strategy_learning import _read

MIN_TRAINING_SAMPLES = 40
MIN_CLASS_SAMPLES = 10
_training_lock = Lock()
_NUMERIC_BASE = ("rule_score", "reward_risk")
_CATEGORICAL = ("strategy", "asset_class", "market_region", "currency", "side")


def _clean_row(row: dict[str, Any]) -> dict[str, Any] | None:
    features = row.get("features")
    try:
        pnl = float(row.get("net_pnl"))
        if not math.isfinite(pnl) or not isinstance(features, dict) or not features:
            return None
        clean = {name: str(row.get(name, "unknown")) for name in _CATEGORICAL}
        numeric_features = {name: float(value) for name, value in features.items()
                            if isinstance(value, (int, float)) and math.isfinite(float(value))}
        if not numeric_features:
            return None
        clean.update(numeric_features)
        clean["rule_score"] = float(row.get("rule_score", 0) or 0)
        reward_risk = row.get("reward_risk")
        clean["reward_risk"] = float(reward_risk) if reward_risk is not None else None
        clean["label"] = int(pnl > 0)
        clean["closed_at"] = str(row.get("closed_at", ""))
        clean["signal_id"] = str(row.get("signal_id", ""))
        return clean
    except (TypeError, ValueError, OverflowError):
        return None


def _manifest_path(root: Path) -> Path:
    return root / "latest_model.json"


def _dataset_rows(outcome_path: str | Path, model_dir: str | Path) -> list[dict[str, Any]]:
    """Merge the local history with immutable shared per-trade sample files."""
    merged: dict[str, dict[str, Any]] = {}
    for row in _read(outcome_path):
        signal_id = str(row.get("signal_id", ""))
        if signal_id:
            merged[signal_id] = row
    sample_dir = Path(model_dir) / "samples"
    try:
        files = sample_dir.glob("*.json")
        for sample_path in files:
            try:
                sample = json.loads(sample_path.read_text(encoding="utf-8"))
                signal_id = str(sample.get("signal_id", "")) if isinstance(sample, dict) else ""
                if not signal_id:
                    continue
                existing = merged.get(signal_id)
                if existing is None or not existing.get("features"):
                    merged[signal_id] = sample
            except (OSError, json.JSONDecodeError, AttributeError):
                continue
    except OSError:
        pass
    return list(merged.values())


def status(outcome_path: str | Path, model_dir: str | Path) -> dict[str, Any]:
    root = Path(model_dir)
    all_rows = _dataset_rows(outcome_path, root)
    samples = [value for row in all_rows if (value := _clean_row(row)) is not None]
    wins = sum(row["label"] for row in samples)
    losses = len(samples) - wins
    latest = None
    try:
        latest = json.loads(_manifest_path(root).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    sklearn_available = importlib.util.find_spec("sklearn") is not None
    dependency_error = None if sklearn_available else "Install backend requirements to enable local model training."
    ready = (len(samples) >= MIN_TRAINING_SAMPLES and wins >= MIN_CLASS_SAMPLES
             and losses >= MIN_CLASS_SAMPLES and sklearn_available)
    return {
        "status": "READY_TO_TRAIN" if ready else "DEPENDENCY_MISSING" if not sklearn_available
                  else "COLLECTING_DATA" if len(samples) < MIN_TRAINING_SAMPLES
                  else "NEEDS_BOTH_OUTCOMES" if min(wins, losses) < MIN_CLASS_SAMPLES else "DEPENDENCY_MISSING",
        "sample_count": len(samples), "all_closed_outcomes": len(all_rows),
        "wins": wins, "losses": losses, "minimum_samples": MIN_TRAINING_SAMPLES,
        "minimum_per_outcome": MIN_CLASS_SAMPLES, "samples_needed": max(0, MIN_TRAINING_SAMPLES - len(samples)),
        "training_available": ready, "sklearn_available": sklearn_available,
        "dependency_error": dependency_error, "model_dir": str(root),
        "outcome_store": str(outcome_path), "latest_model": latest,
        "mode": "shadow_only", "used_for_trade_decisions": False,
    }


def _atomic_json(target: Path, payload: dict[str, Any]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".model-metrics-", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def train(outcome_path: str | Path, model_dir: str | Path) -> dict[str, Any]:
    """Fit and chronologically evaluate a regularized logistic baseline."""
    with _training_lock:
        current = status(outcome_path, model_dir)
        if not current["training_available"]:
            return {**current, "trained": False,
                    "message": current["dependency_error"] or
                    f"Need {current['samples_needed']} more feature-complete outcomes and at least "
                    f"{MIN_CLASS_SAMPLES} wins and losses; no model was trained."}
        try:
            import joblib
            import numpy as np
            from sklearn.compose import ColumnTransformer
            from sklearn.impute import SimpleImputer
            from sklearn.linear_model import LogisticRegression
            from sklearn.metrics import accuracy_score, brier_score_loss, roc_auc_score
            from sklearn.pipeline import Pipeline
            from sklearn.preprocessing import OneHotEncoder, StandardScaler
        except ImportError as exc:
            return {**current, "status": "DEPENDENCY_MISSING", "trained": False,
                    "message": f"Model-training dependency is missing: {exc}"}

        rows = [_clean_row(row) for row in _dataset_rows(outcome_path, model_dir)]
        rows = [row for row in rows if row]
        rows.sort(key=lambda row: (row["closed_at"], row["signal_id"]))
        columns = list(_NUMERIC_BASE) + sorted({key for row in rows for key in row
                                                  if key not in {*_NUMERIC_BASE, *_CATEGORICAL,
                                                                 "label", "closed_at", "signal_id"}})
        n_train = max(1, min(len(rows) - 1, int(len(rows) * 0.8)))
        training, holdout = rows[:n_train], rows[n_train:]
        x_train = [{key: row.get(key) for key in [*columns, *_CATEGORICAL]} for row in training]
        x_test = [{key: row.get(key) for key in [*columns, *_CATEGORICAL]} for row in holdout]
        y_train = np.asarray([row["label"] for row in training], dtype=int)
        y_test = np.asarray([row["label"] for row in holdout], dtype=int)
        if len(set(y_train)) < 2:
            return {**current, "status": "NEEDS_BOTH_OUTCOMES_IN_TRAINING_WINDOW", "trained": False,
                    "message": "The older training window has only one outcome class. Collect more varied paper outcomes."}

        numeric_pipe = Pipeline([("impute", SimpleImputer(strategy="median", keep_empty_features=True)),
                                 ("scale", StandardScaler())])
        category_pipe = Pipeline([("impute", SimpleImputer(strategy="most_frequent")),
                                  ("encode", OneHotEncoder(handle_unknown="ignore"))])
        preprocessing = ColumnTransformer([("numeric", numeric_pipe, columns),
                                            ("category", category_pipe, list(_CATEGORICAL))])
        model = Pipeline([("features", preprocessing),
                          ("classifier", LogisticRegression(C=0.25, class_weight="balanced",
                                                             max_iter=1000, random_state=17))])
        model.fit(x_train, y_train)
        probabilities = model.predict_proba(x_test)[:, 1]
        predictions = (probabilities >= 0.5).astype(int)
        metrics: dict[str, Any] = {
            "holdout_samples": len(holdout), "holdout_wins": int(y_test.sum()),
            "holdout_losses": int(len(y_test) - y_test.sum()),
            "accuracy": round(float(accuracy_score(y_test, predictions)), 4),
            "brier_score": round(float(brier_score_loss(y_test, probabilities)), 4),
            "roc_auc": round(float(roc_auc_score(y_test, probabilities)), 4)
                       if len(set(y_test.tolist())) == 2 else None,
            "split": "chronological 80% train / 20% holdout; no shuffle",
        }
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        model_id = f"paper-logistic-{stamp}-{uuid4().hex[:8]}"
        root = Path(model_dir)
        model_path = root / "models" / model_id / "model.joblib"
        metrics_path = root / "models" / model_id / "metrics.json"
        model_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".model-", suffix=".tmp", dir=model_path.parent)
        os.close(fd)
        try:
            joblib.dump(model, temporary)
            os.replace(temporary, model_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        metadata = {
            "model_id": model_id, "created_at": datetime.now(timezone.utc).isoformat(),
            "training_samples": len(training), "total_feature_complete_samples": len(rows),
            "numeric_features": columns, "categorical_features": list(_CATEGORICAL),
            "target": "net_pnl > 0", "metrics": metrics,
            "mode": "shadow_only", "used_for_trade_decisions": False,
            "model_file": str(model_path),
        }
        _atomic_json(metrics_path, metadata)
        _atomic_json(_manifest_path(root), metadata)
        return {**status(outcome_path, model_dir), "trained": True, "latest_model": metadata,
                "message": "Baseline trained and evaluated on a chronological holdout. Shadow only; it does not affect suggestions, approvals, or trades."}
