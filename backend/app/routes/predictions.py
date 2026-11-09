"""Today's recommended bets for the dashboard."""
from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import jwt_required
from sqlalchemy import select

from ..errors import AppError
from ..extensions import db
from ..models import Bet, Prediction
from ..services.kelly import confidence_label
from ..services.recommendations import generate_for_date
from ..utils import parse_date, today_et
from . import current_user

bp = Blueprint("predictions", __name__, url_prefix="/api/predictions")


def recommended_stake(pred, bankroll):
    cfg = current_app.config
    fraction = min(
        pred.kelly_fraction * cfg["KELLY_MULTIPLIER"],
        cfg["MAX_BET_FRACTION"],
    )
    return round(bankroll * fraction, 2), fraction


def serialize_prediction(pred, user, bet=None):
    cfg = current_app.config
    stake, fraction = recommended_stake(pred, user.bankroll)
    return {
        "id": pred.id,
        "player": pred.player.name,
        "player_id": pred.player_id,
        "team": pred.player.team,
        "opponent": pred.opponent.abbreviation if pred.opponent else None,
        "is_home": pred.is_home,
        "game_date": pred.game_date.isoformat(),
        "stat_type": pred.stat_type,
        "side": pred.side,
        "line": pred.line,
        "predicted_value": pred.predicted_value,
        "edge_pct": round(pred.edge_pct, 2),
        "odds": pred.odds,
        "bookmaker": pred.bookmaker,
        "win_prob": round(pred.win_prob, 4),
        "expected_value": round(pred.expected_value, 4),
        "confidence": confidence_label(pred.win_prob),
        "kelly_fraction": round(pred.kelly_fraction, 4),
        "stake_fraction": round(fraction, 4),
        "recommended_stake": stake,
        "is_recommended": (
            pred.kelly_fraction > 0
            and pred.expected_value >= cfg["MIN_EXPECTED_VALUE"]
        ),
        "bet": (
            {"id": bet.id, "status": bet.status, "outcome": bet.outcome}
            if bet else None
        ),
    }


@bp.get("/today")
@jwt_required()
def today():
    user = current_user()
    game_date = parse_date(request.args.get("date")) or today_et()
    refresh = request.args.get("refresh") == "1"

    def stored():
        return db.session.scalars(
            select(Prediction)
            .where(Prediction.game_date == game_date)
            .order_by(Prediction.expected_value.desc())
        ).all()

    preds, warning = stored(), None
    if refresh or (not preds and game_date == today_et()):
        try:
            generate_for_date(game_date)
            preds = stored()
        except AppError as exc:
            warning = exc.message

    bets = {
        b.prediction_id: b
        for b in db.session.scalars(
            select(Bet).where(
                Bet.user_id == user.id,
                Bet.prediction_id.in_([p.id for p in preds]),
            )
        )
    }
    rows = [serialize_prediction(p, user, bets.get(p.id)) for p in preds]
    return jsonify(
        date=game_date.isoformat(),
        bankroll=round(user.bankroll, 2),
        predictions=rows,
        recommended_count=sum(1 for r in rows if r["is_recommended"]),
        warning=warning,
    )
