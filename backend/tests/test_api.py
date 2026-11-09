from datetime import timedelta

import pytest

from app.extensions import db
from app.models import Game, GameLog, Player, Prediction, Team, User
from app.services.ingest import finalize_derived
from app.services.recommendations import generate_for_date
from app.utils import today_et

from .synthetic import make_data


def _seed_db():
    teams, players, games, logs = make_data()
    db.session.add_all(Team(**t) for t in teams)
    db.session.flush()
    db.session.add_all(
        Player(id=p["id"], name=p["name"], position=p["position"])
        for p in players
    )
    db.session.flush()
    db.session.add_all(Game(**g) for g in games.to_dict("records"))
    db.session.flush()
    db.session.add_all(GameLog(**r) for r in logs.to_dict("records"))
    db.session.commit()
    finalize_derived()
    return logs


def test_auth_flow(client, auth):
    assert client.get("/api/auth/me").status_code == 401
    me = client.get("/api/auth/me", headers=auth)
    assert me.json["user"]["bankroll"] == 1000
    dup = client.post("/api/auth/register", json={
        "email": "tester@example.com", "password": "another pass",
    })
    assert dup.status_code == 409
    bad = client.post("/api/auth/login", json={
        "email": "tester@example.com", "password": "wrong password",
    })
    assert bad.status_code == 401
    ok = client.post("/api/auth/login", json={
        "email": "TESTER@example.com", "password": "correct horse",
    })
    assert ok.status_code == 200 and ok.json["access_token"]


def test_retrain_and_backtest(app, client, auth):
    with app.app_context():
        _seed_db()
        player = db.session.get(Player, 100)
        assert player.team_id == 1 and player.team == "T1"
        rest = db.session.scalars(
            db.select(GameLog.rest_days).where(GameLog.player_id == 100)
        ).all()
        assert sum(r is None for r in rest) == 1

    resp = client.post("/api/model/retrain", headers=auth)
    assert resp.status_code == 200, resp.json
    assert resp.json["model"]["trained"]

    status = client.get("/api/model/status", headers=auth).json
    assert set(status["game_logs"]) == {"2023", "2024", "2025"}

    bt = client.post("/api/backtest", headers=auth, json={
        "season": 2025, "min_ev": 0.0, "max_bets_per_day": 5,
    })
    assert bt.status_code == 201, bt.json
    summary = bt.json["results"]["summary"]
    assert bt.json["results"]["train_seasons"] == [2023, 2024]
    assert summary["bets"] > 0
    assert 0 <= summary["win_rate"] <= 100
    assert "sharpe" in summary
    latest = client.get("/api/backtest/latest", headers=auth).json
    assert latest["run"]["id"] == bt.json["id"]


class FakeOdds:
    """Stands in for OddsApiClient."""

    def __init__(self, game_date):
        self.tip = f"{game_date.isoformat()}T23:30:00Z"

    def events(self):
        return [{
            "id": "evt1", "commence_time": self.tip,
            "home_team": "Test City A", "away_team": "Test City B",
        }]

    def event_odds(self, event_id):
        outcomes = [
            {"name": "Over", "description": "Player baa",
             "price": 1.91, "point": 0.5},
            {"name": "Under", "description": "Player baa",
             "price": 1.91, "point": 0.5},
            {"name": "Over", "description": "Unknown Guy",
             "price": 1.91, "point": 10.5},
        ]
        return {"bookmakers": [{
            "key": "draftkings",
            "markets": [{"key": "player_points", "outcomes": outcomes}],
        }]}


def test_predictions_bets_and_settlement(app, client, auth):
    with app.app_context():
        _seed_db()
        client.post("/api/model/retrain", headers=auth)
        # Tip-off must be in the future: started games are skipped.
        game_date = today_et() + timedelta(days=1)
        preds = generate_for_date(game_date, client=FakeOdds(game_date))
        assert len(preds) == 1
        pred = preds[0]
        # A 0.5 point line for a scorer should be a strong over.
        assert pred.side == "over" and pred.kelly_fraction > 0
        pred_id = pred.id

    resp = client.get(
        f"/api/predictions/today?date={game_date.isoformat()}",
        headers=auth,
    )
    assert resp.status_code == 200
    row = resp.json["predictions"][0]
    assert row["is_recommended"] and row["recommended_stake"] <= 50

    bet = client.post("/api/bets", headers=auth, json={
        "prediction_id": pred_id, "decision": "accept", "stake": 20,
    })
    assert bet.status_code == 201, bet.json
    again = client.post("/api/bets", headers=auth, json={
        "prediction_id": pred_id, "decision": "accept", "stake": 20,
    })
    assert again.status_code == 409

    with app.app_context():
        db.session.add(GameLog(
            id=999999, player_id=100, game_date=game_date, season=2026,
            team_id=1, pts=25, reb=5, ast=5, min=30.0, is_home=True,
            opponent_id=2,
        ))
        db.session.commit()
    settled = client.post("/api/bets/settle", headers=auth)
    assert settled.json["settled"] == 1

    history = client.get("/api/bets", headers=auth).json
    assert history["bets"][0]["outcome"] == "win"
    assert history["summary"]["profit"] == pytest.approx(20 * 0.91)
    with app.app_context():
        user = db.session.scalar(db.select(User))
        assert user.bankroll == pytest.approx(1000 + 20 * 0.91)

    # Manual correction moves the bankroll by the difference.
    bet_id = history["bets"][0]["id"]
    fix = client.patch(
        f"/api/bets/{bet_id}", headers=auth, json={"outcome": "loss"}
    )
    assert fix.json["bankroll"] == pytest.approx(980)

    perf = client.get("/api/performance", headers=auth).json
    assert perf["summary"]["bets"] == 1
    assert perf["by_stat"][0]["stat_type"] == "pts"
    assert perf["series"][-1]["cumulative_roi"] == pytest.approx(-100)

    with app.app_context():
        assert db.session.get(Prediction, pred_id).line == 0.5
