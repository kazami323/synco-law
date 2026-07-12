"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { api } from "@/lib/api";
import type { User } from "@/lib/types";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string, mfaCode?: string) => Promise<User>;
  logout: () => void;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    await Promise.resolve();
    try {
      // A public visitor normally has no session. Do not emit the global
      // "session expired" redirect while bootstrapping login/register pages.
      setUser(await api<User>("/api/auth/me", {}, false));
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      void refresh();
    }, 0);
    return () => window.clearTimeout(timeout);
  }, [refresh]);

  const login = useCallback(async (email: string, password: string, mfaCode?: string) => {
    await api<{ access_token: string }>("/api/auth/login", {
      method: "POST",
      body: { email, password, mfa_code: mfaCode || null },
    });
    const me = await api<User>("/api/auth/me");
    setUser(me);
    setLoading(false);
    return me;
  }, []);

  const logout = useCallback(() => {
    void api("/api/auth/logout", { method: "POST" }).catch(() => undefined);
    setUser(null);
    window.location.href = "/login";
  }, []);

  useEffect(() => {
    const expired = () => {
      setUser(null);
      window.location.href = "/login";
    };
    window.addEventListener("auth:expired", expired);
    return () => window.removeEventListener("auth:expired", expired);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
