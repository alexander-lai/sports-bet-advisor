const money = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
});

export const fmtMoney = (v) => money.format(v ?? 0);
export const fmtPct = (v, digits = 1) => `${Number(v ?? 0).toFixed(digits)}%`;
export const fmtProb = (v) => `${(Number(v ?? 0) * 100).toFixed(1)}%`;
export const fmtNum = (v, digits = 1) => Number(v ?? 0).toFixed(digits);

export const STAT_LABELS = { pts: 'Points', reb: 'Rebounds', ast: 'Assists' };

export const signClass = (v) =>
  v > 0 ? 'text-emerald-400' : v < 0 ? 'text-rose-400' : 'text-slate-300';
