"""Turn today's sportsbook props into model-backed recommendations."""
import logging
from datetime import datetime, timedelta

import pandas as pd
from flask import current_app
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..errors import AppError
from ..extensions import db
from ..models import Player, Prediction, PropLine, Team
from ..utils import normalize_name, to_eastern_date, utcnow
from .data import load_frames
from .features import upcoming_rows
from .kelly import evaluate_prop
from .ml import load_bundle, predict, prediction_sigma
from .odds_api import OddsApiClient, parse_event_props

log = logging.getLogger(__name__)
HISTORY_DAYS = 400


def require_model():
    bundle = load_bundle(current_app.config["MODEL_DIR"])
    if bundle is None:
        raise AppError(
            "Model is not trained yet. Run the seed script or "
            "POST /api/model/retrain.",
            503,
        )
    return bundle


def _lookup_tables():
    teams = {
        normalize_name(t.full_name): t
        for t in db.session.scalars(select(Team))
    }
    players = {}
    for player in db.session.scalars(select(Player)):
        key = normalize_name(player.name)
        # On a name collision keep the player with a current team.
        if key not in players or players[key].team_id is None:
            players[key] = player
    return teams, players


def save_prop_line(player_id, game_date, prop, event_id, source):
    values = {
        "player_id": player_id,
        "game_date": game_date,
        "stat_type": prop["stat_type"],
        "line": prop["line"],
        "over_odds": prop["over_odds"],
        "under_odds": prop["under_odds"],
        "bookmaker": prop["bookmaker"],
        "event_id": event_id,
        "source": source,
        "fetched_at": utcnow(),
    }
    stmt = pg_insert(PropLine.__table__).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["player_id", "game_date", "stat_type", "bookmaker"],
        set_={
            k: stmt.excluded[k]
            for k in ("line", "over_odds", "under_odds", "fetched_at")
        },
    )
    db.session.execute(stmt)


def match_event_props(event, payload, game_date, teams, players, source):
    """Map an event's props onto known players; store the lines."""
    home = teams.get(normalize_name(event.get("home_team", "")))
    away = teams.get(normalize_name(event.get("away_team", "")))
    if home is None or away is None:
        return []
    cfg = current_app.config
    matched = []
    for prop in parse_event_props(payload, cfg["PREFERRED_BOOKMAKERS"]):
        player = players.get(normalize_name(prop["player_name"]))
        if player is None or player.team_id not in (home.id, away.id):
            continue
        is_home = player.team_id == home.id
        save_prop_line(player.id, game_date, prop, event["id"], source)
        matched.append({
            **prop,
            "player_id": player.id,
            "is_home": is_home,
            "opponent_id": away.id if is_home else home.id,
        })
    return matched


def has_started(event, now=None):
    tip = datetime.fromisoformat(
        event["commence_time"].replace("Z", "+00:00")
    )
    return tip <= (now or utcnow())


def generate_for_date(game_date, client=None, event_ids=None):
    """Price props for a slate (or only `event_ids` on that date).

    Games that have already tipped off are skipped: in-game lines
    would be compared with a pre-game projection.
    """
    bundle = require_model()
    client = client or OddsApiClient.from_config()
    teams, players = _lookup_tables()

    props = []
    for event in client.events():
        if to_eastern_date(event["commence_time"]) != game_date:
            continue
        if event_ids is not None and event["id"] not in event_ids:
            continue
        if has_started(event):
            continue
        payload = client.event_odds(event["id"])
        props += match_event_props(
            event, payload, game_date, teams, players, "live"
        )
    db.session.commit()
    if not props:
        log.info("No matchable props for %s", game_date)
        return []

    upcoming = pd.DataFrame([
        {
            "player_id": p["player_id"],
            "game_date": pd.Timestamp(game_date),
            "is_home": p["is_home"],
            "opponent_id": p["opponent_id"],
        }
        for p in props
    ]).drop_duplicates("player_id")
    logs, games = load_frames(
        player_ids=upcoming["player_id"].tolist(),
        since=game_date - timedelta(days=HISTORY_DAYS),
    )
    # `games` covers every team (only logs are filtered by player).
    logs = logs[pd.to_datetime(logs["game_date"]) < pd.Timestamp(game_date)]
    rows = upcoming_rows(logs, games, upcoming)
    if rows.empty:
        return []
    preds = predict(bundle, rows)
    projected = {}
    for stat, values in preds.items():
        for player_id, value in zip(rows["player_id"], values):
            projected[(int(player_id), stat)] = float(value)

    saved = []
    for prop in props:
        value = projected.get((prop["player_id"], prop["stat_type"]))
        if value is None:
            continue
        sigma = float(prediction_sigma(bundle, prop["stat_type"], value))
        result = evaluate_prop(
            value, prop["line"], sigma,
            prop["over_odds"], prop["under_odds"],
        )
        saved.append(_upsert_prediction(prop, game_date, value, result))
    db.session.commit()
    log.info("Generated %d predictions for %s", len(saved), game_date)
    return saved


def _upsert_prediction(prop, game_date, value, result):
    pred = db.session.scalar(
        select(Prediction).where(
            Prediction.player_id == prop["player_id"],
            Prediction.game_date == game_date,
            Prediction.stat_type == prop["stat_type"],
        )
    )
    if pred is None:
        pred = Prediction(
            player_id=prop["player_id"],
            game_date=game_date,
            stat_type=prop["stat_type"],
        )
        db.session.add(pred)
    pred.predicted_value = round(value, 2)
    pred.line = prop["line"]
    pred.side = result["side"]
    pred.odds = result["odds"]
    pred.win_prob = result["win_prob"]
    pred.expected_value = result["expected_value"]
    pred.kelly_fraction = result["kelly_fraction"]
    pred.edge_pct = result["edge_pct"]
    pred.is_home = prop["is_home"]
    pred.opponent_id = prop["opponent_id"]
    pred.bookmaker = prop["bookmaker"]
    pred.created_at = utcnow()
    return pred
