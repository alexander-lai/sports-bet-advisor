"""Backfill historical prop lines from The Odds API (paid plans only).

Each event-odds snapshot costs 10 credits per market per region, so
this is opt-in and bounded by --days. Snapshots are cached forever.
"""
import logging
from datetime import datetime, timedelta, timezone

from ..extensions import db
from ..utils import to_eastern_date
from .odds_api import OddsApiClient
from .recommendations import _lookup_tables, match_event_props

log = logging.getLogger(__name__)


def _iso(ts):
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_historical_lines(start, days):
    client = OddsApiClient.from_config()
    teams, players = _lookup_tables()
    stored = 0
    for offset in range(days):
        day = start + timedelta(days=offset)
        # 16:00 UTC is before any tip-off on that US date.
        snapshot = datetime(
            day.year, day.month, day.day, 16, tzinfo=timezone.utc
        )
        for event in client.historical_events(_iso(snapshot)):
            if to_eastern_date(event["commence_time"]) != day:
                continue
            tip = datetime.fromisoformat(
                event["commence_time"].replace("Z", "+00:00")
            )
            payload = client.historical_event_odds(
                event["id"], _iso(tip - timedelta(hours=1))
            )
            stored += len(match_event_props(
                event, payload, day, teams, players, "historical"
            ))
        db.session.commit()
        log.info("%s: %d historical lines stored so far", day, stored)
    return stored
