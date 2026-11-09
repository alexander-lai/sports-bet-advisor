"""Model status and retraining."""
from flask import Blueprint, current_app, jsonify
from flask_jwt_extended import jwt_required
from sqlalchemy import func, select

from ..extensions import db
from ..models import GameLog
from ..services.ml import bundle_summary, load_bundle
from ..services.state import get_state
from ..services.training import retrain
from . import current_user

bp = Blueprint("model", __name__, url_prefix="/api/model")


@bp.get("/status")
@jwt_required()
def status():
    current_user()
    seasons = db.session.execute(
        select(GameLog.season, func.count())
        .group_by(GameLog.season)
        .order_by(GameLog.season)
    ).all()
    return jsonify(
        model=bundle_summary(load_bundle(current_app.config["MODEL_DIR"])),
        game_logs={str(season): count for season, count in seasons},
        last_refresh=get_state("last_refresh"),
        seeded_at=get_state("seed_complete"),
    )


@bp.post("/retrain")
@jwt_required()
def retrain_model():
    current_user()
    return jsonify(model=retrain())
