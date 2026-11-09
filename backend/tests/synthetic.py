"""Deterministic fake NBA data for tests."""
from datetime import date, timedelta

import numpy as np
import pandas as pd

N_TEAMS = 6
PLAYERS_PER_TEAM = 5


def _letters(number):
    """Names must survive normalize_name, which drops digits."""
    return "".join(chr(97 + int(d)) for d in str(number))


def make_data(seasons=(2023, 2024, 2025), games_per_season=40, seed=7):
    rng = np.random.default_rng(seed)
    teams = [
        {"id": i + 1, "abbreviation": f"T{i + 1}",
         "full_name": f"Test City {chr(65 + i)}"}
        for i in range(N_TEAMS)
    ]
    players = []
    for t in teams:
        for j in range(PLAYERS_PER_TEAM):
            pid = t["id"] * 100 + j
            players.append({
                "id": pid, "name": f"Player {_letters(pid)}",
                "team_id": t["id"],
                "position": "G", "base": rng.uniform(5, 28),
            })
    games, logs = [], []
    game_id = log_id = 1
    for season in seasons:
        day = date(season, 10, 25)
        for _ in range(games_per_season):
            order = rng.permutation(N_TEAMS) + 1
            for k in range(0, N_TEAMS, 2):
                home, away = int(order[k]), int(order[k + 1])
                scores = {home: 0, away: 0}
                for p in players:
                    if p["team_id"] not in (home, away):
                        continue
                    is_home = p["team_id"] == home
                    pts = int(rng.poisson(p["base"] + (1.5 if is_home
                                                       else 0)))
                    scores[p["team_id"]] += pts
                    logs.append({
                        "id": log_id, "player_id": p["id"],
                        "game_id": game_id, "game_date": day,
                        "season": season, "team_id": p["team_id"],
                        "pts": pts,
                        "reb": int(rng.poisson(p["base"] / 3)),
                        "ast": int(rng.poisson(p["base"] / 4)),
                        "min": float(rng.uniform(20, 38)),
                        "is_home": is_home,
                        "opponent_id": away if is_home else home,
                    })
                    log_id += 1
                games.append({
                    "id": game_id, "game_date": day, "season": season,
                    "home_team_id": home, "visitor_team_id": away,
                    "home_score": scores[home] + 40,
                    "visitor_score": scores[away] + 40,
                    "postseason": False,
                })
                game_id += 1
            day += timedelta(days=int(rng.integers(1, 4)))
    return teams, players, pd.DataFrame(games), pd.DataFrame(logs)
