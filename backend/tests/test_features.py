import numpy as np
import pandas as pd

from app.services.features import (
    FEATURES,
    engineer,
    training_rows,
    upcoming_rows,
)
from app.services.ml import load_bundle, predict, save_bundle, train_models

from .synthetic import make_data


def _frame():
    _, _, games, logs = make_data()
    return logs, games, engineer(logs, games)


def test_rolling_average_uses_only_prior_games():
    logs, _, frame = _frame()
    pid = int(logs["player_id"].iloc[0])
    player = frame[frame["player_id"] == pid].reset_index(drop=True)
    row = 15
    expected = player["pts"].iloc[row - 10:row].mean()
    assert player.loc[row, "roll_pts"] == expected
    assert np.isnan(player.loc[0, "roll_pts"])


def test_rest_days_and_opponent_rating():
    _, games, frame = _frame()
    assert frame["rest_days"].between(1, 10).all()
    assert frame["opp_def_rating"].notna().all()
    # First game of the dataset: no prior opponent data -> league avg.
    first = frame.sort_values("game_date").iloc[0]
    assert first["opp_def_rating"] > 0


def test_upcoming_rows_build_one_row_per_player():
    logs, games, _ = _frame()
    last = pd.to_datetime(logs["game_date"]).max()
    upcoming = pd.DataFrame([
        {"player_id": 100, "game_date": last + pd.Timedelta(days=2),
         "is_home": True, "opponent_id": 2},
        {"player_id": 200, "game_date": last + pd.Timedelta(days=2),
         "is_home": False, "opponent_id": 1},
    ])
    rows = upcoming_rows(logs, games, upcoming)
    assert sorted(rows["player_id"]) == [100, 200]
    assert rows[FEATURES].notna().all().all()
    assert (rows["rest_days"] >= 1).all()


def test_train_save_load_predict(tmp_path):
    _, _, frame = _frame()
    rows = training_rows(frame)
    bundle = train_models(rows, params={"n_estimators": 50})
    assert set(bundle["models"]) == {"pts", "reb", "ast"}
    assert bundle["seasons"] == [2023, 2024, 2025]
    save_bundle(bundle, tmp_path)
    loaded = load_bundle(tmp_path)
    preds = predict(loaded, rows.head(20))
    assert all(len(v) == 20 and (v >= 0).all() for v in preds.values())
    # The model should at least match a naive rolling average.
    m = bundle["metrics"]["pts"]
    assert m["mae"] < m["baseline_mae"] * 1.1
