from datetime import timedelta

from app.services import schedule
from app.services.schedule import classify, normalize_game
from app.utils import today_et

from .test_api import FakeOdds, _seed_db

TEAM_A = {"id": 1, "abbreviation": "T1", "full_name": "Test City A"}
TEAM_B = {"id": 2, "abbreviation": "T2", "full_name": "Test City B"}
TEAM_C = {"id": 3, "abbreviation": "T3", "full_name": "Test City C"}


def _game(gid, day, status, period=0, home=TEAM_A, away=TEAM_B, **kw):
    return {
        "id": gid, "date": day.isoformat(), "status": status,
        "period": period, "time": kw.get("time", ""),
        "home_team": home, "visitor_team": away,
        "home_team_score": kw.get("hs", 0),
        "visitor_team_score": kw.get("vs", 0),
        "postseason": False, "datetime": kw.get("tip"),
    }


class FakeBdl:
    def __init__(self, games):
        self._games = games
        self.calls = 0

    def games(self, start, end):
        self.calls += 1
        return self._games


def test_classify_and_normalize():
    day = today_et()
    live = normalize_game(
        _game(1, day, "3rd Qtr", 3, time="5:32", hs=70, vs=66)
    )
    assert live["state"] == "live"
    assert live["status_text"] == "3rd Qtr 5:32"
    assert live["home"]["score"] == 70
    final = _game(2, day, "Final", 4, hs=101, vs=99)
    assert classify(final) == "final"
    upcoming = normalize_game(
        _game(3, day, "2026-11-10T00:30:00Z", tip=None)
    )
    assert upcoming["state"] == "scheduled"
    assert upcoming["home"]["score"] is None
    assert upcoming["tip_off"] == "2026-11-10T00:30:00Z"


def test_games_endpoint_attaches_picks(app, client, auth, monkeypatch):
    tomorrow = today_et() + timedelta(days=1)
    bdl = FakeBdl([
        _game(10, tomorrow, f"{tomorrow.isoformat()}T23:30:00Z"),
        _game(11, today_et(), "2nd Qtr", 2, home=TEAM_C, away=TEAM_B,
              hs=40, vs=38),
    ])
    odds = FakeOdds(tomorrow)
    schedule.clear_cache()
    monkeypatch.setattr(schedule, "client_from_config", lambda: bdl)
    monkeypatch.setattr(
        schedule.OddsApiClient, "from_config", classmethod(lambda c: odds)
    )
    import app.services.recommendations as recs

    monkeypatch.setattr(
        recs.OddsApiClient, "from_config", classmethod(lambda c: odds)
    )
    with app.app_context():
        _seed_db()
    client.post("/api/model/retrain", headers=auth)

    resp = client.get("/api/games?days=3", headers=auth)
    assert resp.status_code == 200, resp.json
    games = {g["id"]: g for g in resp.json["games"]}
    upcoming, live = games[10], games[11]
    assert upcoming["odds_event_id"] == "evt1" and upcoming["can_price"]
    assert upcoming["picks"] == []
    assert live["state"] == "live" and not live["can_price"]

    priced = client.post("/api/games/price", headers=auth, json={
        "event_id": "evt1", "game_date": tomorrow.isoformat(),
    })
    assert priced.json["priced"] == 1

    again = client.get("/api/games?days=3", headers=auth).json
    picks = {g["id"]: g for g in again["games"]}[10]["picks"]
    assert len(picks) == 1 and picks[0]["player"] == "Player baa"
    assert {g["id"]: g for g in again["games"]}[11]["picks"] == []
    assert bdl.calls == 1  # second request served from cache


def test_price_requires_fields(client, auth):
    resp = client.post("/api/games/price", headers=auth, json={})
    assert resp.status_code == 400
