"use client";

/**
 * 이전 대화 세션 목록 컴포넌트
 * 좌측 사이드바에 표시
 */

interface Session {
  id: string;
  title: string;
  created_at: string;
}

interface SessionListProps {
  sessions: Session[];
  currentSessionId: string | null;
  onSessionSelect: (sessionId: string) => void;
  onNewSession: () => void;
}

export default function SessionList({
  sessions,
  currentSessionId,
  onSessionSelect,
  onNewSession,
}: SessionListProps) {
  return (
    <div className="w-64 bg-white border-r border-gray-200 dark:bg-gray-900 dark:border-gray-700 p-4 flex flex-col h-full">
      <button
        onClick={onNewSession}
        className="mb-4 py-2 px-4 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium"
      >
        + 새 대화
      </button>
      <div className="flex-1 overflow-y-auto">
        <h3 className="text-xs font-semibold text-gray-500 mb-2 uppercase">
          이전 대화
        </h3>
        {sessions.length === 0 ? (
          <p className="text-sm text-gray-400 text-center py-4">
            대화 내역이 없습니다
          </p>
        ) : (
          <ul className="space-y-1">
            {sessions.map((session) => (
              <li key={session.id}>
                <button
                  onClick={() => onSessionSelect(session.id)}
                  className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${
                    currentSessionId === session.id
                      ? "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300"
                      : "hover:bg-gray-100 text-gray-700 dark:hover:bg-gray-800 dark:text-gray-300"
                  }`}
                >
                  <div className="truncate font-medium">{session.title}</div>
                  <div className="text-xs text-gray-500 truncate">
                    {new Date(session.created_at).toLocaleDateString("ko-KR", {
                      year: "numeric",
                      month: "numeric",
                      day: "numeric",
                    })}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}