"""Load game logs / games from PostgreSQL into pandas."""
import pandas as pd
from sqlalchemy import select

from ..extensions import db
from ..models import Game, GameLog, PropLine

LOG_COLUMNS = (
    GameLog.player_id,
    GameLog.game_id,
    GameLog.game_date,
    GameLog.season,
    GameLog.team_id,
    GameLog.pts,
    GameLog.reb,
    GameLog.ast,
    GameLog.min,
    GameLog.is_home,
    GameLog.opponent_id,
)
GAME_COLUMNS = (
    Game.game_date,
    Game.home_team_id,
    Game.visitor_team_id,
    Game.home_score,
    Game.visitor_score,
)


def _read(stmt):
    with db.engine.connect() as conn:
        return pd.read_sql(stmt, conn)


def load_frames(player_ids=None, since=None):
    logs_stmt = select(*LOG_COLUMNS)
    games_stmt = select(*GAME_COLUMNS)
    if since is not None:
        logs_stmt = logs_stmt.where(GameLog.game_date >= since)
        games_stmt = games_stmt.where(Game.game_date >= since)
    if player_ids is not None:
        logs_stmt = logs_stmt.where(GameLog.player_id.in_(player_ids))
    return _read(logs_stmt), _read(games_stmt)


def load_prop_lines(start, end):
    stmt = select(
        PropLine.player_id,
        PropLine.game_date,
        PropLine.stat_type,
        PropLine.line,
        PropLine.over_odds,
        PropLine.under_odds,
    ).where(PropLine.game_date.between(start, end))
    df = _read(stmt)
    if not df.empty:
        df["game_date"] = pd.to_datetime(df["game_date"])
        df = df.drop_duplicates(["player_id", "game_date", "stat_type"])
    return df
