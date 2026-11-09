"""Walk-forward backtest on a held-out season.

The model is trained only on seasons before the test season, then
bets are simulated day by day with Kelly sizing.

Lines: real historical sportsbook lines are used when they have been
fetched into prop_lines (see `flask fetch-historical-odds`). Otherwise
a proxy line is used: the player's rolling 10-game average rounded to
the nearest half point, at standard -110 (1.909) pricing. Proxy-line
results measure the model against a naive average, not a real book,
and should be read that way.
"""
import numpy as np
import pandas as pd

from ..errors import AppError
from .data import load_prop_lines
from .features import TARGETS
from .kelly import kelly_fraction_vec, over_probability_vec
from .ml import predict, prediction_sigma, train_models
from .training import build_training_frame

STANDARD_ODDS = 1.909
MAX_DAILY_EXPOSURE = 0.5


def _candidates(test, preds, bundle, lines):
    frames = []
    for stat in TARGETS:
        t = test[["player_id", "game_date", stat, f"roll_{stat}"]].copy()
        t = t.rename(columns={stat: "actual", f"roll_{stat}": "roll"})
        t["stat_type"] = stat
        t["pred"] = preds[stat]
        t["sigma"] = prediction_sigma(bundle, stat, t["pred"].to_numpy())
        proxy = np.floor(t["roll"]) + 0.5
        if not lines.empty:
            real = lines[lines["stat_type"] == stat].drop(
                columns="stat_type"
            )
            t = t.merge(real, on=["player_id", "game_date"], how="left")
        else:
            t["line"] = np.nan
            t["over_odds"] = np.nan
            t["under_odds"] = np.nan
        t["line_source"] = np.where(
            t["line"].notna(), "historical", "proxy"
        )
        t["line"] = t["line"].fillna(proxy)
        t["over_odds"] = t["over_odds"].fillna(STANDARD_ODDS)
        t["under_odds"] = t["under_odds"].fillna(STANDARD_ODDS)
        frames.append(t)
    c = pd.concat(frames, ignore_index=True)

    p_over = over_probability_vec(c["pred"], c["line"], c["sigma"])
    ev_over = p_over * c["over_odds"] - 1
    ev_under = (1 - p_over) * c["under_odds"] - 1
    is_over = ev_over >= ev_under
    c["side"] = np.where(is_over, "over", "under")
    c["p"] = np.where(is_over, p_over, 1 - p_over)
    c["odds"] = np.where(is_over, c["over_odds"], c["under_odds"])
    c["ev"] = np.where(is_over, ev_over, ev_under)
    c["kelly"] = kelly_fraction_vec(c["p"], c["odds"])

    went_over = c["actual"] > c["line"]
    won = np.where(is_over, went_over, ~went_over)
    c["outcome"] = np.where(
        c["actual"] == c["line"], "push", np.where(won, "win", "loss")
    )
    return c


def _sharpe(returns):
    if len(returns) < 2 or np.std(returns, ddof=1) == 0:
        return 0.0
    # Annualised over the number of betting days in the test season.
    return float(
        np.mean(returns) / np.std(returns, ddof=1) * np.sqrt(len(returns))
    )


def _summarize(bets):
    wins = int((bets["outcome"] == "win").sum())
    losses = int((bets["outcome"] == "loss").sum())
    staked = float(bets["stake"].sum())
    profit = float(bets["pnl"].sum())
    flat = np.where(
        bets["outcome"] == "win",
        bets["odds"] - 1,
        np.where(bets["outcome"] == "loss", -1.0, 0.0),
    )
    return {
        "bets": int(len(bets)),
        "wins": wins,
        "losses": losses,
        "pushes": int(len(bets) - wins - losses),
        "win_rate": round(wins / (wins + losses) * 100, 2)
        if wins + losses else 0.0,
        "staked": round(staked, 2),
        "profit": round(profit, 2),
        "roi": round(profit / staked * 100, 2) if staked else 0.0,
        "flat_roi": round(float(flat.mean()) * 100, 2) if len(flat) else 0,
    }


