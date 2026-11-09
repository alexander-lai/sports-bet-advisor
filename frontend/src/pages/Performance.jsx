import { useEffect, useState } from 'react';
import {
  Bar,
  BarChart,
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
import { STAT_LABELS, fmtMoney, fmtPct, signClass } from '../format.js';

const pctTick = (v) => `${v}%`;

function ChartCard({ title, children, height = 280 }) {
  return (
    <div className="card">
      <h2 className="mb-3 text-sm font-semibold text-slate-300">{title}</h2>
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          {children}
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export default function Performance() {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    api('/performance').then(setData).catch((e) => setError(e.message));
  }, []);

  if (error) return <Notice kind="error">{error}</Notice>;
  if (!data) return <p className="text-slate-400">Loading…</p>;

  const s = data.summary;
  const byStat = data.by_stat.map((r) => ({
    ...r,
    label: STAT_LABELS[r.stat_type] ?? r.stat_type,
  }));
  const series = data.series.map((p, i) => ({ ...p, n: i + 1 }));

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Performance</h1>
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard label="Settled bets" value={s.bets} />
        <StatCard
          label="Win rate"
          value={fmtPct(s.win_rate)}
          hint={`${s.wins}W · ${s.losses}L · ${s.pushes}P`}
        />
        <StatCard
          label="Profit"
          value={fmtMoney(s.profit)}
          className={signClass(s.profit)}
          hint={`on ${fmtMoney(s.staked)} staked`}
        />
        <StatCard
          label="ROI"
          value={fmtPct(s.roi)}
          className={signClass(s.roi)}
        />
      </div>

      {s.bets === 0 ? (
        <Notice>
          No settled bets yet. Charts appear once accepted bets are graded.
        </Notice>
      ) : (
        <>
          <ChartCard title="Cumulative ROI by bet">
            <LineChart data={series} margin={{ right: 16 }}>
              <CartesianGrid stroke={GRID} vertical={false} />
              <XAxis dataKey="n" tick={AXIS} stroke={BASELINE} />
              <YAxis tick={AXIS} tickFormatter={pctTick} stroke={GRID} />
              <ReferenceLine y={0} stroke={BASELINE} />
              <Tooltip
                {...tooltipProps}
                labelFormatter={(n) => `Bet #${n} · ${series[n - 1]?.date}`}
                formatter={(v, name) =>
                  name === 'cumulative_roi'
                    ? [fmtPct(v), 'ROI']
                    : [fmtMoney(v), 'Profit']
                }
              />
              <Line
                type="monotone"
                dataKey="cumulative_roi"
                stroke={SERIES}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 5, strokeWidth: 2, stroke: '#0f172a' }}
              />
            </LineChart>
          </ChartCard>

          <div className="grid gap-6 lg:grid-cols-2">
            <ChartCard title="Win rate by stat type">
              <BarChart data={byStat} barCategoryGap="30%">
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis dataKey="label" tick={AXIS} stroke={BASELINE} />
                <YAxis
                  domain={[0, 100]}
                  tick={AXIS}
                  tickFormatter={pctTick}
                  stroke={GRID}
                />
                <ReferenceLine y={52.4} stroke={BASELINE}
                  strokeDasharray="4 4" />
                <Tooltip
                  {...tooltipProps}
                  formatter={(v, _n, item) => [
                    `${fmtPct(v)} (${item.payload.bets} bets)`,
                    'Win rate',
                  ]}
                />
                <Bar dataKey="win_rate" fill={SERIES} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ChartCard>

            <ChartCard
              title="Win rate by player (most bets)"
              height={Math.max(220, data.by_player.length * 28)}
            >
              <BarChart
                data={data.by_player}
                layout="vertical"
                margin={{ left: 24 }}
                barCategoryGap="25%"
              >
                <CartesianGrid stroke={GRID} horizontal={false} />
                <XAxis
                  type="number"
                  domain={[0, 100]}
                  tick={AXIS}
                  tickFormatter={pctTick}
                  stroke={BASELINE}
                />
                <YAxis
                  type="category"
                  dataKey="player"
                  tick={AXIS}
                  width={120}
                  stroke={GRID}
                />
                <Tooltip
                  {...tooltipProps}
                  formatter={(v, _n, item) => [
                    `${fmtPct(v)} (${item.payload.bets} bets, ` +
                      `${fmtMoney(item.payload.profit)})`,
                    'Win rate',
                  ]}
                />
                <Bar dataKey="win_rate" fill={SERIES} radius={[0, 4, 4, 0]} />
              </BarChart>
            </ChartCard>
          </div>
          <p className="text-xs text-slate-500">
            Dashed line: 52.4%, the break-even win rate at -110 odds.
          </p>
        </>
      )}
    </div>
  );
}
