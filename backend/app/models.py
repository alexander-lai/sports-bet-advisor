"""Database schema (PostgreSQL). Created with db.create_all().

Spec tables: users, players, game_logs, predictions, bets.
Supporting tables: teams, games (for opponent defence), prop_lines
(parsed sportsbook lines), odds_cache (raw Odds API responses),
sync_state (resumable ingestion) and backtest_runs.
"""
from .extensions import db
from .utils import utcnow

TZ_DATETIME = db.DateTime(timezone=True)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    bankroll = db.Column(db.Float, nullable=False, default=1000.0)
    created_at = db.Column(TZ_DATETIME, nullable=False, default=utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "bankroll": round(self.bankroll, 2),
            "created_at": self.created_at.isoformat(),
        }


class Team(db.Model):
    __tablename__ = "teams"

    id = db.Column(db.Integer, primary_key=True, autoincrement=False)
    abbreviation = db.Column(db.String(8), nullable=False)
    full_name = db.Column(db.String(64), nullable=False)


class Player(db.Model):
    __tablename__ = "players"

    id = db.Column(db.Integer, primary_key=True, autoincrement=False)
    name = db.Column(db.String(128), nullable=False, index=True)
    team = db.Column(db.String(8))
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"))
    position = db.Column(db.String(8))


class Game(db.Model):
    __tablename__ = "games"

    id = db.Column(db.Integer, primary_key=True, autoincrement=False)
    game_date = db.Column(db.Date, nullable=False, index=True)
    season = db.Column(db.Integer, nullable=False, index=True)
    home_team_id = db.Column(db.Integer, db.ForeignKey("teams.id"))
    visitor_team_id = db.Column(db.Integer, db.ForeignKey("teams.id"))
    home_score = db.Column(db.Integer)
    visitor_score = db.Column(db.Integer)
    postseason = db.Column(db.Boolean, nullable=False, default=False)


class GameLog(db.Model):
    __tablename__ = "game_logs"
    __table_args__ = (
        db.UniqueConstraint("player_id", "game_id"),
        db.Index("ix_game_logs_player_date", "player_id", "game_date"),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=False)
    player_id = db.Column(
        db.Integer, db.ForeignKey("players.id"), nullable=False
    )
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"))
    game_date = db.Column(db.Date, nullable=False)
    season = db.Column(db.Integer, nullable=False, index=True)
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"))
    pts = db.Column(db.Integer, nullable=False, default=0)
    reb = db.Column(db.Integer, nullable=False, default=0)
    ast = db.Column(db.Integer, nullable=False, default=0)
    min = db.Column(db.Float, nullable=False, default=0.0)
    is_home = db.Column(db.Boolean, nullable=False)
    opponent_id = db.Column(db.Integer, db.ForeignKey("teams.id"))
    rest_days = db.Column(db.Integer)


class PropLine(db.Model):
    __tablename__ = "prop_lines"
    __table_args__ = (
        db.UniqueConstraint(
            "player_id", "game_date", "stat_type", "bookmaker"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(
        db.Integer, db.ForeignKey("players.id"), nullable=False
    )
    game_date = db.Column(db.Date, nullable=False, index=True)
    stat_type = db.Column(db.String(8), nullable=False)
    line = db.Column(db.Float, nullable=False)
    over_odds = db.Column(db.Float, nullable=False)
    under_odds = db.Column(db.Float, nullable=False)
    bookmaker = db.Column(db.String(32), nullable=False)
    event_id = db.Column(db.String(64))
    source = db.Column(db.String(16), nullable=False, default="live")
    fetched_at = db.Column(TZ_DATETIME, nullable=False, default=utcnow)


class Prediction(db.Model):
    __tablename__ = "predictions"
    __table_args__ = (
        db.UniqueConstraint("player_id", "game_date", "stat_type"),
    )

    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(
        db.Integer, db.ForeignKey("players.id"), nullable=False
    )
    game_date = db.Column(db.Date, nullable=False, index=True)
    stat_type = db.Column(db.String(8), nullable=False)
    predicted_value = db.Column(db.Float, nullable=False)
    line = db.Column(db.Float, nullable=False)
    edge_pct = db.Column(db.Float, nullable=False)
    kelly_fraction = db.Column(db.Float, nullable=False)
    created_at = db.Column(TZ_DATETIME, nullable=False, default=utcnow)
    # Extra context needed to place and grade the bet.
    side = db.Column(db.String(5), nullable=False)
    odds = db.Column(db.Float, nullable=False)
    win_prob = db.Column(db.Float, nullable=False)
    expected_value = db.Column(db.Float, nullable=False)
    is_home = db.Column(db.Boolean)
    opponent_id = db.Column(db.Integer, db.ForeignKey("teams.id"))
    bookmaker = db.Column(db.String(32))

    player = db.relationship("Player", lazy="joined")
    opponent = db.relationship("Team", lazy="joined")


class Bet(db.Model):
    __tablename__ = "bets"
    __table_args__ = (db.UniqueConstraint("user_id", "prediction_id"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    prediction_id = db.Column(
        db.Integer, db.ForeignKey("predictions.id"), nullable=False
    )
    stake = db.Column(db.Float, nullable=False)
    odds = db.Column(db.Float, nullable=False)
    # pending | win | loss | push
    outcome = db.Column(db.String(8), nullable=False, default="pending")
    profit_loss = db.Column(db.Float, nullable=False, default=0.0)
    logged_at = db.Column(TZ_DATETIME, nullable=False, default=utcnow)
    # accepted | rejected. Rejected bets are graded but never count
    # toward bankroll or ROI.
    status = db.Column(db.String(10), nullable=False, default="accepted")
    # Snapshot of the line at log time so later line moves don't
    # change how the bet is graded.
    side = db.Column(db.String(5), nullable=False)
    line = db.Column(db.Float, nullable=False)
    settled_at = db.Column(TZ_DATETIME)

    user = db.relationship("User")
    prediction = db.relationship("Prediction", lazy="joined")


class OddsCache(db.Model):
    __tablename__ = "odds_cache"

    id = db.Column(db.Integer, primary_key=True)
    cache_key = db.Column(db.String(512), unique=True, nullable=False)
    payload = db.Column(db.JSON, nullable=False)
    fetched_at = db.Column(TZ_DATETIME, nullable=False, default=utcnow)


class SyncState(db.Model):
    __tablename__ = "sync_state"

    key = db.Column(db.String(64), primary_key=True)
    value = db.Column(db.Text)
    updated_at = db.Column(TZ_DATETIME, nullable=False, default=utcnow)


class BacktestRun(db.Model):
    __tablename__ = "backtest_runs"

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(TZ_DATETIME, nullable=False, default=utcnow)
    params = db.Column(db.JSON, nullable=False)
    results = db.Column(db.JSON, nullable=False)
