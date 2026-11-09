"""The Odds API client. Every response is cached in Postgres.

Player-prop markets are only available from the per-event endpoint,
so a slate costs one events call (free) plus one odds call per game.
Historical snapshots never change, so they are cached forever.
"""
import logging
from datetime import timedelta

import requests
from flask import current_app
from sqlalchemy import select

from ..errors import AppError
from ..extensions import db
from ..models import OddsCache
from ..utils import utcnow

log = logging.getLogger(__name__)

BASE_URL = "https://api.the-odds-api.com/v4"
SPORT = "basketball_nba"
MARKETS = {
    "player_points": "pts",
    "player_rebounds": "reb",
    "player_assists": "ast",
}


class OddsApiClient:
    def __init__(self, api_key, ttl_minutes=180, regions="us",
                 timeout=20):
        if not api_key:
            raise AppError("ODDS_API_KEY is not configured", 503)
        self.api_key = api_key
        self.ttl_minutes = ttl_minutes
        self.regions = regions
        self.timeout = timeout

    @classmethod
    def from_config(cls):
        cfg = current_app.config
        return cls(
            cfg["ODDS_API_KEY"],
            ttl_minutes=cfg["ODDS_CACHE_TTL_MINUTES"],
            regions=cfg["ODDS_REGIONS"],
        )

    def _get(self, path, params, ttl_minutes):
        query = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        key = f"{path}?{query}"  # never includes the API key
        row = db.session.scalar(
            select(OddsCache).where(OddsCache.cache_key == key)
        )
        now = utcnow()
        fresh = row is not None and (
            ttl_minutes is None
            or row.fetched_at > now - timedelta(minutes=ttl_minutes)
        )
        if fresh:
            return row.payload
        try:
            resp = requests.get(
                BASE_URL + path,
                params={**params, "apiKey": self.api_key},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            if row is not None:
                log.warning("Odds API unreachable, using stale cache")
                return row.payload
            raise AppError(f"Odds API unreachable: {exc}", 502) from exc
        if resp.status_code != 200:
            if row is not None:
                log.warning("Odds API %s, using stale cache",
                            resp.status_code)
                return row.payload
            raise AppError(
                f"Odds API error {resp.status_code}: {resp.text[:200]}",
                502,
            )
        log.info(
            "Odds API %s (requests remaining: %s)",
            path, resp.headers.get("x-requests-remaining", "?"),
        )
        payload = resp.json()
        if row is None:
            db.session.add(
                OddsCache(cache_key=key, payload=payload, fetched_at=now)
            )
        else:
            row.payload = payload
            row.fetched_at = now
        db.session.commit()
        return payload

    def _odds_params(self):
        return {
            "regions": self.regions,
            "markets": ",".join(MARKETS),
            "oddsFormat": "decimal",
        }

    def events(self):
        return self._get(f"/sports/{SPORT}/events", {}, self.ttl_minutes)

    def event_odds(self, event_id):
        return self._get(
            f"/sports/{SPORT}/events/{event_id}/odds",
            self._odds_params(),
            self.ttl_minutes,
        )

    def historical_events(self, iso_ts):
        body = self._get(
            f"/historical/sports/{SPORT}/events", {"date": iso_ts}, None
        )
        return body.get("data", [])

    def historical_event_odds(self, event_id, iso_ts):
        params = {**self._odds_params(), "date": iso_ts}
        body = self._get(
            f"/historical/sports/{SPORT}/events/{event_id}/odds",
            params,
            None,
        )
        return body.get("data") or {}


def parse_event_props(event, preferred_books=()):
    """Flatten an event's prop markets to one line per player/stat.

    Bookmakers are tried in preference order; the first book with both
    an over and an under price at the same point wins.
    """
    rank = {key: i for i, key in enumerate(preferred_books)}
    books = sorted(
        event.get("bookmakers", []),
        key=lambda b: rank.get(b.get("key"), len(rank)),
    )
    found = {}
    for book in books:
        for market in book.get("markets", []):
            stat = MARKETS.get(market.get("key"))
            if stat is None:
                continue
            sides = {}
            for outcome in market.get("outcomes", []):
                player = outcome.get("description")
                point = outcome.get("point")
                if not player or point is None:
                    continue
                side = str(outcome.get("name", "")).lower()
                sides.setdefault((player, point), {})[side] = outcome[
                    "price"
                ]
            for (player, point), prices in sides.items():
                if (player, stat) in found:
                    continue
                if "over" not in prices or "under" not in prices:
                    continue
                found[(player, stat)] = {
                    "player_name": player,
                    "stat_type": stat,
                    "line": float(point),
                    "over_odds": float(prices["over"]),
                    "under_odds": float(prices["under"]),
                    "bookmaker": book.get("key", "unknown"),
                }
    return list(found.values())
