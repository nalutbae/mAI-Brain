"use client";

import { useState, useEffect } from "react";
import ChatInterface from "../components/ChatInterface";
import SessionList from "../components/SessionList";
import { Session, getSessions, createSession, downloadAllSessionsExport, type ExportFormat } from "../lib/api";

export default function Home() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [exportMenuOpen, setExportMenuOpen] = useState(false);
  const [isExporting, setIsExporting] = useState(false);

  useEffect(() => {
    loadSessions();
  }, []);

  const loadSessions = async () => {
    try {
      const data = await getSessions();
      setSessions(data);
    } catch (error) {
      console.error("Failed to load sessions:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSessionSelect = (sessionId: string) => {
    setCurrentSessionId(sessionId);
  };

  const handleNewSession = async () => {
    try {
      const newSession = await createSession("새 대화");
      setSessions((prev) => [newSession, ...prev]);
      setCurrentSessionId(newSession.id);
    } catch (error) {
      console.error("Failed to create session:", error);
    }
  };

  const handleSessionStart = (sessionId: string) => {
    setCurrentSessionId(sessionId);
    // 세션이 시작되면 세션 목록 새로고침
    loadSessions();
  };

  const handleSessionDelete = (sessionId: string) => {
    setSessions((prev) => prev.filter((s) => s.id !== sessionId));
    if (currentSessionId === sessionId) {
      setCurrentSessionId(null);
    }
  };

  const handleExportAll = async (format: ExportFormat) => {
    setIsExporting(true);
    setExportMenuOpen(false);
    try {
      await downloadAllSessionsExport(format);
    } catch (error) {
      console.error("Export all failed:", error);
      alert("전체 내보내기에 실패했습니다.");
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div className="flex h-full bg-gray-50 dark:bg-black">
      <SessionList
        sessions={sessions}
        currentSessionId={currentSessionId}
        onSessionSelect={handleSessionSelect}
        onNewSession={handleNewSession}
        onSessionDelete={handleSessionDelete}
      />
      <div className="flex-1 flex flex-col">
        <header className="border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
              mAI-Brain
            </h1>
            {currentSessionId && (
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                세션 ID: {currentSessionId}
              </p>
            )}
          </div>

          {/* 전체 대화 내보내기 */}
          <div className="relative">
            <button
              onClick={() => setExportMenuOpen(!exportMenuOpen)}
              disabled={isExporting}
              className="flex items-center gap-2 px-4 py-2 bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-200 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors text-sm font-medium disabled:opacity-50"
              title="전체 대화 내보내기"
            >
              {isExporting ? (
                <>
                  <span className="animate-spin">⏳</span>
                  <span>내보내는 중...</span>
                </>
              ) : (
                <>
                  <span>📦</span>
                  <span>전체 내보내기</span>
                </>
              )}
            </button>
            {exportMenuOpen && (
              <>
                {/* 바깥 클릭 시 닫기 */}
                <div
                  className="fixed inset-0 z-40"
                  onClick={() => setExportMenuOpen(false)}
                />
                <div className="absolute right-0 top-full mt-2 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-lg shadow-lg z-50 py-2 min-w-[160px]">
                  <div className="px-3 py-1.5 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">
                    형식 선택
                  </div>
                  <button
                    onClick={() => handleExportAll("markdown")}
                    className="w-full text-left px-3 py-2 hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-200 flex items-center gap-2"
                  >
                    <span>📝</span>
                    <div>
                      <div className="text-sm font-medium">Markdown</div>
                      <div className="text-xs text-gray-400">가독성 좋은 문서 형식</div>
                    </div>
                  </button>
                  <button
                    onClick={() => handleExportAll("json")}
                    className="w-full text-left px-3 py-2 hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-200 flex items-center gap-2"
                  >
                    <span>{"{ }"}</span>
                    <div>
                      <div className="text-sm font-medium">JSON</div>
                      <div className="text-xs text-gray-400">구조화된 데이터 형식</div>
                    </div>
                  </button>
                  <button
                    onClick={() => handleExportAll("csv")}
                    className="w-full text-left px-3 py-2 hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-200 flex items-center gap-2"
                  >
                    <span>📊</span>
                    <div>
                      <div className="text-sm font-medium">CSV</div>
                      <div className="text-xs text-gray-400">스프레드시트 호환</div>
                    </div>
                  </button>
                </div>
              </>
            )}
          </div>
        </header>
        <ChatInterface
          sessionId={currentSessionId || undefined}
          onSessionStart={handleSessionStart}
        />
      </div>
    </div>
  );
}