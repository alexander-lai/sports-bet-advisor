import { Navigate, Route, Routes } from 'react-router-dom';
import { useAuth } from './auth.jsx';
import Layout from './components/Layout.jsx';
import Backtest from './pages/Backtest.jsx';
import BetHistory from './pages/BetHistory.jsx';
import Dashboard from './pages/Dashboard.jsx';
import Login from './pages/Login.jsx';
import Performance from './pages/Performance.jsx';

function RequireAuth({ children }) {
  const { user, loading } = useAuth();
  if (loading) {
    return <p className="p-8 text-slate-400">Loading…</p>;
  }
  return user ? children : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="history" element={<BetHistory />} />
        <Route path="performance" element={<Performance />} />
        <Route path="backtest" element={<Backtest />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
