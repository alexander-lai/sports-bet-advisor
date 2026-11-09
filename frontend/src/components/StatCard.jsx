export default function StatCard({ label, value, hint, className = '' }) {
  return (
    <div className="card">
      <p className="text-xs uppercase tracking-wide text-slate-400">
        {label}
      </p>
      <p className={`mt-1 text-2xl font-semibold ${className}`}>{value}</p>
      {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
    </div>
  );
}

export function Notice({ kind = 'info', children }) {
  const styles = {
    info: 'border-sky-800 bg-sky-950/50 text-sky-200',
    warn: 'border-amber-800 bg-amber-950/50 text-amber-200',
    error: 'border-rose-800 bg-rose-950/50 text-rose-200',
  };
  return (
    <div className={`rounded-lg border px-4 py-3 text-sm ${styles[kind]}`}>
      {children}
    </div>
  );
}
