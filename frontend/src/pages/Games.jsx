import { useCallback, useEffect, useState } from 'react';
import { api } from '../api.js';
import BetActions from '../components/BetActions.jsx';
import { Notice } from '../components/StatCard.jsx';
import {
  STAT_LABELS,
  fmtMoney,
  fmtNum,
  fmtPct,
  fmtProb,
} from '../format.js';

const FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'live', label: 'Live' },
  { key: 'today', label: 'Today' },
  { key: 'upcoming', label: 'Upcoming' },
  { key: 'picks', label: 'Has picks' },
];
const LIVE_REFRESH_MS = 30000;

const tipTime = (iso) =>
  iso
    ? new Date(iso).toLocaleTimeString([], {
        hour: 'numeric',
        minute: '2-digit',
      })
    : 'TBD';

const dayLabel = (dateStr, today) => {
  if (dateStr === today) return 'Today';
  const d = new Date(`${dateStr}T12:00:00`);
  return d.toLocaleDateString([], {
    weekday: 'long',
    month: 'short',
    day: 'numeric',
  });
};

function StatusBadge({ game }) {
  if (game.state === 'live') {
    return (
      <span
        className="inline-flex items-center gap-1.5 rounded bg-rose-950
          px-2 py-0.5 text-xs font-semibold text-rose-300"
      >
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-rose-400" />
        LIVE · {game.status_text}
      </span>
    );
  }
  if (game.state === 'final') {
    return <span className="text-xs text-slate-400">{game.status_text}</span>;
  }
  return (
    <span className="text-xs text-slate-300">{tipTime(game.tip_off)}</span>
  );
}

function TeamRow({ team, winner, showScore }) {
  return (
    <div className="flex items-center justify-between">
      <span className={winner ? 'font-semibold' : 'text-slate-300'}>
        {team.name}
      </span>
      {showScore && (
        <span
          className={`tabular-nums ${
            winner ? 'font-semibold' : 'text-slate-400'
          }`}
        >
          {team.score ?? 0}
        </span>
      )}
    </div>
  );
}

function PickRow({ pick, locked, onLogged }) {
  return (
    <div
      className="flex flex-wrap items-center justify-between gap-2
        border-t border-slate-800 py-2 text-sm"
    >
      <div className="min-w-[12rem]">
        <span className="font-medium">{pick.player}</span>{' '}
        <span className="uppercase text-emerald-400">
          {pick.side} {pick.line}
        </span>{' '}
        <span className="text-slate-400">{STAT_LABELS[pick.stat_type]}</span>
        <div className="text-xs text-slate-500">
          proj {fmtNum(pick.predicted_value)} · edge {fmtPct(pick.edge_pct)}
          {' · '}win {fmtProb(pick.win_prob)} ({pick.confidence}) · odds{' '}
          {fmtNum(pick.odds, 2)} · stake {fmtMoney(pick.recommended_stake)}
        </div>
      </div>
      {locked ? (
        pick.bet && (
          <span className="text-xs text-slate-400">
            {pick.bet.status} · {pick.bet.outcome}
          </span>
        )
      ) : (
        <BetActions pred={pick} onLogged={onLogged} />
      )}
    </div>
  );
}

