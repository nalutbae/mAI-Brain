"use client";

import { useState, useEffect, useCallback } from "react";
import { useAuth } from "../../../lib/auth";
import { AdminGuard } from "../../../components/AuthGuard";
import {
  AdminUser,
  listUsers,
  updateUserRole,
  setUserActive,
  deleteUser,
  getUserStats,
} from "../../../lib/api";

export default function UsersPage() {
  return (
    <AdminGuard>
      <UsersContent />
    </AdminGuard>
  );
}

function UsersContent() {
  const { user: currentUser, isAdmin } = useAuth();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [stats, setStats] = useState<{ total: number; active: number; admins: number; regular_users: number } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [selectedUser, setSelectedUser] = useState<AdminUser | null>(null);

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const [usersData, statsData] = await Promise.all([listUsers(), getUserStats()]);
      setUsers(usersData);
      setStats(statsData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "데이터를 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isAdmin) fetchData();
  }, [isAdmin, fetchData]);

  // AdminGuard가 이미 관리자 권한 검증을 수행함

  const handleRoleChange = async (userId: string, newRole: "admin" | "user") => {
    if (!confirm(`역할을 ${newRole === "admin" ? "관리자" : "일반 사용자"}로 변경하시겠습니까?`)) return;
    try {
      setActionLoading(userId);
      await updateUserRole(userId, newRole);
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "역할 변경에 실패했습니다.");
    } finally {
      setActionLoading(null);
    }
  };

  const handleToggleActive = async (userId: string, isActive: boolean) => {
    const action = isActive ? "활성화" : "비활성화";
    if (!confirm(`사용자를 ${action}하시겠습니까?`)) return;
    try {
      setActionLoading(userId);
      await setUserActive(userId, isActive);
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : `${action}에 실패했습니다.`);
    } finally {
      setActionLoading(null);
    }
  };

  const handleDelete = async (userId: string, username: string) => {
    if (!confirm(`사용자 "${username}"을(를) 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.`)) return;
    try {
      setActionLoading(userId);
      await deleteUser(userId);
      await fetchData();
      if (selectedUser?.id === userId) setSelectedUser(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "삭제에 실패했습니다.");
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 p-6">
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">👥 사용자 관리</h1>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              가입한 사용자 목록과 역할을 관리합니다.
            </p>
          </div>
        </div>

        {error && (
          <div className="mb-4 p-4 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-lg text-red-700 dark:text-red-300 text-sm">
            {error}
            <button onClick={() => setError(null)} className="float-right font-bold">✕</button>
          </div>
        )}

        {/* 통계 카드 */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <div className="bg-white dark:bg-gray-800 p-4 rounded-lg border border-gray-200 dark:border-gray-700 text-center">
              <div className="text-2xl font-bold text-gray-900 dark:text-white">{stats.total}</div>
              <div className="text-xs text-gray-500 dark:text-gray-400">전체</div>
            </div>
            <div className="bg-white dark:bg-gray-800 p-4 rounded-lg border border-gray-200 dark:border-gray-700 text-center">
              <div className="text-2xl font-bold text-green-600">{stats.active}</div>
              <div className="text-xs text-gray-500 dark:text-gray-400">활성</div>
            </div>
            <div className="bg-white dark:bg-gray-800 p-4 rounded-lg border border-gray-200 dark:border-gray-700 text-center">
              <div className="text-2xl font-bold text-purple-600">{stats.admins}</div>
              <div className="text-xs text-gray-500 dark:text-gray-400">관리자</div>
            </div>
            <div className="bg-white dark:bg-gray-800 p-4 rounded-lg border border-gray-200 dark:border-gray-700 text-center">
              <div className="text-2xl font-bold text-blue-600">{stats.regular_users}</div>
              <div className="text-xs text-gray-500 dark:text-gray-400">일반</div>
            </div>
          </div>
        )}

        {/* 사용자 목록 */}
        {loading ? (
          <div className="text-center py-12 text-gray-500 dark:text-gray-400">로딩 중...</div>
        ) : (
          <div className="space-y-3">
            {users.map((u) => (
              <div
                key={u.id}
                className={`p-4 bg-white dark:bg-gray-800 border rounded-lg shadow-sm cursor-pointer transition-colors ${
                  selectedUser?.id === u.id
                    ? "border-blue-500 ring-2 ring-blue-200 dark:ring-blue-800"
                    : u.is_active
                    ? "border-gray-200 dark:border-gray-700 hover:border-blue-300"
                    : "border-gray-300 dark:border-gray-600 opacity-60"
                }`}
                onClick={() => setSelectedUser(u)}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-blue-100 dark:bg-blue-900 flex items-center justify-center text-blue-700 dark:text-blue-300 font-bold text-sm">
                      {(u.display_name || u.username).charAt(0).toUpperCase()}
                    </div>
                    <div>
                      <div className="font-medium text-gray-900 dark:text-white">
                        {u.display_name || u.username}
                        <span className="text-gray-400 ml-1 text-sm">@{u.username}</span>
                      </div>
                      <div className="text-xs text-gray-500 dark:text-gray-400">
                        가입: {new Date(u.created_at).toLocaleDateString("ko-KR")}
                        {u.last_login_at && ` · 마지막 로그인: ${new Date(u.last_login_at).toLocaleDateString("ko-KR")}`}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                      u.role === "admin"
                        ? "bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200"
                        : "bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300"
                    }`}>
                      {u.role === "admin" ? "👑 관리자" : "👤 사용자"}
                    </span>
                    {!u.is_active && (
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200">
                        비활성
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* 사용자 상세 패널 */}
        {selectedUser && (
          <div className="mt-6 p-6 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                📋 {selectedUser.display_name || selectedUser.username} 상세 정보
              </h3>
              <button
                onClick={() => setSelectedUser(null)}
                className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
              >
                ✕
              </button>
            </div>

            <div className="grid grid-cols-2 gap-4 mb-4 text-sm">
              <div><span className="text-gray-500">ID:</span> <span className="font-mono text-gray-900 dark:text-white">{selectedUser.id.slice(0, 12)}...</span></div>
              <div><span className="text-gray-500">사용자명:</span> <span className="text-gray-900 dark:text-white">{selectedUser.username}</span></div>
              <div><span className="text-gray-500">표시 이름:</span> <span className="text-gray-900 dark:text-white">{selectedUser.display_name || "-"}</span></div>
              <div><span className="text-gray-500">역할:</span> <span className="text-gray-900 dark:text-white">{selectedUser.role === "admin" ? "관리자" : "일반 사용자"}</span></div>
              <div><span className="text-gray-500">상태:</span> <span className={selectedUser.is_active ? "text-green-600" : "text-red-600"}>{selectedUser.is_active ? "활성" : "비활성"}</span></div>
              <div><span className="text-gray-500">가입일:</span> <span className="text-gray-900 dark:text-white">{new Date(selectedUser.created_at).toLocaleString("ko-KR")}</span></div>
            </div>

            {selectedUser.id !== currentUser?.id && (
              <div className="flex gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
                <button
                  onClick={() => handleRoleChange(selectedUser.id, selectedUser.role === "admin" ? "user" : "admin")}
                  disabled={actionLoading === selectedUser.id}
                  className="px-4 py-2 text-sm border border-purple-500 text-purple-700 dark:text-purple-400 rounded-lg hover:bg-purple-50 dark:hover:bg-purple-900/30 disabled:opacity-50"
                >
                  {selectedUser.role === "admin" ? "👤 사용자로 변경" : "👑 관리자로 변경"}
                </button>
                <button
                  onClick={() => handleToggleActive(selectedUser.id, !selectedUser.is_active)}
                  disabled={actionLoading === selectedUser.id}
                  className={`px-4 py-2 text-sm border rounded-lg disabled:opacity-50 ${
                    selectedUser.is_active
                      ? "border-orange-500 text-orange-700 dark:text-orange-400 hover:bg-orange-50 dark:hover:bg-orange-900/30"
                      : "border-green-500 text-green-700 dark:text-green-400 hover:bg-green-50 dark:hover:bg-green-900/30"
                  }`}
                >
                  {selectedUser.is_active ? "⏸ 비활성화" : "✅ 활성화"}
                </button>
                <button
                  onClick={() => handleDelete(selectedUser.id, selectedUser.username)}
                  className="px-4 py-2 text-sm border border-red-500 text-red-700 dark:text-red-400 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/30"
                >
                  🗑 삭제
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}