"use client";

import { useState } from "react";
import { deleteSession, downloadSessionExport, downloadAllSessionsExport, type ExportFormat } from "../lib/api";

/**
 * 이전 대화 세션 목록 컴포넌트
 * 좌측 사이드바에 표시
 * 세션별 내보내기(다운로드) 버튼 포함
 */

interface Session {
  id: string;
  title: string;
  created_at: string;
  updated_at?: string;
  message_count?: number;
}

interface SessionListProps {
  sessions: Session[];
  currentSessionId: string | null;
  onSessionSelect: (sessionId: string) => void;
  onNewSession: () => void;
  onSessionDelete?: (sessionId: string) => void;
}

const EXPORT_FORMATS: { value: ExportFormat; label: string; icon: string }[] = [
  { value: "markdown", label: "MD", icon: "📝" },
  { value: "json", label: "JSON", icon: "{ }" },
  { value: "csv", label: "CSV", icon: "📊" },
];

export default function SessionList({
  sessions,
  currentSessionId,
  onSessionSelect,
  onNewSession,
  onSessionDelete,
}: SessionListProps) {
  const [exportMenuOpen, setExportMenuOpen] = useState<string | null>(null);
  const [exporting, setExporting] = useState<string | null>(null);
  const [exportAllMenuOpen, setExportAllMenuOpen] = useState(false);
  const [exportingAll, setExportingAll] = useState(false);

  const handleExport = async (sessionId: string, format: ExportFormat) => {
    setExporting(sessionId);
    setExportMenuOpen(null);
    try {
      await downloadSessionExport(sessionId, format);
    } catch (error) {
      console.error("Export failed:", error);
      alert("내보내기에 실패했습니다.");
    } finally {
      setExporting(null);
    }
  };

  const handleDelete = async (sessionId: string) => {
    if (!confirm("이 대화를 삭제하시겠습니까?")) return;
    try {
      await deleteSession(sessionId);
      onSessionDelete?.(sessionId);
    } catch (error) {
      console.error("Delete failed:", error);
      alert("삭제에 실패했습니다.");
    }
  };

  const handleExportAll = async (format: ExportFormat) => {
    setExportingAll(true);
    setExportAllMenuOpen(false);
    try {
      await downloadAllSessionsExport(format);
    } catch (error) {
      console.error("Export all failed:", error);
      alert("전체 내보내기에 실패했습니다.");
    } finally {
      setExportingAll(false);
    }
  };

  return (
    <div className="w-64 bg-white border-r border-gray-200 dark:bg-gray-900 dark:border-gray-700 p-4 flex flex-col h-full">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-bold text-gray-700 dark:text-gray-200">
          대화 목록
        </h2>
        <div className="flex items-center gap-1">
          {/* 전체 내보내기 드롭다운 */}
          <div className="relative">
            <button
              onClick={() => setExportAllMenuOpen(!exportAllMenuOpen)}
              disabled={exportingAll}
              className="py-1.5 px-2 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 transition-colors text-xs font-medium rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700"
              title="전체 대화 내보내기"
            >
              {exportingAll ? "⏳" : "📥"}
            </button>
            {exportAllMenuOpen && (
              <div className="absolute right-0 top-full mt-1 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-lg shadow-lg z-50 py-1 min-w-[100px]">
                {EXPORT_FORMATS.map((fmt) => (
                  <button
                    key={fmt.value}
                    onClick={() => handleExportAll(fmt.value)}
                    className="w-full text-left px-3 py-1.5 text-xs hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-200 flex items-center gap-2"
                  >
                    <span>{fmt.icon}</span>
                    <span>전체 {fmt.label}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
          <button
            onClick={onNewSession}
            className="py-1.5 px-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-xs font-medium"
          >
            + 새 대화
          </button>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto">
        {sessions.length === 0 ? (
          <p className="text-sm text-gray-400 text-center py-4">
            대화 내역이 없습니다
          </p>
        ) : (
          <ul className="space-y-1">
            {sessions.map((session) => (
              <li key={session.id} className="group relative">
                <button
                  onClick={() => onSessionSelect(session.id)}
                  className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors pr-8 ${
                    currentSessionId === session.id
                      ? "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300"
                      : "hover:bg-gray-100 text-gray-700 dark:hover:bg-gray-800 dark:text-gray-300"
                  }`}
                >
                  <div className="truncate font-medium">{session.title}</div>
                  <div className="flex items-center gap-2 text-xs text-gray-500">
                    <span>
                      {new Date(session.created_at).toLocaleDateString("ko-KR", {
                        year: "numeric",
                        month: "numeric",
                        day: "numeric",
                      })}
                    </span>
                    {session.message_count !== undefined && (
                      <span className="text-gray-400">
                        {session.message_count}개 메시지
                      </span>
                    )}
                  </div>
                </button>

                {/* 세션별 액션 버튼 (hover 시 표시) */}
                <div className="absolute right-1 top-1.5 flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                  {/* 내보내기 드롭다운 */}
                  <div className="relative">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setExportMenuOpen(
                          exportMenuOpen === session.id ? null : session.id
                        );
                      }}
                      disabled={exporting === session.id}
                      className="p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 text-xs"
                      title="내보내기"
                    >
                      {exporting === session.id ? "⏳" : "⬇️"}
                    </button>
                    {exportMenuOpen === session.id && (
                      <div className="absolute left-0 top-full mt-1 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-lg shadow-lg z-50 py-1 min-w-[100px]">
                        {EXPORT_FORMATS.map((fmt) => (
                          <button
                            key={fmt.value}
                            onClick={(e) => {
                              e.stopPropagation();
                              handleExport(session.id, fmt.value);
                            }}
                            className="w-full text-left px-3 py-1.5 text-xs hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-200 flex items-center gap-2"
                          >
                            <span>{fmt.icon}</span>
                            <span>{fmt.label}</span>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* 삭제 버튼 */}
                  {onSessionDelete && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDelete(session.id);
                      }}
                      className="p-1 rounded hover:bg-red-100 dark:hover:bg-red-900 text-gray-400 hover:text-red-500 text-xs"
                      title="삭제"
                    >
                      🗑️
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}