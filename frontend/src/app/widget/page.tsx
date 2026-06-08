"use client";

import { useState, useRef, useEffect, useCallback } from "react";

// ── Types ──────────────────────────────────────────────────────────────────

interface WidgetSettings {
  workspace_id: string;
  allowed_origins: string[];
  theme: string;
  greeting: string;
  primary_color: string;
  position: string;
  logo_url: string | null;
  placeholder: string;
  max_height: string;
  width: string;
}

interface Message {
  role: "user" | "assistant";
  content: string;
}

// ── API helpers ────────────────────────────────────────────────────────────

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchSettings(origin: string): Promise<WidgetSettings> {
  const res = await fetch(`${API_BASE}/api/widget/settings`, {
    headers: { "Content-Type": "application/json", "X-Widget-Origin": origin },
  });
  if (!res.ok) throw new Error("Settings fetch failed");
  return res.json();
}

async function fetchToken(origin: string): Promise<{ token: string }> {
  const res = await fetch(`${API_BASE}/api/widget/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ origin }),
  });
  if (!res.ok) throw new Error("Token fetch failed");
  return res.json();
}

async function sendChat(
  question: string,
  token: string,
  mode: string
): Promise<{ answer: string; session_id: string }> {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ question, mode }),
  });
  if (!res.ok) throw new Error("Chat failed");
  return res.json();
}

// ── Component ──────────────────────────────────────────────────────────────

export default function WidgetPage() {
  const [settings, setSettings] = useState<WidgetSettings | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isOpen, setIsOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 초기화: 설정 로드 + 토큰 발급
  useEffect(() => {
    const origin = window.location.origin;
    Promise.all([fetchSettings(origin), fetchToken(origin)])
      .then(([s, t]) => {
        setSettings(s);
        setToken(t.token);
      })
      .catch((e) => setError(e.message));
  }, []);

  // 자동 스크롤
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = useCallback(async () => {
    if (!input.trim() || isLoading || !token) return;

    const userMsg: Message = { role: "user", content: input.trim() };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsLoading(true);

    try {
      const response = await sendChat(userMsg.content, token, "fact");
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: response.answer },
      ]);
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "죄송합니다. 응답 생성 중 오류가 발생했습니다." },
      ]);
    } finally {
      setIsLoading(false);
    }
  }, [input, isLoading, token]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // 로딩 중 / 에러
  if (error) {
    return (
      <div className="flex items-center justify-center h-screen bg-gray-50">
        <div className="text-center p-6">
          <p className="text-red-500 text-lg mb-2">위젯을 불러올 수 없습니다</p>
          <p className="text-gray-400 text-sm">{error}</p>
        </div>
      </div>
    );
  }

  if (!settings) {
    return (
      <div className="flex items-center justify-center h-screen bg-gray-50">
        <div className="animate-pulse text-gray-400">불러오는 중...</div>
      </div>
    );
  }

  const primaryColor = settings.primary_color;
  const isDark = settings.theme === "dark";
  const bgClass = isDark ? "bg-gray-900" : "bg-white";
  const textClass = isDark ? "text-white" : "text-gray-900";
  const inputBg = isDark ? "bg-gray-800" : "bg-gray-50";
  const borderClass = isDark ? "border-gray-700" : "border-gray-200";
  const userBubbleBg = primaryColor;
  const assistantBubbleBg = isDark ? "bg-gray-800" : "bg-gray-100";

  return (
    <div
      className={`flex flex-col h-screen ${bgClass} ${textClass}`}
      style={{ fontFamily: "system-ui, -apple-system, sans-serif" }}
    >
      {/* 채팅창 토글 버튼 (아이콘 전용 - 접힌 상태) */}
      {!isOpen && (
        <div className="flex items-center justify-center h-full">
          <button
            onClick={() => setIsOpen(true)}
            className="flex flex-col items-center gap-3 px-8 py-6 rounded-2xl shadow-lg hover:shadow-xl transition-all"
            style={{ backgroundColor: primaryColor, color: "#fff" }}
          >
            {settings.logo_url && (
              <img
                src={settings.logo_url}
                alt="Logo"
                className="w-10 h-10 rounded-full"
              />
            )}
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="28"
              height="28"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
            <span className="text-sm font-medium">{settings.greeting}</span>
          </button>
        </div>
      )}

      {/* 채팅 인터페이스 (펼쳐진 상태) */}
      {isOpen && (
        <>
          {/* 헤더 */}
          <div
            className="flex items-center justify-between px-4 py-3 shrink-0"
            style={{ backgroundColor: primaryColor, color: "#fff" }}
          >
            <div className="flex items-center gap-2">
              {settings.logo_url && (
                <img
                  src={settings.logo_url}
                  alt="Logo"
                  className="w-6 h-6 rounded-full"
                />
              )}
              <span className="font-semibold text-sm">mAI-Brain</span>
            </div>
            <button
              onClick={() => setIsOpen(false)}
              className="p-1 rounded hover:bg-white/20 transition-colors"
              aria-label="닫기"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>

          {/* 메시지 영역 */}
          <div className={`flex-1 overflow-y-auto p-4 space-y-3 ${bgClass}`}>
            {messages.length === 0 ? (
              <div className="flex items-center justify-center h-full">
                <p className={isDark ? "text-gray-500" : "text-gray-400"}>
                  {settings.greeting}
                </p>
              </div>
            ) : (
              messages.map((msg, i) => (
                <div
                  key={i}
                  className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className={`max-w-[80%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap ${
                      msg.role === "user"
                        ? "text-white"
                        : `${assistantBubbleBg} ${textClass}`
                    }`}
                    style={
                      msg.role === "user"
                        ? { backgroundColor: userBubbleBg }
                        : undefined
                    }
                  >
                    {msg.content}
                  </div>
                </div>
              ))
            )}
            {isLoading && (
              <div className="flex justify-start">
                <div
                  className={`px-4 py-2.5 rounded-2xl ${assistantBubbleBg}`}
                >
                  <div className="flex gap-1">
                    <span className="w-2 h-2 rounded-full bg-gray-400 animate-bounce" />
                    <span className="w-2 h-2 rounded-full bg-gray-400 animate-bounce [animation-delay:0.15s]" />
                    <span className="w-2 h-2 rounded-full bg-gray-400 animate-bounce [animation-delay:0.3s]" />
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* 입력 영역 */}
          <div className={`p-3 border-t ${borderClass} ${bgClass}`}>
            <div className="flex gap-2">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={settings.placeholder}
                disabled={isLoading}
                className={`flex-1 px-4 py-2.5 rounded-full text-sm border ${borderClass} ${inputBg} ${textClass} focus:outline-none focus:ring-2 disabled:opacity-50`}
                style={{ "--tw-ring-color": primaryColor } as React.CSSProperties}
              />
              <button
                onClick={handleSend}
                disabled={!input.trim() || isLoading}
                className="px-4 py-2.5 rounded-full text-white text-sm font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                style={{ backgroundColor: primaryColor }}
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="18"
                  height="18"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <line x1="22" y1="2" x2="11" y2="13" />
                  <polygon points="22 2 15 22 11 13 2 9 22 2" />
                </svg>
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
