import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from 'react';
import { api, getToken, setToken } from './api.js';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(Boolean(getToken()));

  const refreshUser = useCallback(async () => {
    if (!getToken()) return;
    try {
      const data = await api('/auth/me');
      setUser(data.user);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshUser();
    const onLogout = () => setUser(null);
    window.addEventListener('sba:logout', onLogout);
    return () => window.removeEventListener('sba:logout', onLogout);
  }, [refreshUser]);

  const authenticate = async (mode, payload) => {
    const data = await api(`/auth/${mode}`, {
      method: 'POST',
      body: payload,
    });
    setToken(data.access_token);
    setUser(data.user);
  };

  const logout = () => {
    setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider
      value={{ user, loading, authenticate, logout, refreshUser }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
