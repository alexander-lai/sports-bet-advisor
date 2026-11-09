"""Load Ball Don't Lie box scores into PostgreSQL (idempotent upserts)."""
import logging
from datetime import date, timedelta

from flask import current_app
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..extensions import db
from ..models import Game, GameLog, Player, Team
from ..utils import parse_minutes
from .balldontlie import BallDontLieClient
from .state import delete_state, get_state, set_state

log = logging.getLogger(__name__)


def client_from_config():
    cfg = current_app.config
    return BallDontLieClient(
        api_key=cfg["BALLDONTLIE_API_KEY"],
        requests_per_minute=cfg["BDL_REQUESTS_PER_MINUTE"],
    )


def _upsert(model, rows, key="id", update=()):
    if not rows:
        return
    stmt = pg_insert(model.__table__).values(rows)
    if update:
        stmt = stmt.on_conflict_do_update(
            index_elements=[key],
            set_={col: stmt.excluded[col] for col in update},
        )
    else:
        stmt = stmt.on_conflict_do_nothing(index_elements=[key])
    db.session.execute(stmt)


def _team_row(team):
    return {
        "id": team["id"],
        "abbreviation": team.get("abbreviation") or "",
        "full_name": team.get("full_name") or team.get("name") or "",
    }


def sync_teams(client):
    rows = [_team_row(t) for t in client.teams()]
    _upsert(Team, rows, update=("abbreviation", "full_name"))
    db.session.commit()
    return len(rows)


def store_stat_rows(rows):
    """Upsert one page of /stats rows. Returns game logs stored."""
    teams, players, games, logs = {}, {}, {}, {}
    for row in rows:
        game = row.get("game")
        player = row.get("player")
        team = row.get("team")
        if not (game and player and team):
            continue
        minutes = parse_minutes(row.get("min"))
        if minutes <= 0:
            continue  # did not play
        game_date = date.fromisoformat(game["date"][:10])
        home_id, away_id = game["home_team_id"], game["visitor_team_id"]
        is_home = team["id"] == home_id
        teams[team["id"]] = _team_row(team)
        players[player["id"]] = {
            "id": player["id"],
            "name": f"{player['first_name']} {player['last_name']}".strip(),
            "position": player.get("position") or None,
        }
        games[game["id"]] = {
            "id": game["id"],
            "game_date": game_date,
            "season": game["season"],
            "home_team_id": home_id,
            "visitor_team_id": away_id,
            "home_score": game.get("home_team_score"),
            "visitor_score": game.get("visitor_team_score"),
            "postseason": bool(game.get("postseason")),
        }
        logs[row["id"]] = {
            "id": row["id"],
            "player_id": player["id"],
            "game_id": game["id"],
            "game_date": game_date,
            "season": game["season"],
            "team_id": team["id"],
            "pts": row.get("pts") or 0,
            "reb": row.get("reb") or 0,
            "ast": row.get("ast") or 0,
            "min": round(minutes, 2),
            "is_home": is_home,
            "opponent_id": away_id if is_home else home_id,
        }
    _upsert(Team, list(teams.values()), update=("abbreviation",))
    _upsert(Player, list(players.values()), update=("name", "position"))
    _upsert(
        Game,
        list(games.values()),
        update=("home_score", "visitor_score"),
    )
    _upsert(
        GameLog,
        list(logs.values()),
        update=("pts", "reb", "ast", "min"),
    )
    return len(logs)


def sync_season_stats(client, season, start_date=None):
    """Fetch a season of box scores. Full syncs resume from a cursor."""
    resumable = start_date is None
    cursor_key = f"stats_cursor:{season}"
    cursor = get_state(cursor_key) if resumable else None
    if cursor:
        log.info("Resuming season %s from cursor %s", season, cursor)
    total = pages = 0
    pager = client.iter_stat_pages(season, start_date, cursor or None)
    for rows, next_cursor in pager:
        total += store_stat_rows(rows)
        pages += 1
        if resumable:
            set_state(cursor_key, str(next_cursor or ""))
        db.session.commit()
        if pages % 10 == 0:
            log.info("Season %s: %d pages, %d logs", season, pages, total)
    if resumable:
        delete_state(cursor_key)
        set_state(f"stats_done:{season}", "1")
        db.session.commit()
    log.info("Season %s synced: %d game logs", season, total)
    return total


def season_done(season):
    return get_state(f"stats_done:{season}") == "1"


def refresh_season(client, season):
    """Incremental update: re-pull from two days before the last game."""
    last = db.session.scalar(
        select(func.max(GameLog.game_date)).where(GameLog.season == season)
    )
    start = last - timedelta(days=2) if last else None
    if start is None and season_done(season):
        return 0
    if start is None:
        return sync_season_stats(client, season)
    return sync_season_stats(client, season, start_date=start)


REST_DAYS_SQL = text("""
UPDATE game_logs g SET rest_days = s.rd
FROM (
    SELECT id, game_date - LAG(game_date) OVER (
        PARTITION BY player_id ORDER BY game_date
    ) AS rd
    FROM game_logs
) s
WHERE g.id = s.id AND g.rest_days IS DISTINCT FROM s.rd
""")

PLAYER_TEAM_SQL = text("""
UPDATE players p SET team_id = s.team_id, team = t.abbreviation
FROM (
    SELECT DISTINCT ON (player_id) player_id, team_id
    FROM game_logs ORDER BY player_id, game_date DESC
) s
JOIN teams t ON t.id = s.team_id
WHERE p.id = s.player_id
  AND p.team_id IS DISTINCT FROM s.team_id
""")


def finalize_derived():
    """Recompute rest days and each player's current team."""
    db.session.execute(REST_DAYS_SQL)
    db.session.execute(PLAYER_TEAM_SQL)
    db.session.commit()
