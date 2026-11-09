"""Current and upcoming games, with live scores and model picks.

The schedule and scores come from Ball Don't Lie `/games` and are
cached in memory briefly (live scores change by the minute). Each game
is matched to its Odds API event by Eastern date + team names so it
can be priced on demand.
"""
import logging
import threading
import time
from datetime import timedelta

from sqlalchemy import select

from ..errors import AppError
from ..extensions import db
from ..models import Bet, Prediction
from ..utils import normalize_name, to_eastern_date, today_et
from .balldontlie import BallDontLieError
from .ingest import client_from_config
from .odds_api import OddsApiClient

log = logging.getLogger(__name__)

LIVE_TTL_SECONDS = 30
FUTURE_TTL_SECONDS = 600
_cache = {}
_cache_lock = threading.Lock()


def _cached_games(start, end, fetch):
    key = (start, end)
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and hit[0] > now:
            return hit[1]
    games = fetch(start, end)
    ttl = LIVE_TTL_SECONDS if start <= today_et() else FUTURE_TTL_SECONDS
    with _cache_lock:
        _cache[key] = (now + ttl, games)
    return games


def clear_cache():
    with _cache_lock:
        _cache.clear()


def classify(game):
    status = str(game.get("status") or "").strip()
    if status.lower().startswith("final"):
        return "final"
    if (game.get("period") or 0) > 0:
        return "live"
    return "scheduled"


def _tip_off(game):
    for value in (game.get("datetime"), game.get("status")):
        if value and "T" in str(value):
            return str(value)
    return None


def _team(team, score):
    return {
        "id": team["id"],
        "abbreviation": team.get("abbreviation"),
        "name": team.get("full_name") or team.get("name"),
        "score": score,
    }


def normalize_game(game):
    state = classify(game)
    has_score = state != "scheduled"
    clock = str(game.get("time") or "").strip()
    status = str(game.get("status") or "").strip()
    if state == "live":
        status_text = f"{status} {clock}".strip()
    elif state == "final":
        status_text = status
    else:
        status_text = "Scheduled"
    return {
        "id": game["id"],
        "date": str(game["date"])[:10],
        "tip_off": _tip_off(game),
        "state": state,
        "status_text": status_text,
        "period": game.get("period") or 0,
        "postseason": bool(game.get("postseason")),
        "home": _team(
            game["home_team"],
            game.get("home_team_score") if has_score else None,
        ),
        "away": _team(
            game["visitor_team"],
            game.get("visitor_team_score") if has_score else None,
        ),
    }


def _event_key(date_str, home_name, away_name):
    return (date_str, normalize_name(home_name), normalize_name(away_name))


def _odds_events(odds_client):
    """Index Odds API events by (ET date, home, away)."""
    events = {}
    for event in odds_client.events():
        day = to_eastern_date(event["commence_time"]).isoformat()
        key = _event_key(day, event["home_team"], event["away_team"])
        events[key] = event
    return events


def _belongs_to(pred, game):
    """A prediction stores the opponent and venue, which pins its game."""
    if pred.game_date.isoformat() != game["date"]:
        return False
    if pred.is_home:
        return pred.opponent_id == game["away"]["id"]
    return pred.opponent_id == game["home"]["id"]


def get_schedule(user, start, days, serialize, bdl_client=None,
                 odds_client=None):
    """Games from `start` for `days` days, with picks attached.

    `serialize(prediction, user, bet)` renders one prediction so the
    games view and the dashboard show identical rows.
    """
    end = start + timedelta(days=days - 1)
    bdl = bdl_client or client_from_config()
    try:
        raw = _cached_games(start, end, bdl.games)
    except BallDontLieError as exc:
        raise AppError(f"Could not load schedule: {exc}", 502) from exc
    games = sorted(
        (normalize_game(g) for g in raw),
        key=lambda g: (g["date"], g["tip_off"] or "", g["id"]),
    )

    warning = None
    events = {}
    try:
        odds = odds_client or OddsApiClient.from_config()
        events = _odds_events(odds)
    except AppError as exc:
        warning = f"Odds unavailable: {exc.message}"

    preds = db.session.scalars(
        select(Prediction)
        .where(Prediction.game_date.between(start, end))
        .order_by(Prediction.expected_value.desc())
    ).all()
    bets = {
        b.prediction_id: b
        for b in db.session.scalars(
            select(Bet).where(
                Bet.user_id == user.id,
                Bet.prediction_id.in_([p.id for p in preds]),
            )
        )
    }

    for game in games:
        event = events.get(_event_key(
            game["date"], game["home"]["name"], game["away"]["name"]
        ))
        game["odds_event_id"] = event["id"] if event else None
        if event and not game["tip_off"]:
            game["tip_off"] = event["commence_time"]
        rows = [
            serialize(p, user, bets.get(p.id))
            for p in preds if _belongs_to(p, game)
        ]
        game["props_priced"] = len(rows)
        game["picks"] = [r for r in rows if r["is_recommended"]]
        game["can_price"] = (
            game["state"] == "scheduled" and event is not None
        )
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "games": games,
        "warning": warning,
    }
