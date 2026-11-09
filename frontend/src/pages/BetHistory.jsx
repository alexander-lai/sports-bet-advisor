import { useCallback, useEffect, useState } from 'react';
import { api } from '../api.js';
import { useAuth } from '../auth.jsx';
import StatCard, { Notice } from '../components/StatCard.jsx';
import {
  STAT_LABELS,
  fmtMoney,
  fmtNum,
  fmtPct,
  signClass,
} from '../format.js';

const OUTCOMES = ['pending', 'win', 'loss', 'push'];

export default function BetHistory() {
  const { refreshUser } = useAuth();
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const load = useCallback(async () => {
    try {
      setData(await api('/bets'));
    } catch (err) {
      setError(err.message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const setOutcome = async (bet, outcome) => {
    try {
      await api(`/bets/${bet.id}`, { method: 'PATCH', body: { outcome } });
      await Promise.all([load(), refreshUser()]);
    } catch (err) {
      setError(err.message);
    }
  };

  const autoSettle = async () => {
    try {
      const res = await api('/bets/settle', { method: 'POST' });
      setMessage(`Settled ${res.settled} bet(s) from box scores.`);
      await Promise.all([load(), refreshUser()]);
    } catch (err) {
      setError(err.message);
    }
  };

  const s = data?.summary;
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-2xl font-semibold">Bet history</h1>
        <button className="btn-ghost" onClick={autoSettle}>
          Auto-settle from box scores
        </button>
      </div>
      {error && <Notice kind="error">{error}</Notice>}
      {message && <Notice>{message}</Notice>}

      <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
        <StatCard label="Settled bets" value={s?.bets ?? 0} />
        <StatCard label="Pending" value={s?.pending ?? 0} />
        <StatCard label="Win rate" value={fmtPct(s?.win_rate)} />
        <StatCard
          label="Profit"
          value={fmtMoney(s?.profit)}
          className={signClass(s?.profit)}
        />
        <StatCard
          label="ROI"
          value={fmtPct(s?.roi)}
          className={signClass(s?.roi)}
        />
      </div>

      <div className="card overflow-x-auto p-0">
        <table className="min-w-full divide-y divide-slate-800">
          <thead>
            <tr>
              {[
                'Date', 'Player', 'Pick', 'Proj.', 'Odds', 'Stake',
                'Status', 'Outcome', 'P/L', 'Running ROI',
              ].map((h) => (
                <th key={h} className="th">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {(data?.bets ?? []).map((b) => (
              <tr
                key={b.id}
                className={b.status === 'rejected' ? 'opacity-60' : ''}
              >
                <td className="td">{b.game_date}</td>
                <td className="td">
                  <div className="font-medium">{b.player}</div>
                  <div className="text-xs text-slate-500">
                    {b.team} v {b.opponent}
                  </div>
                </td>
                <td className="td uppercase">
                  {b.side} {b.line} {STAT_LABELS[b.stat_type]}
                </td>
                <td className="td">{fmtNum(b.predicted_value)}</td>
                <td className="td">{fmtNum(b.odds, 2)}</td>
                <td className="td">{fmtMoney(b.stake)}</td>
                <td className="td capitalize">{b.status}</td>
                <td className="td">
                  <select
                    className="input py-1"
                    value={b.outcome}
                    onChange={(e) => setOutcome(b, e.target.value)}
                    aria-label="Outcome"
                  >
                    {OUTCOMES.map((o) => (
                      <option key={o} value={o}>{o}</option>
                    ))}
                  </select>
                </td>
                <td className={`td ${signClass(b.profit_loss)}`}>
                  {fmtMoney(b.profit_loss)}
                </td>
                <td className={`td ${signClass(b.running_roi)}`}>
                  {fmtPct(b.running_roi)}
                </td>
              </tr>
            ))}
            {data && data.bets.length === 0 && (
              <tr>
                <td className="td text-slate-400" colSpan={10}>
                  No bets logged yet. Accept or reject picks on the
                  dashboard.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-slate-500">
        Rejected bets are graded for reference but excluded from bankroll
        and ROI.
      </p>
    </div>
  );
}
