"use client";

import { useState, useRef, useEffect, useCallback } from "react";

// ── Types ──────────────────────────────────────────────────────────────────

interface WidgetTheme {
  primary_color: string;
  background_color: string;
  text_color: string;
  user_bubble_color: string;
  user_bubble_text_color: string;
  assistant_bubble_color: string;
  assistant_bubble_text_color: string;
  border_radius: string;
  font_family: string;
}

interface WidgetConfig {
  id: string;
  name: string;
  workspace_id: string | null;
  allowed_origins: string[];
  greeting: string;
  theme: WidgetTheme;
  position: string;
  logo_url: string | null;
  placeholder: string;
  is_active: boolean;
}

interface TokenResponse {
  token: string;
  widget_id: string;
  expires_at: string;
  config: WidgetConfig;
}

interface Message {
  role: "user" | "assistant";
  content: string;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchToken(
  widgetId: string,
  origin: string
): Promise<TokenResponse> {
  const res = await fetch(`${API_BASE}/api/widget/${widgetId}/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ widget_id: widgetId, origin }),
  });
  if (!res.ok) throw new Error("Token fetch failed");
  return res.json();
}

async function sendChat(
  question: string,
  token: string,
  mode: string = "fact"
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

export default function WidgetPage() {
  const [config, setConfig] = useState<WidgetConfig | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isOpen, setIsOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const getWidgetId = useCallback(() => {
    if (typeof window === "undefined") return "default";
    const params = new URLSearchParams(window.location.search);
    return params.get("widget_id") || "default";
  }, []);

  useEffect(() => {
    const widgetId = getWidgetId();
    const origin = window.location.origin;
    fetchToken(widgetId, origin)
      .then((resp) => {
        setToken(resp.token);
        setConfig(resp.config);
      })
      .catch((e) => setError(e.message));
  }, [getWidgetId]);

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
      const response = await sendChat(userMsg.content, token);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: response.answer },
      ]);
    } catch {
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

  if (error) {
    return (
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "center",
        height: "100vh", fontFamily: "system-ui, sans-serif",
        background: "#f9fafb", color: "#ef4444",
        flexDirection: "column", gap: "8px",
      }}>
        <p style={{ fontSize: "18px", fontWeight: 600, margin: 0 }}>
          위젯을 불러올 수 없습니다
        </p>
        <p style={{ fontSize: "14px", color: "#9ca3af", margin: 0 }}>{error}</p>
      </div>
    );
  }

  if (!config) {
    return (
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "center",
        height: "100vh", fontFamily: "system-ui, sans-serif",
        background: "#f9fafb", color: "#9ca3af",
      }}>
        <span>불러오는 중...</span>
      </div>
    );
  }

  const t = config.theme;
  const bg = t.background_color;
  const txt = t.text_color;
  const bc = "#e5e7eb";

  return (
    <div style={{
      display: "flex", flexDirection: "column", height: "100vh",
      fontFamily: t.font_family, background: bg, color: txt,
    }}>
      {!isOpen ? (
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "center",
          height: "100%",
        }}>
          <button
            onClick={() => setIsOpen(true)}
            style={{
              display: "flex", flexDirection: "column", alignItems: "center",
              gap: "12px", padding: "24px 32px", borderRadius: "16px",
              border: "none", cursor: "pointer", background: t.primary_color,
              color: "#fff", boxShadow: "0 4px 16px rgba(0,0,0,0.15)",
              fontFamily: "inherit",
            }}
          >
            {config.logo_url && (
              <img src={config.logo_url} alt="Logo"
                style={{ width: "40px", height: "40px", borderRadius: "50%" }} />
            )}
            <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28"
              viewBox="0 0 24 24" fill="none" stroke="currentColor"
              strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
            <span style={{ fontSize: "14px", fontWeight: 500 }}>
              {config.greeting}
            </span>
          </button>
        </div>
      ) : (
        <>
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            padding: "12px 16px", background: t.primary_color, color: "#fff",
            flexShrink: 0,
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              {config.logo_url && (
                <img src={config.logo_url} alt="Logo"
                  style={{ width: "24px", height: "24px", borderRadius: "50%" }} />
              )}
              <span style={{ fontWeight: 600, fontSize: "14px" }}>{config.name}</span>
            </div>
            <button onClick={() => setIsOpen(false)} aria-label="닫기"
              style={{ padding: "4px", borderRadius: "4px", border: "none",
                background: "transparent", color: "#fff", cursor: "pointer" }}>
              ✕
            </button>
          </div>

          <div style={{
            flex: 1, overflowY: "auto", padding: "16px",
            display: "flex", flexDirection: "column", gap: "12px", background: bg,
          }}>
            {messages.length === 0 ? (
              <div style={{
                display: "flex", alignItems: "center", justifyContent: "center",
                height: "100%", color: "#9ca3af", fontSize: "14px",
              }}>
                {config.greeting}
              </div>
            ) : (
              messages.map((msg, i) => (
                <div key={i} style={{
                  display: "flex",
                  justifyContent: msg.role === "user" ? "flex-end" : "flex-start",
                }}>
                  <div style={{
                    maxWidth: "80%", padding: "10px 16px",
                    borderRadius: t.border_radius, fontSize: "14px",
                    lineHeight: 1.6, whiteSpace: "pre-wrap", wordBreak: "break-word",
                    background: msg.role === "user"
                      ? t.user_bubble_color : t.assistant_bubble_color,
                    color: msg.role === "user"
                      ? t.user_bubble_text_color : t.assistant_bubble_text_color,
                  }}>
                    {msg.content}
                  </div>
                </div>
              ))
            )}
            {isLoading && (
              <div style={{ display: "flex", justifyContent: "flex-start" }}>
                <div style={{
                  padding: "10px 16px", borderRadius: t.border_radius,
                  background: t.assistant_bubble_color,
                }}>
                  <div style={{ display: "flex", gap: "4px" }}>
                    <span style={{
                      width: "8px", height: "8px", borderRadius: "50%",
                      background: "#9ca3af", animation: "bounce 0.6s infinite",
                    }} />
                    <span style={{
                      width: "8px", height: "8px", borderRadius: "50%",
                      background: "#9ca3af", animation: "bounce 0.6s 0.15s infinite",
                    }} />
                    <span style={{
                      width: "8px", height: "8px", borderRadius: "50%",
                      background: "#9ca3af", animation: "bounce 0.6s 0.3s infinite",
                    }} />
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          <div style={{
            padding: "12px", borderTop: `1px solid ${bc}`,
            background: bg, flexShrink: 0,
          }}>
            <div style={{ display: "flex", gap: "8px" }}>
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={config.placeholder}
                disabled={isLoading}
                style={{
                  flex: 1, padding: "10px 16px", borderRadius: "24px",
                  border: `1px solid ${bc}`, fontSize: "14px",
                  outline: "none", background: bg, color: txt,
                  fontFamily: "inherit",
                }}
              />
              <button
                onClick={handleSend}
                disabled={!input.trim() || isLoading}
                style={{
                  padding: "10px 16px", borderRadius: "24px", border: "none",
                  cursor: "pointer", background: t.primary_color, color: "#fff",
                  opacity: !input.trim() || isLoading ? 0.5 : 1,
                  fontFamily: "inherit",
                }}
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18"
                  viewBox="0 0 24 24" fill="none" stroke="currentColor"
                  strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
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
