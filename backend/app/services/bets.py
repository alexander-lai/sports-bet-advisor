"""Bet grading, bankroll updates and performance aggregation."""
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import select

from ..extensions import db
from ..models import Bet, GameLog
from ..utils import today_et, utcnow
from .kelly import grade, profit_for

OUTCOMES = ("pending", "win", "loss", "push")
VOID_AFTER_DAYS = 2


def set_outcome(bet, outcome):
    """Grade a bet; accepted bets move the user's bankroll by the delta."""
    new_pl = profit_for(outcome, bet.stake, bet.odds)
    if bet.status == "accepted":
        bet.user.bankroll += new_pl - (bet.profit_loss or 0.0)
    bet.profit_loss = new_pl
    bet.outcome = outcome
    bet.settled_at = None if outcome == "pending" else utcnow()


def settle_pending(today=None):
    """Grade pending bets from stored box scores.

    A player with no box score VOID_AFTER_DAYS after the game (DNP)
    is graded as a push, like a voided prop.
    """
    today = today or today_et()
    settled = 0
    pending = db.session.scalars(
        select(Bet).where(Bet.outcome == "pending")
    ).all()
    for bet in pending:
        pred = bet.prediction
        log = db.session.scalar(
            select(GameLog).where(
                GameLog.player_id == pred.player_id,
                GameLog.game_date == pred.game_date,
            )
        )
        if log is not None:
            actual = getattr(log, pred.stat_type)
            set_outcome(bet, grade(bet.side, bet.line, actual))
        elif pred.game_date < today - timedelta(days=VOID_AFTER_DAYS):
            set_outcome(bet, "push")
        else:
            continue
        settled += 1
    db.session.commit()
    return settled


def serialize_bet(bet):
    pred = bet.prediction
    return {
        "id": bet.id,
        "prediction_id": pred.id,
        "player": pred.player.name,
        "team": pred.player.team,
        "opponent": pred.opponent.abbreviation if pred.opponent else None,
        "game_date": pred.game_date.isoformat(),
        "stat_type": pred.stat_type,
        "side": bet.side,
        "line": bet.line,
        "predicted_value": pred.predicted_value,
        "edge_pct": round(pred.edge_pct, 2),
        "stake": round(bet.stake, 2),
        "odds": bet.odds,
        "status": bet.status,
        "outcome": bet.outcome,
        "profit_loss": round(bet.profit_loss, 2),
        "logged_at": bet.logged_at.isoformat(),
    }


def bet_history(user_id):
    """All bets, oldest first, with running ROI over settled accepts."""
    bets = db.session.scalars(
        select(Bet).where(Bet.user_id == user_id).order_by(Bet.logged_at)
    ).all()
    staked = profit = 0.0
    rows = []
    for bet in bets:
        row = serialize_bet(bet)
        counts = bet.status == "accepted" and bet.outcome != "pending"
        if counts:
            staked += bet.stake
            profit += bet.profit_loss
        row["running_roi"] = round(profit / staked * 100, 2) if staked else 0
        rows.append(row)
    summary = _summarize([
        b for b in bets
        if b.status == "accepted" and b.outcome != "pending"
    ])
    summary["pending"] = sum(
        1 for b in bets if b.status == "accepted" and b.outcome == "pending"
    )
    return {"bets": rows[::-1], "summary": summary}


def _summarize(bets):
    wins = sum(1 for b in bets if b.outcome == "win")
    losses = sum(1 for b in bets if b.outcome == "loss")
    staked = sum(b.stake for b in bets)
    profit = sum(b.profit_loss for b in bets)
    decided = wins + losses
    return {
        "bets": len(bets),
        "wins": wins,
        "losses": losses,
        "pushes": len(bets) - decided,
        "win_rate": round(wins / decided * 100, 2) if decided else 0.0,
        "staked": round(staked, 2),
        "profit": round(profit, 2),
        "roi": round(profit / staked * 100, 2) if staked else 0.0,
    }


def performance(user_id, top_players=15):
    bets = db.session.scalars(
        select(Bet)
        .where(
            Bet.user_id == user_id,
            Bet.status == "accepted",
            Bet.outcome != "pending",
        )
        .order_by(Bet.logged_at)
    ).all()

    series, staked, profit = [], 0.0, 0.0
    for bet in bets:
        staked += bet.stake
        profit += bet.profit_loss
        series.append({
            "date": bet.prediction.game_date.isoformat(),
            "bet_id": bet.id,
            "cumulative_profit": round(profit, 2),
            "cumulative_roi": round(profit / staked * 100, 2),
        })

    by_stat, by_player = defaultdict(list), defaultdict(list)
    for bet in bets:
        by_stat[bet.prediction.stat_type].append(bet)
        by_player[bet.prediction.player.name].append(bet)

    stat_rows = [
        {"stat_type": stat, **_summarize(group)}
        for stat, group in sorted(by_stat.items())
    ]
    player_rows = sorted(
        ({"player": name, **_summarize(group)}
         for name, group in by_player.items()),
        key=lambda r: r["bets"],
        reverse=True,
    )[:top_players]
    return {
        "summary": _summarize(bets),
        "series": series,
        "by_stat": stat_rows,
        "by_player": player_rows,
    }
