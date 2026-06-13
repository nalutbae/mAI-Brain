"use client";

import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from "react";

// nginx 프록시 모드에서는 빈 문자열(상대 경로) 사용
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

// ── 타입 ──────────────────────────────────────────────────────────────────────

export interface AuthUser {
  id: string;
  username: string;
  display_name: string | null;
  role: "admin" | "user";
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
}

interface AuthContextType {
  user: AuthUser | null;
  loading: boolean;
  isAdmin: boolean;
  login: (username: string, password: string) => Promise<AuthUser>;
  register: (username: string, password: string, display_name?: string) => Promise<AuthUser>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

// ── Provider ───────────────────────────────────────────────────────────────────

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/auth/me`, {
        credentials: "include",
      });
      if (res.ok) {
        const data = await res.json();
        setUser(data);
      } else {
        setUser(null);
      }
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const login = async (username: string, password: string): Promise<AuthUser> => {
    let res: Response;
    try {
      res = await fetch(`${API_BASE_URL}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ username, password }),
      });
    } catch (networkErr) {
      throw new Error("서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.");
    }
    if (!res.ok) {
      const detail = await res.json().catch(() => ({ detail: "로그인에 실패했습니다." }));
      throw new Error(detail.detail || "로그인에 실패했습니다.");
    }
    const data = await res.json();
    setUser(data);
    return data;
  };

  const register = async (username: string, password: string, display_name?: string): Promise<AuthUser> => {
    let res: Response;
    try {
      res = await fetch(`${API_BASE_URL}/api/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ username, password, display_name }),
      });
    } catch (networkErr) {
      throw new Error("서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.");
    }
    if (!res.ok) {
      const detail = await res.json().catch(() => ({ detail: "회원가입에 실패했습니다." }));
      throw new Error(detail.detail || "회원가입에 실패했습니다.");
    }
    const data = await res.json();
    setUser(data);
    return data;
  };

  const logout = async () => {
    await fetch(`${API_BASE_URL}/api/auth/logout`, {
      method: "POST",
      credentials: "include",
    });
    setUser(null);
  };

  const isAdmin = user?.role === "admin";

  return (
    <AuthContext.Provider value={{ user, loading, isAdmin, login, register, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}