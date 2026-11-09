"""First-run seeding, the nightly refresh job and the scheduler."""
import logging
import threading

from apscheduler.schedulers.background import BackgroundScheduler
from flask import current_app

from ..config import season_now
from ..errors import AppError
from ..extensions import db
from ..utils import today_et, utcnow
from .bets import settle_pending
from .ingest import (
    client_from_config,
    finalize_derived,
    refresh_season,
    season_done,
    sync_season_stats,
    sync_teams,
)
from .ml import load_bundle
from .recommendations import generate_for_date
from .state import get_state, set_state
from .training import retrain

log = logging.getLogger(__name__)
SEED_KEY = "seed_complete"
_job_lock = threading.Lock()


def is_seeded():
    model = load_bundle(current_app.config["MODEL_DIR"])
    return get_state(SEED_KEY) is not None and model is not None


def run_seed(force=False):
    """Fetch the seed seasons, the current season so far, then train."""
    cfg = current_app.config
    client = client_from_config()
    log.info("Syncing teams")
    sync_teams(client)
    for season in cfg["SEED_SEASONS"]:
        if force or not season_done(season):
            log.info("Fetching season %s-%s", season, (season + 1) % 100)
            sync_season_stats(client, season)
        else:
            log.info("Season %s already stored, skipping", season)
    current = season_now(cfg)
    if current not in cfg["SEED_SEASONS"]:
        log.info("Fetching current season %s so far", current)
        refresh_season(client, current)
    finalize_derived()
    log.info("Training model on all stored game logs")
    summary = retrain()
    set_state(SEED_KEY, utcnow().isoformat())
    db.session.commit()
    log.info("Seed complete: %s rows", summary["n_rows"])
    return summary


def nightly_refresh():
    cfg = current_app.config
    if not _job_lock.acquire(blocking=False):
        log.info("Refresh already running; skipping")
        return
    try:
        refresh_season(client_from_config(), season_now(cfg))
        finalize_derived()
        log.info("Settled %d bets", settle_pending())
        if cfg["NIGHTLY_RETRAIN"]:
            retrain()
        if cfg["ODDS_API_KEY"]:
            try:
                generate_for_date(today_et())
            except AppError as exc:
                log.warning("Skipping predictions: %s", exc.message)
        set_state("last_refresh", utcnow().isoformat())
        db.session.commit()
    finally:
        _job_lock.release()


def start_scheduler(app):
    scheduler = BackgroundScheduler(timezone="UTC", daemon=True)

    def job():
        with app.app_context():
            try:
                nightly_refresh()
            except Exception:  # keep the scheduler alive
                log.exception("Nightly refresh failed")

    scheduler.add_job(
        job,
        "cron",
        hour=app.config["REFRESH_HOUR_UTC"],
        minute=0,
        id="nightly_refresh",
        replace_existing=True,
    )
    scheduler.start()
    log.info(
        "Scheduler started; nightly refresh at %02d:00 UTC",
        app.config["REFRESH_HOUR_UTC"],
    )
    return scheduler
