"""Live / upcoming games and on-demand pricing for a single game."""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from ..errors import AppError
from ..services.recommendations import generate_for_date
from ..services.schedule import get_schedule
from ..utils import parse_date, parse_float, today_et
from . import current_user, json_body
from .predictions import serialize_prediction

bp = Blueprint("games", __name__, url_prefix="/api/games")
MAX_DAYS = 14


@bp.get("")
@jwt_required()
def list_games():
    user = current_user()
    start = parse_date(request.args.get("start")) or today_et()
    days = int(parse_float(
        request.args.get("days", 7), "days", 1, MAX_DAYS
    ))
    return jsonify(get_schedule(user, start, days, serialize_prediction))


@bp.post("/price")
@jwt_required()
def price_game():
    """Fetch props for one game and run the model on them."""
    current_user()
    data = json_body()
    event_id = str(data.get("event_id") or "")
    game_date = parse_date(data.get("game_date"))
    if not event_id or game_date is None:
        raise AppError("event_id and game_date are required")
    preds = generate_for_date(game_date, event_ids={event_id})
    return jsonify(priced=len(preds))
