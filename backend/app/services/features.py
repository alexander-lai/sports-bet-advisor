"""Feature engineering on player game logs (pure pandas, no DB).

Every feature for a game uses only information available *before*
tip-off: rolling windows are shifted by one game and the opponent's
defensive rating is taken strictly before the game date.
"""
import pandas as pd

TARGETS = ("pts", "reb", "ast")
ROLLING_COLS = ("pts", "reb", "ast", "min")
ROLLING_WINDOW = 10
VENUE_WINDOW = 20
MIN_PRIOR_GAMES = 3
DEFAULT_REST_DAYS = 3
MAX_REST_DAYS = 10
LEAGUE_AVG_POINTS = 114.0

FEATURES = [
    "roll_pts",
    "roll_reb",
    "roll_ast",
    "roll_min",
    "venue_pts",
    "venue_reb",
    "venue_ast",
    "is_home",
    "rest_days",
    "opp_def_rating",
]
REQUIRED = [f"roll_{c}" for c in ROLLING_COLS]


def _shifted_rolling(series, window, min_periods):
    return series.shift(1).rolling(window, min_periods=min_periods).mean()


def team_defense(games):
    """Rolling points allowed per team, known *after* each game.

    Approximates defensive rating as opponent points allowed per game
    over the last ROLLING_WINDOW games.
    """
    cols = ["team_id", "game_date", "def_rating"]
    if games is None or games.empty:
        return pd.DataFrame(columns=cols)
    home = pd.DataFrame({
        "team_id": games["home_team_id"],
        "game_date": games["game_date"],
        "allowed": games["visitor_score"],
    })
    away = pd.DataFrame({
        "team_id": games["visitor_team_id"],
        "game_date": games["game_date"],
        "allowed": games["home_score"],
    })
    df = pd.concat([home, away], ignore_index=True)
    df = df.dropna(subset=["allowed", "team_id"])
    df = df[df["allowed"] > 0].copy()
    df["team_id"] = df["team_id"].astype("int64")
    df["game_date"] = pd.to_datetime(df["game_date"])
    df = df.sort_values(["team_id", "game_date"])
    df["def_rating"] = df.groupby("team_id")["allowed"].transform(
        lambda s: s.rolling(ROLLING_WINDOW, min_periods=1).mean()
    )
    return df[cols].reset_index(drop=True)


def engineer(logs, games):
    """Return logs with FEATURES columns added (targets untouched)."""
    df = logs.copy()
    df["game_date"] = pd.to_datetime(df["game_date"])
    df["is_home"] = df["is_home"].astype(int)
    df["opponent_id"] = df["opponent_id"].astype("int64")
    df = df.sort_values(["player_id", "game_date"]).reset_index(drop=True)

    by_player = df.groupby("player_id", sort=False)
    for col in ROLLING_COLS:
        df[f"roll_{col}"] = by_player[col].transform(
            lambda s: _shifted_rolling(s, ROLLING_WINDOW, MIN_PRIOR_GAMES)
        )

    # Home/away split: the player's recent average at this venue type.
    by_venue = df.groupby(["player_id", "is_home"], sort=False)
    for col in TARGETS:
        venue = by_venue[col].transform(
            lambda s: _shifted_rolling(s, VENUE_WINDOW, 1)
        )
        df[f"venue_{col}"] = venue.fillna(df[f"roll_{col}"])

    rest = by_player["game_date"].diff().dt.days
    df["rest_days"] = rest.fillna(DEFAULT_REST_DAYS).clip(1, MAX_REST_DAYS)

    defense = team_defense(games).rename(columns={"team_id": "opponent_id"})
    df = df.sort_values("game_date")
    if defense.empty:
        df["def_rating"] = float("nan")
        league_avg = LEAGUE_AVG_POINTS
    else:
        df = pd.merge_asof(
            df,
            defense.sort_values("game_date"),
            on="game_date",
            by="opponent_id",
            allow_exact_matches=False,
            direction="backward",
        )
        league_avg = float(defense["def_rating"].mean())
    df["opp_def_rating"] = df["def_rating"].fillna(league_avg)
    df = df.drop(columns="def_rating")
    return df.sort_values(["player_id", "game_date"]).reset_index(drop=True)


def training_rows(frame):
    """Rows with enough history and known outcomes."""
    return frame.dropna(subset=REQUIRED + list(TARGETS)).reset_index(
        drop=True
    )


def upcoming_rows(logs, games, upcoming):
    """Features for games not yet played.

    `upcoming` has columns player_id, game_date, is_home, opponent_id.
    The rows are appended to each player's history so they go through
    exactly the same transformations as training rows.
    """
    base = logs.copy()
    base["_upcoming"] = False
    future = upcoming.copy()
    future["_upcoming"] = True
    frame = engineer(pd.concat([base, future], ignore_index=True), games)
    rows = frame[frame["_upcoming"].astype(bool)]
    return rows.dropna(subset=REQUIRED).reset_index(drop=True)
