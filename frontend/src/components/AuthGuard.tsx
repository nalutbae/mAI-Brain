"use client";

import { useAuth } from "../lib/auth";

/** 관리자 전용 페이지 래퍼. 비관리자면 접근 거부 메시지 표시. */
export function AdminGuard({ children }: { children: React.ReactNode }) {
  const { user, loading, isAdmin } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
        <div className="text-gray-500 dark:text-gray-400">로딩 중...</div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">로그인이 필요합니다</h1>
          <p className="text-gray-500 dark:text-gray-400">이 페이지에 접근하려면 로그인하세요.</p>
        </div>
      </div>
    );
  }

  if (!isAdmin) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">접근 권한 없음</h1>
          <p className="text-gray-500 dark:text-gray-400">관리자 권한이 필요합니다.</p>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}

/** 로그인 필수 페이지 래퍼. 로그인 안 되어 있으면 접근 거부. */
export function AuthGuard({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
        <div className="text-gray-500 dark:text-gray-400">로딩 중...</div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">로그인이 필요합니다</h1>
          <p className="text-gray-500 dark:text-gray-400">이 페이지에 접근하려면 로그인하세요.</p>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}