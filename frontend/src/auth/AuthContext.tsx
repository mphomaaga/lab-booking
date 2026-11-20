import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useNavigate } from "react-router-dom";
import * as api from "../api/client";
import type { User } from "../api/types";
import { clearToken, getToken, setToken } from "./tokenStorage";

export interface AuthContextValue {
  /** The logged-in user, or null when logged out (or still loading). */
  user: User | null;
  /** true while a stored token is being checked with `getMe` on page load. */
  loading: boolean;
  /** Throws ApiError on failure, for example 401 `invalid_credentials`. */
  login: (studentNumber: string, password: string) => Promise<void>;
  /** Removes the token and goes to /login. No server call (rule 5.14). */
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(() => getToken() !== null);

  // A 401 from any call except login: the client has cleared the token already.
  useEffect(() => {
    api.setUnauthorizedHandler(() => {
      setUser(null);
      setLoading(false);
      navigate("/login", { replace: true });
    });
    return () => api.setUnauthorizedHandler(null);
  }, [navigate]);

  // On load with a token, learn who the user is and whether they are an admin.
  useEffect(() => {
    if (getToken() === null) return;
    let cancelled = false;
    api
      .getMe()
      .then((me) => {
        if (!cancelled) setUser(me);
      })
      .catch(() => {
        // A 401 is handled by the client. Any other failure: treat as logged out.
        if (cancelled) return;
        clearToken();
        setUser(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (studentNumber: string, password: string) => {
    const response = await api.login(studentNumber, password);
    setToken(response.access_token);
    setUser(response.user);
    setLoading(false);
  }, []);

  const logout = useCallback(() => {
    clearToken();
    setUser(null);
    navigate("/login", { replace: true });
  }, [navigate]);

  const value = useMemo<AuthContextValue>(
    () => ({ user, loading, login, logout }),
    [user, loading, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (value === null) throw new Error("useAuth must be used inside an AuthProvider");
  return value;
}
