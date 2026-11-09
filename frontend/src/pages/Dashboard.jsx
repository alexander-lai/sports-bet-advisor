import { useCallback, useEffect, useState } from 'react';
import { api } from '../api.js';
import StatCard, { Notice } from '../components/StatCard.jsx';
import {
  STAT_LABELS,
  fmtMoney,
  fmtNum,
  fmtPct,
  fmtProb,
} from '../format.js';

const CONFIDENCE_STYLES = {
  high: 'bg-emerald-900 text-emerald-200',
  medium: 'bg-amber-900 text-amber-200',
  low: 'bg-slate-800 text-slate-300',
};

function BetActions({ pred, onLogged }) {
  const [stake, setStake] = useState(pred.recommended_stake);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  if (pred.bet) {
    return (
      <span className="text-xs text-slate-400">
        {pred.bet.status} · {pred.bet.outcome}
      </span>
    );
  }

  const log = async (decision) => {
    setBusy(true);
    setError('');
    try {
      await api('/bets', {
        method: 'POST',
        body: {
          prediction_id: pred.id,
          decision,
          stake: Number(stake),
        },
      });
      onLogged();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex items-center gap-2">
      <input
        className="input w-24 py-1"
        type="number"
        min="0"
        step="0.01"
        value={stake}
        onChange={(e) => setStake(e.target.value)}
        aria-label="Stake"
      />
      <button
        className="btn-primary"
        disabled={busy}
        onClick={() => log('accept')}
      >
        Accept
      </button>
      <button
        className="btn-ghost"
        disabled={busy}
        onClick={() => log('reject')}
      >
        Reject
      </button>
      {error && <span className="text-xs text-rose-400">{error}</span>}
    </div>
  );
}

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [showAll, setShowAll] = useState(false);

  const load = useCallback(async (refresh = false) => {
    setLoading(true);
    setError('');
    try {
      setData(await api(`/predictions/today${refresh ? '?refresh=1' : ''}`));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const rows = (data?.predictions ?? []).filter(
    (p) => showAll || p.is_recommended,
  );
  const best = data?.predictions?.find((p) => p.is_recommended);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Today's recommended bets</h1>
          <p className="text-sm text-slate-400">
            {data?.date ?? '…'} · projections vs. sportsbook player props
          </p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-slate-300">
            <input
              type="checkbox"
              checked={showAll}
              onChange={(e) => setShowAll(e.target.checked)}
            />
            Show all props
          </label>
          <button
            className="btn-ghost"
            onClick={() => load(true)}
            disabled={loading}
          >
            {loading ? 'Loading…' : 'Refresh odds'}
          </button>
        </div>
      </div>

      {error && <Notice kind="error">{error}</Notice>}
      {data?.warning && <Notice kind="warn">{data.warning}</Notice>}

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard label="Bankroll" value={fmtMoney(data?.bankroll)} />
        <StatCard
          label="Recommended"
          value={data?.recommended_count ?? 0}
          hint={`of ${data?.predictions?.length ?? 0} props priced`}
        />
        <StatCard
          label="Top edge"
          value={best ? fmtPct(best.edge_pct) : '—'}
          hint={best ? `${best.player} ${best.side} ${best.line}` : ''}
        />
        <StatCard
          label="Top EV / $1"
          value={best ? fmtNum(best.expected_value, 3) : '—'}
        />
      </div>

      <div className="card overflow-x-auto p-0">
        <table className="min-w-full divide-y divide-slate-800">
          <thead>
            <tr>
              {[
                'Player', 'Stat', 'Pick', 'Proj.', 'Edge', 'Win prob',
                'Odds', 'Kelly', 'Stake', '',
              ].map((h) => (
                <th key={h} className="th">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {rows.map((p) => (
              <tr key={p.id} className="hover:bg-slate-800/40">
                <td className="td">
                  <div className="font-medium">{p.player}</div>
                  <div className="text-xs text-slate-500">
                    {p.team} {p.is_home ? 'vs' : '@'} {p.opponent}
                  </div>
                </td>
                <td className="td">{STAT_LABELS[p.stat_type]}</td>
                <td className="td font-medium uppercase">
                  {p.side} {p.line}
                </td>
                <td className="td">{fmtNum(p.predicted_value)}</td>
                <td className="td text-emerald-400">
                  {fmtPct(p.edge_pct)}
                </td>
                <td className="td">
                  <span
                    className={`rounded px-2 py-0.5 text-xs ${
                      CONFIDENCE_STYLES[p.confidence]
                    }`}
                  >
                    {fmtProb(p.win_prob)} {p.confidence}
                  </span>
                </td>
                <td className="td">
                  {fmtNum(p.odds, 2)}
                  <div className="text-xs text-slate-500">{p.bookmaker}</div>
                </td>
                <td className="td">
                  {fmtProb(p.kelly_fraction)}
                  <div className="text-xs text-slate-500">
                    using {fmtProb(p.stake_fraction)}
                  </div>
                </td>
                <td className="td">{fmtMoney(p.recommended_stake)}</td>
                <td className="td">
                  <BetActions pred={p} onLogged={() => load()} />
                </td>
              </tr>
            ))}
            {!loading && rows.length === 0 && (
              <tr>
                <td className="td text-slate-400" colSpan={10}>
                  No recommended bets for this slate yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-slate-500">
        Kelly = (b·p − q) / b with b = decimal odds − 1. Stakes are capped
        by MAX_BET_FRACTION. Projections are estimates, not guarantees.
      </p>
    </div>
  );
}
