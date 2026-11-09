import { useEffect, useState } from 'react';
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { api } from '../api.js';
import {
  AXIS,
  BASELINE,
  GRID,
  SERIES,
  tooltipProps,
} from '../components/charts.js';
import StatCard, { Notice } from '../components/StatCard.jsx';
import {
  STAT_LABELS,
  fmtMoney,
  fmtNum,
  fmtPct,
  signClass,
} from '../format.js';

const FIELDS = [
  { key: 'season', label: 'Test season (start year)', step: 1 },
  { key: 'min_ev', label: 'Min EV per $1', step: 0.01 },
  { key: 'kelly_multiplier', label: 'Kelly multiplier', step: 0.05 },
  { key: 'max_fraction', label: 'Max bet fraction', step: 0.01 },
  { key: 'max_bets_per_day', label: 'Max bets / day', step: 1 },
  { key: 'starting_bankroll', label: 'Starting bankroll', step: 100 },
];

function ModelPanel() {
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const load = () =>
    api('/model/status').then(setStatus).catch((e) => setError(e.message));
  useEffect(() => {
    load();
  }, []);

  const retrain = async () => {
    setBusy(true);
    setError('');
    try {
      await api('/model/retrain', { method: 'POST' });
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const model = status?.model;
  return (
    <div className="card space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-300">Model</h2>
        <button className="btn-ghost" onClick={retrain} disabled={busy}>
          {busy ? 'Retraining…' : 'Retrain on all data'}
        </button>
      </div>
      {error && <Notice kind="error">{error}</Notice>}
      {model && !model.trained && (
        <Notice kind="warn">Not trained yet — run the seed script.</Notice>
      )}
      {model?.trained && (
        <div className="grid gap-2 text-sm text-slate-300 md:grid-cols-2">
          <p>Trained {new Date(model.trained_at).toLocaleString()}</p>
          <p>
            {model.n_rows.toLocaleString()} rows · seasons{' '}
            {model.seasons.join(', ')}
          </p>
          {Object.entries(model.metrics).map(([stat, m]) => (
            <p key={stat}>
              {STAT_LABELS[stat]}: MAE {fmtNum(m.mae, 2)} (rolling-avg{' '}
              {fmtNum(m.baseline_mae, 2)})
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Backtest() {
  const [params, setParams] = useState({
    season: 2025,
    min_ev: 0.03,
    kelly_multiplier: 0.5,
    max_fraction: 0.05,
    max_bets_per_day: 10,
    starting_bankroll: 1000,
  });
  const [run, setRun] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    api('/backtest/latest')
      .then((d) => d.run && setRun(d.run))
      .catch(() => {});
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      const body = Object.fromEntries(
        Object.entries(params).map(([k, v]) => [k, Number(v)]),
      );
      setRun(await api('/backtest', { method: 'POST', body }));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const r = run?.results;
  const s = r?.summary;
  const proxyOnly = r && !r.line_sources?.historical;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Backtest</h1>
      <ModelPanel />

      <form onSubmit={submit} className="card space-y-4">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-6">
          {FIELDS.map((f) => (
            <label key={f.key} className="space-y-1 text-xs text-slate-400">
              <span>{f.label}</span>
              <input
                className="input"
                type="number"
                step={f.step}
                value={params[f.key]}
                onChange={(e) =>
                  setParams((p) => ({ ...p, [f.key]: e.target.value }))
                }
              />
            </label>
          ))}
        </div>
        <button className="btn-primary" disabled={busy}>
          {busy ? 'Running (trains a fresh model)…' : 'Run backtest'}
        </button>
      </form>
      {error && <Notice kind="error">{error}</Notice>}

      {r && (
        <>
          <p className="text-sm text-slate-400">
            Season {r.season} held out · trained on{' '}
            {r.train_seasons.join(', ')} · run{' '}
            {new Date(run.created_at).toLocaleString()}
          </p>
          {proxyOnly && (
            <Notice kind="warn">
              No historical sportsbook lines are stored, so this run used
              proxy lines (rolling 10-game average at -110). It measures
              the model against a naive average, not a real book.
            </Notice>
          )}
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <StatCard label="Bets" value={s.bets.toLocaleString()}
              hint={`${s.betting_days} betting days`} />
            <StatCard label="Win rate" value={fmtPct(s.win_rate)}
              hint={`${s.wins}W · ${s.losses}L · ${s.pushes}P`} />
            <StatCard label="ROI (Kelly)" value={fmtPct(s.roi)}
              className={signClass(s.roi)}
              hint={`flat-stake ROI ${fmtPct(s.flat_roi)}`} />
            <StatCard label="Sharpe" value={fmtNum(s.sharpe, 2)}
              hint="daily returns, season-annualised" />
            <StatCard label="Final bankroll"
              value={fmtMoney(s.final_bankroll)}
              className={signClass(s.bankroll_return)}
              hint={`${fmtPct(s.bankroll_return)} return`} />
            <StatCard label="Max drawdown" value={fmtPct(s.max_drawdown)} />
            <StatCard label="Profit" value={fmtMoney(s.profit)}
              className={signClass(s.profit)} />
            <StatCard label="Props evaluated"
              value={r.candidates_evaluated.toLocaleString()} />
          </div>

          <div className="card">
            <h2 className="mb-3 text-sm font-semibold text-slate-300">
              Bankroll over the season
            </h2>
            <div style={{ height: 300 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={r.equity_curve} margin={{ right: 16 }}>
                  <CartesianGrid stroke={GRID} vertical={false} />
                  <XAxis dataKey="date" tick={AXIS} stroke={BASELINE}
                    minTickGap={40} />
                  <YAxis tick={AXIS} stroke={GRID}
                    tickFormatter={(v) => `$${Math.round(v)}`} />
                  <ReferenceLine y={s.starting_bankroll} stroke={BASELINE}
                    strokeDasharray="4 4" />
                  <Tooltip {...tooltipProps}
                    formatter={(v) => [fmtMoney(v), 'Bankroll']} />
                  <Line type="monotone" dataKey="bankroll" stroke={SERIES}
                    strokeWidth={2} dot={false}
                    activeDot={{ r: 5, strokeWidth: 2, stroke: '#0f172a' }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="card overflow-x-auto p-0">
            <table className="min-w-full divide-y divide-slate-800">
              <thead>
                <tr>
                  {['Stat', 'Bets', 'Win rate', 'ROI', 'Flat ROI',
                    'Model MAE', 'Rolling-avg MAE'].map((h) => (
                    <th key={h} className="th">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {r.by_stat.map((row) => {
                  const m = r.model_metrics[row.stat_type] ?? {};
                  return (
                    <tr key={row.stat_type}>
                      <td className="td">{STAT_LABELS[row.stat_type]}</td>
                      <td className="td">{row.bets}</td>
                      <td className="td">{fmtPct(row.win_rate)}</td>
                      <td className={`td ${signClass(row.roi)}`}>
                        {fmtPct(row.roi)}
                      </td>
                      <td className={`td ${signClass(row.flat_roi)}`}>
                        {fmtPct(row.flat_roi)}
                      </td>
                      <td className="td">{fmtNum(m.mae, 2)}</td>
                      <td className="td">{fmtNum(m.baseline_mae, 2)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