function GameCard({ game, onChanged }) {
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');
  const showScore = game.state !== 'scheduled';
  const homeWins =
    showScore && (game.home.score ?? 0) > (game.away.score ?? 0);
  const awayWins =
    showScore && (game.away.score ?? 0) > (game.home.score ?? 0);

  const findBets = async () => {
    setBusy(true);
    setNote('');
    try {
      const res = await api('/games/price', {
        method: 'POST',
        body: { event_id: game.odds_event_id, game_date: game.date },
      });
      if (res.priced === 0) setNote('No player props posted yet.');
      onChanged();
    } catch (err) {
      setNote(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card space-y-3">
      <div className="flex items-center justify-between">
        <StatusBadge game={game} />
        {game.postseason && (
          <span className="text-xs text-amber-300">Playoffs</span>
        )}
      </div>
      <div className="space-y-1">
        <TeamRow team={game.away} winner={awayWins} showScore={showScore} />
        <TeamRow team={game.home} winner={homeWins} showScore={showScore} />
      </div>

      <div>
        <div className="flex items-center justify-between">
          <span className="text-xs uppercase tracking-wide text-slate-400">
            {game.picks.length
              ? `${game.picks.length} good bet` +
                (game.picks.length > 1 ? 's' : '')
              : game.props_priced
                ? `No edges in ${game.props_priced} props`
                : 'Not priced yet'}
          </span>
          {game.can_price && (
            <button
              className="btn-ghost"
              onClick={findBets}
              disabled={busy}
            >
              {busy
                ? 'Pricing…'
                : game.props_priced
                  ? 'Refresh bets'
                  : 'Find bets'}
            </button>
          )}
        </div>
        {!game.can_price && game.state === 'scheduled' && (
          <p className="mt-1 text-xs text-slate-500">
            No sportsbook lines listed for this game yet.
          </p>
        )}
        {note && <p className="mt-1 text-xs text-amber-300">{note}</p>}
        {game.picks.map((p) => (
          <PickRow
            key={p.id}
            pick={p}
            locked={game.state !== 'scheduled'}
            onLogged={onChanged}
          />
        ))}
      </div>
    </div>
  );
}

export default function Games() {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('all');

  const load = useCallback(async () => {
    try {
      setData(await api('/games?days=7'));
      setError('');
    } catch (err) {
      setError(err.message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const games = data?.games ?? [];
  const anyLive = games.some((g) => g.state === 'live');

  useEffect(() => {
    if (!anyLive) return undefined;
    const id = setInterval(load, LIVE_REFRESH_MS);
    return () => clearInterval(id);
  }, [anyLive, load]);

  const today = data?.start;
  const visible = games.filter((g) => {
    if (filter === 'live') return g.state === 'live';
    if (filter === 'today') return g.date === today;
    if (filter === 'upcoming') return g.state === 'scheduled';
    if (filter === 'picks') return g.picks.length > 0;
    return true;
  });
  const byDate = visible.reduce((acc, g) => {
    (acc[g.date] ||= []).push(g);
    return acc;
  }, {});

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Games</h1>
          <p className="text-sm text-slate-400">
            Live scores and the next 7 days, with the model's best bets
            {anyLive && ' · live scores refresh every 30s'}
          </p>
        </div>
        <button className="btn-ghost" onClick={load}>
          Refresh
        </button>
      </div>

      <div className="flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className={`btn ${
              filter === f.key
                ? 'bg-slate-700 text-white'
                : 'border border-slate-800 text-slate-400 hover:text-white'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {error && <Notice kind="error">{error}</Notice>}
      {data?.warning && <Notice kind="warn">{data.warning}</Notice>}
      {!data && !error && <p className="text-slate-400">Loading…</p>}
      {data && visible.length === 0 && (
        <Notice>No games match this filter.</Notice>
      )}

      {Object.entries(byDate).map(([date, dayGames]) => (
        <section key={date} className="space-y-3">
          <h2 className="text-sm font-semibold text-slate-300">
            {dayLabel(date, today)}{' '}
            <span className="font-normal text-slate-500">
              · {dayGames.length} game{dayGames.length > 1 ? 's' : ''}
            </span>
          </h2>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {dayGames.map((g) => (
              <GameCard key={g.id} game={g} onChanged={load} />
            ))}
          </div>
        </section>
      ))}

      <p className="text-xs text-slate-500">
        Pricing a game fetches its player props from The Odds API (about 3
        credits per game, cached). Games that have started are not priced:
        in-game lines don't match pre-game projections.
      </p>
    </div>
  );
}
