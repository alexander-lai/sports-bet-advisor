# Sports Bet Advisor

A full-stack NBA player-prop advisor. It projects points, rebounds and
assists with XGBoost, compares them with sportsbook lines, sizes bets
with the Kelly criterion, tracks your bets, and backtests the strategy
on a held-out season.

- **Frontend:** React, Tailwind, Recharts (Vite)
- **Backend:** Flask, SQLAlchemy, JWT auth, APScheduler
- **Database:** PostgreSQL
- **ML:** pandas, NumPy, XGBoost, joblib
- **Data:** [Ball Don't Lie](https://www.balldontlie.io) box scores and
  [The Odds API](https://the-odds-api.com) player props

> This is an analytics tool, not financial advice. Projections are noisy,
> and sportsbooks price props well. Bet only what you can afford to lose.

## Setup

### Prerequisites

- Python 3.11+ and Node 18+
- PostgreSQL 14+ running locally (or any `DATABASE_URL`)
- macOS only: XGBoost needs OpenMP (`brew install libomp`)

### 1. Configure

```bash
cp .env.example .env
createdb sports_bet_advisor
```

Edit `.env` and set at least `DATABASE_URL`, `JWT_SECRET` and
`ODDS_API_KEY`. All keys are read from environment variables.

**Ball Don't Lie:** the API now issues keys, and box-score access
(`/stats`) may need a paid tier. Set `BALLDONTLIE_API_KEY` and
`BDL_REQUESTS_PER_MINUTE` to match your plan. If the key is missing or
lacks access, seeding stops with a clear error.

### 2. Backend and first-run seeding

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

On first run, `run.py` runs the seeding script before it starts the API
on port 5000. You can also run the script on its own:

```bash
python seed.py
```

The seeding script:

1. Fetches every game log for 2023-24, 2024-25 and 2025-26
   (`SEED_SEASONS`), plus the current season so far, from Ball Don't Lie.
2. Stores teams, players, games and game logs in PostgreSQL.
3. Engineers features and trains the XGBoost models.
4. Saves the models to `model/player_props.joblib` with joblib.

Seeding is idempotent and resumable. Finished seasons are skipped, and an
interrupted season resumes from its last page. Three seasons is about 800
API pages, which takes roughly 15 minutes at 60 requests/min.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 and register. Vite proxies `/api` to Flask.

## How it works

### Data pipeline

- `services/balldontlie.py` is a rate-limited client with retry and
  backoff. `services/ingest.py` upserts box scores, then recomputes
  `rest_days` and each player's current team in SQL.
- `services/odds_api.py` fetches events and per-event player-prop odds
  (`player_points`, `player_rebounds`, `player_assists`). **Every
  response is cached in the `odds_cache` table.** Live data refreshes
  after `ODDS_CACHE_TTL_MINUTES`; historical snapshots are cached
  forever. The API key is never part of the cache key.
- **Nightly job (APScheduler):** at `REFRESH_HOUR_UTC` it pulls new
  current-season box scores, settles pending bets, optionally retrains,
  and prices the day's props.

### Features (`services/features.py`)

Each feature uses only data from before tip-off:

| Feature | Definition |
|---|---|
| `roll_pts/reb/ast/min` | Previous 10 games (shifted, so no leakage) |
| `venue_pts/reb/ast` | Previous 20 home games or 20 away games |
| `is_home` | Home flag |
| `rest_days` | Days since the player's last game, clipped to 1-10 |
| `opp_def_rating` | Opponent's points allowed per game over its last 10 games, taken strictly before the game date |

Live predictions add the upcoming game to each player's history and run
the same function, so live and training features cannot drift apart.

### Model (`services/ml.py`)

There is one `XGBRegressor` per stat. A time-ordered validation split
(the last 15% of dates) reports MAE against a rolling-average baseline
and fits the error model σ = k·√prediction. The final model is then
refit on all rows.

### Edge, probability and Kelly (`services/kelly.py`)

- `P(over) = 1 − Φ((line − projection) / σ)`
- The side with the higher expected value (`p · odds − 1`) is picked.
- `edge_pct = (projection − line) / line × 100`, signed in the pick's
  favour.
- Kelly: `f = (b·p − q) / b`, where `b = decimal odds − 1` and
  `q = 1 − p`, clamped at 0.
- Recommended stake: `bankroll × min(f × KELLY_MULTIPLIER,
  MAX_BET_FRACTION)`. The 5% default cap keeps full Kelly from sizing
  bets wildly on an overconfident projection.

### Bet tracking

You can accept or reject each recommendation. Accepted bets are graded
automatically from box scores (nightly, or with **Auto-settle**), or you
can set the outcome by hand. Grading moves your bankroll by the profit or
loss. A player with no box score 2 days after the game counts as a push
(void). Rejected bets are graded for reference only and never count
toward ROI.

### Backtesting (`services/backtest.py`)

The backtest trains on the seasons before `BACKTEST_SEASON` (2025-26 by
default) and predicts every game in that season. It then simulates
Kelly-sized betting day by day, taking the top N bets by EV and capping
total daily exposure at 50%. It reports win rate, Kelly ROI, flat-stake
ROI, Sharpe ratio, max drawdown and the equity curve. Sharpe is the mean
over the standard deviation of daily returns, × √(betting days).

**Lines in the backtest.** The Odds API serves historical odds on paid
plans only. Fetch them with:

```bash
flask --app wsgi fetch-historical-odds --start 2025-10-21 --days 7
```

Each event snapshot costs 10 credits per market per region. Where no
historical line is stored, the backtest uses a **proxy line**: the
player's rolling 10-game average rounded to x.5, at -110. Proxy results
show whether the model beats a naive average. They do not show whether
it beats a real book, and the UI says so.

## API

All routes except register and login need `Authorization: Bearer <jwt>`.

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/auth/register`, `/api/auth/login` | Get a JWT |
| GET/PATCH | `/api/auth/me` | Profile and bankroll |
| GET | `/api/predictions/today[?date=&refresh=1]` | Priced props |
| POST/GET | `/api/bets` | Log (accept or reject) and list bets |
| PATCH | `/api/bets/<id>` | Set outcome |
| POST | `/api/bets/settle` | Grade pending bets from box scores |
| GET | `/api/performance` | ROI series, win rate by stat and player |
| GET | `/api/model/status` | Model metrics and stored data |
| POST | `/api/model/retrain` | Retrain on all stored game logs |
| POST | `/api/backtest`, GET `/api/backtest/latest` | Backtests |

CLI commands (run from `backend/`): `flask --app wsgi seed | refresh |
retrain | fetch-historical-odds`.

## Database

The tables are defined in `backend/app/models.py` and created
automatically.

- **Spec tables:** `users`, `players`, `game_logs`, `predictions`, `bets`.
- **Supporting tables:**
  - `teams` and `games`: opponent defence
  - `prop_lines`: parsed book lines, live and historical
  - `odds_cache`: raw Odds API responses
  - `sync_state`: resumable seeding
  - `backtest_runs`
- **Extra columns:**
  - `predictions`: `side`, `odds`, `win_prob` and `expected_value`
  - `bets`: `status`, plus `side` and `line` snapshotted at log time, so
    a line that moves later can't change how the bet is graded

## Tests

```bash
cd backend
createdb sports_bet_advisor_test
.venv/bin/python -m pytest
.venv/bin/flake8
```

The tests use synthetic data. API tests run against the PostgreSQL test
database (`TEST_DATABASE_URL`) and are skipped if it is unreachable.

## Production notes

Run with a single worker (`gunicorn -w 1 wsgi:app`) so the nightly job
isn't scheduled twice. Alternatively, set `ENABLE_SCHEDULER=false` and
run `flask --app wsgi refresh` from cron.
