"""Bet logging, grading and performance."""
from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required
from sqlalchemy import select

from ..errors import AppError
from ..extensions import db
from ..models import Bet, Prediction
from ..services.bets import (
    OUTCOMES,
    bet_history,
    performance,
    serialize_bet,
    set_outcome,
    settle_pending,
)
from ..utils import parse_float
from . import current_user, json_body
from .predictions import recommended_stake

bp = Blueprint("bets", __name__, url_prefix="/api")


@bp.post("/bets")
@jwt_required()
def log_bet():
    user = current_user()
    data = json_body()
    pred = db.session.get(Prediction, data.get("prediction_id"))
    if pred is None:
        raise AppError("Prediction not found", 404)
    decision = data.get("decision", "accept")
    if decision not in ("accept", "reject"):
        raise AppError("decision must be 'accept' or 'reject'")
    duplicate = db.session.scalar(
        select(Bet).where(
            Bet.user_id == user.id, Bet.prediction_id == pred.id
        )
    )
    if duplicate:
        raise AppError("This prediction is already logged", 409)

    default_stake, _ = recommended_stake(pred, user.bankroll)
    stake = parse_float(
        data.get("stake", default_stake), "stake", 0, max(user.bankroll, 0)
    )
    odds = parse_float(data.get("odds", pred.odds), "odds", 1.01, 1000)
    if decision == "accept" and stake <= 0:
        raise AppError("stake must be positive to accept a bet")
    bet = Bet(
        user_id=user.id,
        prediction_id=pred.id,
        stake=stake,
        odds=odds,
        side=pred.side,
        line=pred.line,
        status="accepted" if decision == "accept" else "rejected",
    )
    db.session.add(bet)
    db.session.commit()
    return jsonify(bet=serialize_bet(bet)), 201


@bp.get("/bets")
@jwt_required()
def list_bets():
    return jsonify(bet_history(current_user().id))


@bp.patch("/bets/<int:bet_id>")
@jwt_required()
def update_bet(bet_id):
    user = current_user()
    bet = db.session.get(Bet, bet_id)
    if bet is None or bet.user_id != user.id:
        raise AppError("Bet not found", 404)
    data = json_body()
    outcome = data.get("outcome", bet.outcome)
    if outcome not in OUTCOMES:
        raise AppError(f"outcome must be one of {', '.join(OUTCOMES)}")
    set_outcome(bet, outcome)
    db.session.commit()
    return jsonify(bet=serialize_bet(bet), bankroll=round(user.bankroll, 2))


@bp.post("/bets/settle")
@jwt_required()
def settle():
    current_user()
    return jsonify(settled=settle_pending())


@bp.get("/performance")
@jwt_required()
def get_performance():
    return jsonify(performance(current_user().id))
