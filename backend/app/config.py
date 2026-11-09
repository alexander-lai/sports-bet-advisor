"""Application configuration, read from environment variables."""
import os
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent

load_dotenv(ROOT_DIR / ".env")
load_dotenv(BACKEND_DIR / ".env")


def _bool(name, default=False):
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _int_list(name, default):
    raw = os.getenv(name, default)
    return [int(x) for x in raw.split(",") if x.strip()]


def _str_list(name, default):
    raw = os.getenv(name, default)
    return [x.strip() for x in raw.split(",") if x.strip()]


def current_nba_season(today=None):
    """Seasons are keyed by start year; they tip off in October."""
    today = today or date.today()
    return today.year if today.month >= 10 else today.year - 1


class Config:
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "postgresql://localhost:5432/sports_bet_advisor"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    JWT_SECRET_KEY = os.getenv("JWT_SECRET", "")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=12)
    CORS_ORIGINS = _str_list("CORS_ORIGINS", "http://localhost:5173")

    # The Odds API
    ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")
    ODDS_CACHE_TTL_MINUTES = int(os.getenv("ODDS_CACHE_TTL_MINUTES", "180"))
    ODDS_REGIONS = os.getenv("ODDS_REGIONS", "us")
    PREFERRED_BOOKMAKERS = _str_list(
        "PREFERRED_BOOKMAKERS", "draftkings,fanduel,betmgm"
    )

    # Ball Don't Lie
    BALLDONTLIE_API_KEY = os.getenv("BALLDONTLIE_API_KEY", "")
    BDL_REQUESTS_PER_MINUTE = int(os.getenv("BDL_REQUESTS_PER_MINUTE", "60"))

    # Seasons (keyed by start year: 2023 means 2023-24)
    SEED_SEASONS = _int_list("SEED_SEASONS", "2023,2024,2025")
    BACKTEST_SEASON = int(os.getenv("BACKTEST_SEASON", "2025"))
    CURRENT_SEASON = (
        int(os.environ["CURRENT_SEASON"])
        if os.getenv("CURRENT_SEASON")
        else None
    )

    # Model + betting
    MODEL_DIR = Path(os.getenv("MODEL_DIR", str(ROOT_DIR / "model")))
    KELLY_MULTIPLIER = float(os.getenv("KELLY_MULTIPLIER", "1.0"))
    MAX_BET_FRACTION = float(os.getenv("MAX_BET_FRACTION", "0.05"))
    MIN_EXPECTED_VALUE = float(os.getenv("MIN_EXPECTED_VALUE", "0.02"))

    # Jobs
    AUTO_SEED = _bool("AUTO_SEED", True)
    ENABLE_SCHEDULER = _bool("ENABLE_SCHEDULER", True)
    REFRESH_HOUR_UTC = int(os.getenv("REFRESH_HOUR_UTC", "9"))
    NIGHTLY_RETRAIN = _bool("NIGHTLY_RETRAIN", False)


def season_now(config):
    return config.get("CURRENT_SEASON") or current_nba_season()