def run_backtest(season, min_ev=0.03, kelly_multiplier=0.5,
                 starting_bankroll=1000.0, max_fraction=0.05,
                 max_bets_per_day=10):
    frame = build_training_frame()
    train = frame[frame["season"] < season]
    test = frame[frame["season"] == season].reset_index(drop=True)
    if test.empty:
        raise AppError(f"No stored game logs for season {season}", 409)
    try:
        bundle = train_models(train)
    except ValueError as exc:
        raise AppError(
            f"Not enough data before season {season}: {exc}", 409
        ) from exc

    preds = predict(bundle, test)
    lines = load_prop_lines(test["game_date"].min(), test["game_date"].max())
    cand = _candidates(test, preds, bundle, lines)

    model_metrics = {}
    for stat in TARGETS:
        rows = cand[cand["stat_type"] == stat]
        model_metrics[stat] = {
            "mae": round(float((rows["pred"] - rows["actual"]).abs()
                               .mean()), 3),
            "baseline_mae": round(float((rows["roll"] - rows["actual"])
                                        .abs().mean()), 3),
        }

    picks = cand[(cand["ev"] >= min_ev) & (cand["kelly"] > 0)]
    picks = picks.sort_values(["game_date", "ev"], ascending=[True, False])
    picks = picks.groupby("game_date").head(max_bets_per_day).copy()

    bankroll = starting_bankroll
    peak, max_drawdown = bankroll, 0.0
    curve, daily_returns, stakes = [], [], np.zeros(len(picks))
    picks = picks.reset_index(drop=True)
    for game_date, day in picks.groupby("game_date"):
        fracs = np.minimum(day["kelly"] * kelly_multiplier, max_fraction)
        total = fracs.sum()
        if total > MAX_DAILY_EXPOSURE:
            fracs = fracs * (MAX_DAILY_EXPOSURE / total)
        day_stakes = (bankroll * fracs).to_numpy()
        stakes[day.index] = day_stakes
        pnl = np.where(
            day["outcome"] == "win",
            day_stakes * (day["odds"] - 1),
            np.where(day["outcome"] == "loss", -day_stakes, 0.0),
        )
        day_profit = float(pnl.sum())
        daily_returns.append(day_profit / bankroll if bankroll else 0.0)
        bankroll += day_profit
        peak = max(peak, bankroll)
        max_drawdown = max(max_drawdown, (peak - bankroll) / peak)
        curve.append({
            "date": game_date.date().isoformat(),
            "bankroll": round(bankroll, 2),
        })
        if bankroll <= 0:
            break
    picks["stake"] = stakes
    picks["pnl"] = np.where(
        picks["outcome"] == "win",
        picks["stake"] * (picks["odds"] - 1),
        np.where(picks["outcome"] == "loss", -picks["stake"], 0.0),
    )
    picks = picks[picks["stake"] > 0]

    summary = _summarize(picks)
    summary.update({
        "sharpe": round(_sharpe(np.array(daily_returns)), 3),
        "starting_bankroll": starting_bankroll,
        "final_bankroll": round(bankroll, 2),
        "bankroll_return": round(
            (bankroll / starting_bankroll - 1) * 100, 2
        ),
        "max_drawdown": round(max_drawdown * 100, 2),
        "betting_days": len(curve),
    })
    sources = picks["line_source"].value_counts().to_dict()
    return {
        "season": season,
        "train_seasons": bundle["seasons"],
        "summary": summary,
        "by_stat": [
            {"stat_type": stat, **_summarize(group)}
            for stat, group in picks.groupby("stat_type")
        ],
        "equity_curve": curve,
        "model_metrics": model_metrics,
        "line_sources": {k: int(v) for k, v in sources.items()},
        "candidates_evaluated": int(len(cand)),
    }
