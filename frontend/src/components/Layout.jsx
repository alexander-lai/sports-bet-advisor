import { NavLink, Outlet } from 'react-router-dom';
import { useAuth } from '../auth.jsx';
import { fmtMoney } from '../format.js';

const LINKS = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/games', label: 'Games' },
  { to: '/history', label: 'Bet History' },
  { to: '/performance', label: 'Performance' },
  { to: '/backtest', label: 'Backtest' },
];

export default function Layout() {
  const { user, logout } = useAuth();
  const linkClass = ({ isActive }) =>
    `rounded-lg px-3 py-1.5 text-sm ${
      isActive
        ? 'bg-slate-800 text-white'
        : 'text-slate-400 hover:text-slate-100'
    }`;

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-800 bg-slate-900/80">
        <div
          className="mx-auto flex max-w-7xl flex-wrap items-center
            justify-between gap-3 px-4 py-3"
        >
          <div className="flex flex-wrap items-center gap-4">
            <span className="font-semibold text-emerald-400">
              Sports Bet Advisor
            </span>
            <nav className="flex flex-wrap gap-1">
              {LINKS.map((l) => (
                <NavLink
                  key={l.to}
                  to={l.to}
                  end={l.end}
                  className={linkClass}
                >
                  {l.label}
                </NavLink>
              ))}
            </nav>
          </div>
          <div className="flex items-center gap-3 text-sm">
            <span className="text-slate-400">
              Bankroll{' '}
              <span className="font-semibold text-slate-100">
                {fmtMoney(user?.bankroll)}
              </span>
            </span>
            <button className="btn-ghost" onClick={logout}>
              Log out
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
