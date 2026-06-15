"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import rehypeHighlight from "rehype-highlight";
import {
  chatStreamApi,
  chatApi,
  fetchAPI,
  type ChatMode,
  type Citation,
} from "../../lib/api";

// ── Types ──────────────────────────────────────────────────────────────────

interface ServiceMessage {
  role: "user" | "assistant" | "system";
  content: string;
  citations?: Citation[];
  sources?: string[];
  timestamp: Date;
}

// ── 자주 묻는 질문 ──────────────────────────────────────────────────────

const FAQ_ITEMS = [
  { icon: "📋", label: "이용 안내", question: "서비스 이용 방법을 알려주세요" },
  { icon: "🕐", label: "운영 시간", question: "운영 시간이 어떻게 되나요?" },
  { icon: "📞", label: "연락처", question: "고객센터 연락처를 알려주세요" },
  { icon: "💰", label: "요금 안내", question: "요금 체계가 어떻게 되나요?" },
];

// ── ServiceChatPage ─────────────────────────────────────────────────────────

export default function ServiceChatPage() {
  const [messages, setMessages] = useState<ServiceMessage[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [showFaq, setShowFaq] = useState(true);
  const [showSources, setShowSources] = useState(false); // 서버 설정에서 로드
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);

  // 초기 인사 메시지 + 서버 설정 로드
  useEffect(() => {
    setMessages([
      {
        role: "assistant",
        content:
          "안녕하세요! 👋 저는 **AI 서비스 어시스턴트**입니다.\n\n궁금한 점이 있으시면 자유롭게 질문해 주세요. 아래 버튼을 클릭하셔도 됩니다.",
        timestamp: new Date(),
      },
    ]);

    // 서버에서 서비스 챗봇 설정 로드
    fetchAPI<{ service_chat?: { show_sources: boolean } }>("/api/settings")
      .then((data) => {
        if (data.service_chat) {
          setShowSources(data.service_chat.show_sources);
        }
      })
      .catch(() => {
        // 설정 로드 실패 시 기본값(false) 유지
      });
  }, []);

  // 자동 스크롤
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = useCallback(
    async (overrideInput?: string) => {
      const question = (overrideInput ?? input).trim();
      if (!question || isLoading || isStreaming) return;

      const userMessage: ServiceMessage = {
        role: "user",
        content: question,
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, userMessage]);
      setInput("");
      setShowFaq(false);
      setIsLoading(true);
      setIsStreaming(true);

      // 스트리밍용 빈 assistant 메시지
      const streamIndex = messages.length + 1;
      const emptyAiMessage: ServiceMessage = {
        role: "assistant",
        content: "",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, emptyAiMessage]);

      let fullAnswer = "";
      let receivedCitations: ServiceMessage["citations"];
      let receivedSources: ServiceMessage["sources"];

      try {
        await chatStreamApi(
          {
            question,
            mode: "fact" as ChatMode,
            session_id: sessionId || undefined,
            service_mode: true,
          },
          {
            onToken: (token: string) => {
              fullAnswer += token;
              setMessages((prev) => {
                const updated = [...prev];
                updated[streamIndex] = {
                  ...updated[streamIndex],
                  content: fullAnswer,
                };
                return updated;
              });
            },
            onCitations: (citations: Citation[]) => {
              receivedCitations = citations;
              setMessages((prev) => {
                const updated = [...prev];
                updated[streamIndex] = {
                  ...updated[streamIndex],
                  citations: receivedCitations,
                };
                return updated;
              });
            },
            onSources: (sources) => {
              receivedSources = sources.map((s) => s.source);
              setMessages((prev) => {
                const updated = [...prev];
                updated[streamIndex] = {
                  ...updated[streamIndex],
                  sources: receivedSources,
                };
                return updated;
              });
            },
            onDone: (newSessionId: string) => {
              setIsLoading(false);
              setIsStreaming(false);
              if (!sessionId && newSessionId) {
                setSessionId(newSessionId);
              }
            },
            onError: (error: string) => {
              console.error("Streaming error:", error);
              if (fullAnswer) {
                setMessages((prev) => {
                  const updated = [...prev];
                  updated[streamIndex] = {
                    ...updated[streamIndex],
                    content: fullAnswer + `\n\n⚠️ 오류: ${error}`,
                  };
                  return updated;
                });
              } else {
                // 폴백
                fallbackToNormalChat(question, streamIndex);
              }
              setIsLoading(false);
              setIsStreaming(false);
            },
          }
        );
      } catch {
        fallbackToNormalChat(question, streamIndex);
      } finally {
        setIsLoading(false);
        setIsStreaming(false);
      }
    },
    [input, isLoading, isStreaming, sessionId, messages.length]
  );

  const fallbackToNormalChat = useCallback(
    async (question: string, streamIndex: number) => {
      setIsStreaming(false);
      try {
        const response = await chatApi({
          question,
          mode: "fact" as ChatMode,
          session_id: sessionId || undefined,
          service_mode: true,
        });
        setMessages((prev) => {
          const updated = [...prev];
          updated[streamIndex] = {
            role: "assistant",
            content: response.answer,
            citations: response.citations,
            sources: response.sources?.map((s) => s.source),
            timestamp: new Date(),
          };
          return updated;
        });
        if (!sessionId && response.session_id) {
          setSessionId(response.session_id);
        }
      } catch {
        setMessages((prev) => {
          const updated = [...prev];
          updated[streamIndex] = {
            role: "assistant",
            content: "죄송합니다. 응답 생성 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
            timestamp: new Date(),
          };
          return updated;
        });
      }
    },
    [sessionId]
  );

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleNewChat = () => {
    setMessages([
      {
        role: "assistant",
        content:
          "안녕하세요! 👋 저는 **AI 서비스 어시스턴트**입니다.\n\n궁금한 점이 있으시면 자유롭게 질문해 주세요. 아래 버튼을 클릭하셔도 됩니다.",
        timestamp: new Date(),
      },
    ]);
    setSessionId(null);
    setInput("");
    setShowFaq(true);
  };

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-full bg-gradient-to-b from-blue-50 to-white dark:from-gray-900 dark:to-gray-950">
      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div className="shrink-0 bg-white dark:bg-gray-900 border-b border-blue-100 dark:border-gray-700 shadow-sm">
        <div className="max-w-3xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-blue-600 flex items-center justify-center text-white text-lg font-bold shadow-md">
              🤖
            </div>
            <div>
              <h1 className="text-lg font-bold text-gray-900 dark:text-white">
                서비스 챗봇
              </h1>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                무엇이든 물어보세요 · AI 기반 실시간 상담
              </p>
            </div>
          </div>
          <button
            onClick={handleNewChat}
            className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg border border-gray-200 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
            title="새 대화 시작"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M12 5v14M5 12h14" />
            </svg>
            새 대화
          </button>
        </div>
      </div>

      {/* ── Messages ─────────────────────────────────────────────────────── */}
      <div
        ref={chatContainerRef}
        className="flex-1 overflow-y-auto"
      >
        <div className="max-w-3xl mx-auto px-4 py-6 space-y-4">
          {messages.map((message, index) => (
            <div key={index}>
              {message.role === "user" ? (
                /* ── 사용자 메시지 ────────────────────────────────────── */
                <div className="flex justify-end">
                  <div className="max-w-[80%] px-4 py-3 rounded-2xl rounded-tr-sm bg-blue-600 text-white shadow-sm">
                    <p className="whitespace-pre-wrap text-sm leading-relaxed">
                      {message.content}
                    </p>
                  </div>
                </div>
              ) : message.role === "system" ? (
                /* ── 시스템 메시지 ────────────────────────────────────── */
                <div className="flex justify-center">
                  <div className="px-4 py-2 rounded-full bg-gray-100 dark:bg-gray-800 text-xs text-gray-500 dark:text-gray-400">
                    {message.content}
                  </div>
                </div>
              ) : (
                /* ── AI 메시지 ────────────────────────────────────────── */
                <div className="flex justify-start">
                  <div className="max-w-[85%]">
                    {/* AI 아바타 + 이름 */}
                    <div className="flex items-center gap-2 mb-1">
                      <div className="w-7 h-7 rounded-full bg-blue-100 dark:bg-blue-900 flex items-center justify-center text-xs">
                        🤖
                      </div>
                      <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
                        AI 어시스턴트
                      </span>
                    </div>
                    {/* 메시지 버블 */}
                    <div className="px-4 py-3 rounded-2xl rounded-tl-sm bg-white dark:bg-gray-800 border border-gray-100 dark:border-gray-700 shadow-sm">
                      {message.content ? (
                        <div className="markdown-body text-sm leading-relaxed text-gray-800 dark:text-gray-200">
                          <ReactMarkdown
                            remarkPlugins={[remarkGfm]}
                            rehypePlugins={[rehypeRaw, rehypeHighlight]}
                          >
                            {message.content}
                          </ReactMarkdown>
                        </div>
                      ) : (
                        /* 스트리밍 로딩 인디케이터 */
                        <div className="flex items-center gap-2 text-gray-400 text-sm">
                          <div className="flex gap-1">
                            <span
                              className="w-2 h-2 rounded-full bg-blue-400"
                              style={{ animation: "bounce 1s infinite" }}
                            />
                            <span
                              className="w-2 h-2 rounded-full bg-blue-400"
                              style={{ animation: "bounce 1s 0.15s infinite" }}
                            />
                            <span
                              className="w-2 h-2 rounded-full bg-blue-400"
                              style={{ animation: "bounce 1s 0.3s infinite" }}
                            />
                          </div>
                          답변을 생성하고 있어요...
                        </div>
                      )}

                      {/* 출처 표시 (서버 설정 show_sources=true인 경우만) */}
                      {showSources && message.sources && message.sources.length > 0 && (
                        <div className="mt-3 pt-3 border-t border-gray-100 dark:border-gray-700">
                          <details className="group">
                            <summary className="text-xs font-medium text-blue-600 dark:text-blue-400 cursor-pointer hover:text-blue-700 dark:hover:text-blue-300 flex items-center gap-1">
                              <svg
                                xmlns="http://www.w3.org/2000/svg"
                                width="12"
                                height="12"
                                viewBox="0 0 24 24"
                                fill="none"
                                stroke="currentColor"
                                strokeWidth="2"
                                strokeLinecap="round"
                                strokeLinejoin="round"
                              >
                                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                                <polyline points="14 2 14 8 20 8" />
                              </svg>
                              출처 ({message.sources.length}건)
                            </summary>
                            <div className="mt-2 flex flex-wrap gap-1.5">
                              {message.sources.map((source, i) => (
                                <span
                                  key={i}
                                  className="inline-flex items-center px-2 py-0.5 text-xs rounded-full bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-800"
                                >
                                  📄 {source}
                                </span>
                              ))}
                            </div>
                          </details>
                        </div>
                      )}

                      {/* 인용 뱃지 (서버 설정 show_sources=true인 경우만) */}
                      {showSources && message.citations && message.citations.length > 0 && (
                        <div className="mt-2">
                          <details className="group">
                            <summary className="text-xs font-medium text-gray-500 dark:text-gray-400 cursor-pointer hover:text-gray-700 dark:hover:text-gray-200">
                              인용 상세 ({message.citations.length}건)
                            </summary>
                            <div className="mt-2 space-y-2">
                              {message.citations.map((c, i) => (
                                <div
                                  key={i}
                                  className="text-xs p-2 rounded-lg bg-gray-50 dark:bg-gray-900 border border-gray-100 dark:border-gray-700"
                                >
                                  <div className="font-medium text-gray-700 dark:text-gray-300 mb-0.5">
                                    {c.source}
                                    {c.page && ` (p.${c.page})`}
                                  </div>
                                  <div className="text-gray-500 dark:text-gray-400 line-clamp-2">
                                    {c.text}
                                  </div>
                                </div>
                              ))}
                            </div>
                          </details>
                        </div>
                      )}
                    </div>

                    {/* 타임스탬프 */}
                    <p className="text-[10px] text-gray-400 dark:text-gray-500 mt-1 ml-9">
                      {message.timestamp.toLocaleTimeString("ko-KR", {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </p>
                  </div>
                </div>
              )}
            </div>
          ))}

          {/* ── 자주 묻는 질문 ─────────────────────────────────────────── */}
          {showFaq && messages.length <= 1 && (
            <div className="pt-2">
              <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-3 text-center">
                자주 묻는 질문
              </p>
              <div className="grid grid-cols-2 gap-2">
                {FAQ_ITEMS.map((faq) => (
                  <button
                    key={faq.label}
                    onClick={() => handleSend(faq.question)}
                    className="flex items-center gap-2 px-4 py-3 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 hover:bg-blue-50 dark:hover:bg-gray-700 hover:border-blue-300 dark:hover:border-blue-600 transition-all text-left group shadow-sm"
                  >
                    <span className="text-lg group-hover:scale-110 transition-transform">
                      {faq.icon}
                    </span>
                    <span className="text-sm font-medium text-gray-700 dark:text-gray-300 group-hover:text-blue-600 dark:group-hover:text-blue-400">
                      {faq.label}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* ── Input ─────────────────────────────────────────────────────────── */}
      <div className="shrink-0 border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900">
        <div className="max-w-3xl mx-auto px-4 py-4">
          <div className="flex gap-2 items-end">
            <div className="flex-1 relative">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyPress}
                placeholder="질문을 입력하세요..."
                disabled={isLoading || isStreaming}
                rows={1}
                className="w-full resize-none rounded-2xl border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-800 px-4 py-3 pr-12 text-sm text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                style={{ maxHeight: "120px" }}
                onInput={(e) => {
                  const target = e.target as HTMLTextAreaElement;
                  target.style.height = "auto";
                  target.style.height = `${Math.min(target.scrollHeight, 120)}px`;
                }}
              />
              {/* 전송 버튼 (입력창 내부) */}
              <button
                onClick={() => handleSend()}
                disabled={!input.trim() || isLoading || isStreaming}
                className="absolute right-2 bottom-2 w-8 h-8 flex items-center justify-center rounded-full bg-blue-600 text-white hover:bg-blue-700 disabled:bg-gray-300 dark:disabled:bg-gray-600 disabled:cursor-not-allowed transition-colors"
                title="전송"
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="16"
                  height="16"
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
          <p className="text-[10px] text-gray-400 dark:text-gray-500 text-center mt-2">
            AI가 생성한 응답이므로 정확하지 않을 수 있습니다 · 중요한 정보는 원본을 확인해 주세요
          </p>
        </div>
      </div>
    </div>
  );
}