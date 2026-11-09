import { useState } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../auth.jsx';
import { Notice } from '../components/StatCard.jsx';

export default function Login() {
  const { user, authenticate } = useAuth();
  const [mode, setMode] = useState('login');
  const [form, setForm] = useState({
    email: '',
    password: '',
    bankroll: 1000,
  });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to="/" replace />;

  const update = (key) => (e) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      const payload = { email: form.email, password: form.password };
      if (mode === 'register') payload.bankroll = Number(form.bankroll);
      await authenticate(mode, payload);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <form onSubmit={submit} className="card w-full max-w-sm space-y-4">
        <div>
          <h1 className="text-xl font-semibold text-emerald-400">
            Sports Bet Advisor
          </h1>
          <p className="text-sm text-slate-400">
            {mode === 'login' ? 'Sign in to your account' : 'Create account'}
          </p>
        </div>
        {error && <Notice kind="error">{error}</Notice>}
        <label className="block space-y-1 text-sm">
          <span>Email</span>
          <input
            className="input"
            type="email"
            required
            value={form.email}
            onChange={update('email')}
          />
        </label>
        <label className="block space-y-1 text-sm">
          <span>Password</span>
          <input
            className="input"
            type="password"
            minLength={8}
            required
            value={form.password}
            onChange={update('password')}
          />
        </label>
        {mode === 'register' && (
          <label className="block space-y-1 text-sm">
            <span>Starting bankroll ($)</span>
            <input
              className="input"
              type="number"
              min="0"
              step="1"
              value={form.bankroll}
              onChange={update('bankroll')}
            />
          </label>
        )}
        <button className="btn-primary w-full py-2" disabled={busy}>
          {mode === 'login' ? 'Sign in' : 'Create account'}
        </button>
        <button
          type="button"
          className="w-full text-sm text-slate-400 hover:text-slate-200"
          onClick={() => setMode(mode === 'login' ? 'register' : 'login')}
        >
          {mode === 'login'
            ? 'No account? Register'
            : 'Have an account? Sign in'}
        </button>
      </form>
    </div>
  );
}
