"""XGBoost models for points / rebounds / assists, persisted with joblib.

A bundle holds one regressor per stat plus an error model: residual
spread grows with the size of the projection, so we model
sigma = k * sqrt(prediction) and fit k on a time-based validation set.
"""
import logging
from pathlib import Path

import joblib
import numpy as np
from xgboost import XGBRegressor

from ..utils import utcnow
from .features import FEATURES, TARGETS

log = logging.getLogger(__name__)

MODEL_FILENAME = "player_props.joblib"
VALIDATION_FRACTION = 0.15
MIN_TRAINING_ROWS = 200
XGB_PARAMS = {
    "n_estimators": 400,
    "learning_rate": 0.05,
    "max_depth": 4,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 5,
    "objective": "reg:squarederror",
    "n_jobs": -1,
    "random_state": 42,
}

_cache = {"path": None, "mtime": None, "bundle": None}


def _split_by_date(frame, fraction):
    dates = np.sort(frame["game_date"].unique())
    cutoff = dates[int(len(dates) * (1 - fraction))]
    return (
        frame[frame["game_date"] < cutoff],
        frame[frame["game_date"] >= cutoff],
    )


def train_models(frame, params=None):
    if len(frame) < MIN_TRAINING_ROWS:
        raise ValueError(
            f"Need at least {MIN_TRAINING_ROWS} rows, got {len(frame)}"
        )
    params = {**XGB_PARAMS, **(params or {})}
    train, valid = _split_by_date(frame, VALIDATION_FRACTION)
    models, sigma_k, metrics = {}, {}, {}
    for stat in TARGETS:
        probe = XGBRegressor(**params)
        probe.fit(train[FEATURES], train[stat])
        pred = np.clip(probe.predict(valid[FEATURES]), 0, None)
        actual = valid[stat].to_numpy(dtype=float)
        resid = actual - pred
        sigma_k[stat] = float(
            np.sqrt(np.mean(resid**2 / np.maximum(pred, 1.0)))
        )
        baseline = valid[f"roll_{stat}"].to_numpy(dtype=float)
        metrics[stat] = {
            "mae": float(np.mean(np.abs(resid))),
            "rmse": float(np.sqrt(np.mean(resid**2))),
            "baseline_mae": float(np.mean(np.abs(actual - baseline))),
            "validation_rows": int(len(valid)),
        }
        final = XGBRegressor(**params)
        final.fit(frame[FEATURES], frame[stat])
        models[stat] = final
        log.info("Trained %s model: %s", stat, metrics[stat])

    seasons = []
    if "season" in frame:
        seasons = sorted(int(s) for s in frame["season"].unique())
    return {
        "models": models,
        "sigma_k": sigma_k,
        "metrics": metrics,
        "features": list(FEATURES),
        "trained_at": utcnow().isoformat(),
        "n_rows": int(len(frame)),
        "seasons": seasons,
    }


def predict(bundle, rows):
    X = rows[bundle["features"]]
    return {
        stat: np.clip(model.predict(X), 0, None)
        for stat, model in bundle["models"].items()
    }


def prediction_sigma(bundle, stat, predicted):
    return bundle["sigma_k"][stat] * np.sqrt(np.maximum(predicted, 1.0))


def model_path(model_dir):
    return Path(model_dir) / MODEL_FILENAME


def save_bundle(bundle, model_dir):
    path = model_path(model_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, path)
    _cache.update(path=None, mtime=None, bundle=None)
    return path


def load_bundle(model_dir):
    path = model_path(model_dir)
    if not path.exists():
        return None
    mtime = path.stat().st_mtime
    if _cache["path"] != path or _cache["mtime"] != mtime:
        _cache.update(path=path, mtime=mtime, bundle=joblib.load(path))
    return _cache["bundle"]


def bundle_summary(bundle):
    if bundle is None:
        return {"trained": False}
    return {
        "trained": True,
        "trained_at": bundle["trained_at"],
        "n_rows": bundle["n_rows"],
        "seasons": bundle["seasons"],
        "metrics": bundle["metrics"],
        "features": bundle["features"],
    }
