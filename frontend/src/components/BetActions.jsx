import { useState } from 'react';
import { api } from '../api.js';

// Accept / reject a prediction with an editable stake.
export default function BetActions({ pred, onLogged }) {
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
