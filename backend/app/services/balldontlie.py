"""Minimal Ball Don't Lie (NBA) API client with rate limiting."""
import logging
import time

import requests

log = logging.getLogger(__name__)

BASE_URL = "https://api.balldontlie.io/v1"
PAGE_SIZE = 100


class BallDontLieError(RuntimeError):
    pass


class BallDontLieClient:
    def __init__(self, api_key="", requests_per_minute=60, timeout=30,
                 max_retries=6, session=None):
        self.session = session or requests.Session()
        if api_key:
            self.session.headers["Authorization"] = api_key
        self.min_interval = 60.0 / max(requests_per_minute, 1)
        self.timeout = timeout
        self.max_retries = max_retries
        self._last_request = 0.0

    def _throttle(self):
        wait = self.min_interval - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def _get(self, path, params=None):
        for attempt in range(self.max_retries):
            self._throttle()
            try:
                resp = self.session.get(
                    BASE_URL + path, params=params, timeout=self.timeout
                )
            except requests.RequestException as exc:
                log.warning("BDL request failed (%s), retrying", exc)
                time.sleep(2**attempt)
                continue
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code in (401, 403):
                raise BallDontLieError(
                    f"Ball Don't Lie returned {resp.status_code} for "
                    f"{path}. The API now requires a key and some "
                    "endpoints (e.g. /stats) need a paid tier; set "
                    "BALLDONTLIE_API_KEY."
                )
            if resp.status_code == 429 or resp.status_code >= 500:
                delay = _retry_after(resp, default=5 * 2**attempt)
                log.warning(
                    "BDL %s on %s; sleeping %.0fs",
                    resp.status_code, path, delay,
                )
                time.sleep(delay)
                continue
            raise BallDontLieError(
                f"BDL {resp.status_code} on {path}: {resp.text[:200]}"
            )
        raise BallDontLieError(f"Gave up on {path} after retries")

    def teams(self):
        return self._get("/teams").get("data", [])

    def games(self, start_date, end_date):
        """Every game (scheduled, live or final) in a date range."""
        params = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "per_page": PAGE_SIZE,
        }
        games = []
        while True:
            body = self._get("/games", params)
            games += body.get("data", [])
            cursor = (body.get("meta") or {}).get("next_cursor")
            if not cursor:
                return games
            params["cursor"] = cursor

    def iter_stat_pages(self, season, start_date=None, cursor=None):
        """Yield (rows, next_cursor) for every page of box scores."""
        params = {"seasons[]": season, "per_page": PAGE_SIZE}
        if start_date is not None:
            params["start_date"] = start_date.isoformat()
        while True:
            if cursor:
                params["cursor"] = cursor
            body = self._get("/stats", params)
            cursor = (body.get("meta") or {}).get("next_cursor")
            yield body.get("data", []), cursor
            if not cursor:
                return


def _retry_after(resp, default):
    try:
        return float(resp.headers.get("Retry-After", default))
    except (TypeError, ValueError):
        return default
