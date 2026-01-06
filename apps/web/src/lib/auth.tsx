"use client";

import { apiGetMe, apiLogin, apiLogout, apiRefresh, API_BASE_URL } from "@/lib/api";
import type { TokenResponse, UserPublic } from "@/lib/types";
import { usePathname, useRouter } from "next/navigation";
import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

type AuthContextValue = {
  loading: boolean;
  user: UserPublic | null;
  accessToken: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  apiFetch: (path: string, init?: RequestInit) => Promise<Response>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

function setStoredTokens(tokens: TokenResponse | null) {
  if (!tokens) {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    return;
  }
  localStorage.setItem("access_token", tokens.access_token);
  localStorage.setItem("refresh_token", tokens.refresh_token);
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [loading, setLoading] = useState(true);
  const [user, setUser] = useState<UserPublic | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState<string | null>(null);
  const refreshInFlight = useRef<Promise<TokenResponse> | null>(null);

  const loadMe = useCallback(
    async (token: string) => {
      const me = await apiGetMe(token);
      setUser(me);
      return me;
    },
    [setUser]
  );

  useEffect(() => {
    const access = localStorage.getItem("access_token");
    const refresh = localStorage.getItem("refresh_token");
    if (!access || !refresh) {
      setLoading(false);
      return;
    }
    setAccessToken(access);
    setRefreshToken(refresh);
    loadMe(access)
      .catch(() => {
        setStoredTokens(null);
        setAccessToken(null);
        setRefreshToken(null);
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, [loadMe]);

  const login = useCallback(
    async (email: string, password: string) => {
      const tokens = await apiLogin(email, password);
      setStoredTokens(tokens);
      setAccessToken(tokens.access_token);
      setRefreshToken(tokens.refresh_token);
      await loadMe(tokens.access_token);
    },
    [loadMe]
  );

  const logout = useCallback(async () => {
    try {
      if (refreshToken) await apiLogout(refreshToken);
    } finally {
      setStoredTokens(null);
      setAccessToken(null);
      setRefreshToken(null);
      setUser(null);
      if (pathname !== "/login") router.replace("/login");
    }
  }, [pathname, refreshToken, router]);

  const apiFetch = useCallback(
    async (path: string, init: RequestInit = {}) => {
      const url = `${API_BASE_URL}${path}`;
      const headers = new Headers(init.headers);
      if (accessToken) headers.set("authorization", `Bearer ${accessToken}`);
      if (init.body && !headers.has("content-type")) headers.set("content-type", "application/json");
      const res = await fetch(url, { ...init, headers });
      if (res.status !== 401 || !refreshToken) return res;

      try {
        if (!refreshInFlight.current) refreshInFlight.current = apiRefresh(refreshToken);
        const newTokens = await refreshInFlight.current;
        refreshInFlight.current = null;
        setStoredTokens(newTokens);
        setAccessToken(newTokens.access_token);
        setRefreshToken(newTokens.refresh_token);

        const headers2 = new Headers(init.headers);
        headers2.set("authorization", `Bearer ${newTokens.access_token}`);
        if (init.body && !headers2.has("content-type")) headers2.set("content-type", "application/json");
        return await fetch(url, { ...init, headers: headers2 });
      } catch {
        refreshInFlight.current = null;
        await logout();
        return res;
      }
    },
    [accessToken, logout, refreshToken]
  );

  const value = useMemo<AuthContextValue>(
    () => ({ loading, user, accessToken, login, logout, apiFetch }),
    [accessToken, apiFetch, loading, login, logout, user]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

