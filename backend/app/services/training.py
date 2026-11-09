"""Train on every stored game log and persist the model bundle."""
from flask import current_app

from ..errors import AppError
from .data import load_frames
from .features import engineer, training_rows
from .ml import bundle_summary, save_bundle, train_models


def build_training_frame():
    logs, games = load_frames()
    if logs.empty:
        raise AppError("No game logs stored yet; run the seed script", 409)
    return training_rows(engineer(logs, games))


def retrain():
    frame = build_training_frame()
    try:
        bundle = train_models(frame)
    except ValueError as exc:
        raise AppError(str(exc), 409) from exc
    save_bundle(bundle, current_app.config["MODEL_DIR"])
    return bundle_summary(bundle)
