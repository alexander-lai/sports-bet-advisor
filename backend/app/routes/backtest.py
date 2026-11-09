"""Run and fetch backtests."""
from flask import Blueprint, current_app, jsonify
from flask_jwt_extended import jwt_required
from sqlalchemy import select

from ..extensions import db
from ..models import BacktestRun
from ..services.backtest import run_backtest
from ..utils import parse_float
from . import current_user, json_body

bp = Blueprint("backtest", __name__, url_prefix="/api/backtest")


def _run_to_dict(run):
    return {
        "id": run.id,
        "created_at": run.created_at.isoformat(),
        "params": run.params,
        "results": run.results,
    }


@bp.post("")
@jwt_required()
def create():
    current_user()
    cfg = current_app.config
    data = json_body()
    params = {
        "season": int(parse_float(
            data.get("season", cfg["BACKTEST_SEASON"]), "season", 2000, 2100
        )),
        "min_ev": parse_float(data.get("min_ev", 0.03), "min_ev", 0, 1),
        "kelly_multiplier": parse_float(
            data.get("kelly_multiplier", 0.5), "kelly_multiplier", 0, 1
        ),
        "starting_bankroll": parse_float(
            data.get("starting_bankroll", 1000), "starting_bankroll", 1
        ),
        "max_fraction": parse_float(
            data.get("max_fraction", cfg["MAX_BET_FRACTION"]),
            "max_fraction", 0.001, 1,
        ),
        "max_bets_per_day": int(parse_float(
            data.get("max_bets_per_day", 10), "max_bets_per_day", 1, 200
        )),
    }
    results = run_backtest(**params)
    run = BacktestRun(params=params, results=results)
    db.session.add(run)
    db.session.commit()
    return jsonify(_run_to_dict(run)), 201


@bp.get("/latest")
@jwt_required()
def latest():
    current_user()
    run = db.session.scalar(
        select(BacktestRun).order_by(BacktestRun.created_at.desc())
    )
    return jsonify(run=_run_to_dict(run) if run else None)
