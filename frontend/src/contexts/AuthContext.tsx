import { createContext, useContext, useState, useCallback, useEffect, type ReactNode } from "react";
import { api, setAuthToken, getAuthToken } from "@/lib/api";

const EMAIL_KEY = "voicecart_email";

interface AuthUser {
  email: string;
}

interface AuthState {
  user: AuthUser | null;
  token: string | null;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (name: string, email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

// The login token does not carry the email, so keep it next to the token to show who is signed in after a refresh.
function savedEmail(): string | null {
  try {
    return localStorage.getItem(EMAIL_KEY);
  } catch {
    return null;
  }
}

function saveEmail(email: string | null) {
  try {
    if (email) localStorage.setItem(EMAIL_KEY, email);
    else localStorage.removeItem(EMAIL_KEY);
  } catch {
    // Storage unavailable; the email is then only known until the page is reloaded.
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(getAuthToken());
  const [user, setUser] = useState<AuthUser | null>(() => {
    const email = savedEmail();
    return getAuthToken() && email ? { email } : null;
  });

  useEffect(() => {
    // If we have a stored token, we're authenticated (user details could be fetched)
    if (token) setAuthToken(token);
  }, [token]);

  const login = useCallback(async (email: string, password: string) => {
    const res = await api.login({ email, password });
    setAuthToken(res.access_token);
    saveEmail(email);
    setToken(res.access_token);
    setUser({ email });
  }, []);

  const register = useCallback(async (name: string, email: string, password: string) => {
    await api.register({ name, email, password });
  }, []);

  const logout = useCallback(() => {
    setAuthToken(null);
    saveEmail(null);
    setToken(null);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, token, isAuthenticated: !!token, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
