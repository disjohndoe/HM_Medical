"use client";

import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { User, TokenResponse, LoginRequest, RegisterRequest } from "@/lib/types";
import { api } from "@/lib/api-client";

interface AuthContextType {
  user: User | null;
  tenant: User["tenant"] | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (data: LoginRequest) => Promise<void>;
  register: (data: RegisterRequest) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

const LOGOUT_MAX_RETRIES = 2;

function setSessionCookie(active: boolean) {
  if (active) {
    document.cookie = "has_session=1; path=/; SameSite=Lax; max-age=604800";
  } else {
    document.cookie = "has_session=; path=/; SameSite=Lax; max-age=0";
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const handleTokenResponse = useCallback((res: TokenResponse) => {
    localStorage.setItem("access_token", res.access_token);
    localStorage.setItem("refresh_token", res.refresh_token);
    setSessionCookie(true);
    // Clear any previous auth redirect reason on successful login
    localStorage.removeItem("auth_redirect_reason");
    localStorage.removeItem("auth_redirect_reason_ts");
    if (res.user) {
      setUser(res.user);
    }
  }, []);

  const clearAuth = useCallback(() => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    setSessionCookie(false);
    setUser(null);
  }, []);

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- hydrate loading state from localStorage
      setIsLoading(false);
      return;
    }

    api
      .get<User>("/auth/me")
      .then((u) => {
        setUser(u);
        setSessionCookie(true);
      })
      .catch(() => clearAuth())
      .finally(() => setIsLoading(false));
  }, [clearAuth]);

  const login = async (data: LoginRequest) => {
    const res = await api.post<TokenResponse>("/auth/login", data);
    handleTokenResponse(res);
    // Clear any stale query cache so dashboard fetches fresh data for this session
    queryClient.clear();
  };

  const register = async (data: RegisterRequest) => {
    const res = await api.post<TokenResponse>("/auth/register", data);
    handleTokenResponse(res);
  };

  const logout = async () => {
    const refreshToken = localStorage.getItem("refresh_token");
    if (refreshToken) {
      // BUG 4 fix: retry logout to avoid ghost sessions
      for (let attempt = 0; attempt <= LOGOUT_MAX_RETRIES; attempt++) {
        try {
          await api.post("/auth/logout", { refresh_token: refreshToken });
          break; // success
        } catch {
          if (attempt === LOGOUT_MAX_RETRIES) {
            // All retries failed — clear locally anyway.
            // Ghost session will be cleaned up by token expiry or cleanup job.
          }
        }
      }
    }
    clearAuth();
    queryClient.clear();
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        tenant: user?.tenant ?? null,
        isAuthenticated: !!user,
        isLoading,
        login,
        register,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
