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

// ── Types (설정 JSON 스키마와 1:1 매핑) ──────────────────────────────────

interface ServiceChatBranding {
  bot_name: string;
  bot_emoji: string;
  header_title: string;
  header_subtitle: string;
  primary_color: string;
  placeholder_text: string;
}

interface ServiceChatGreeting {
  message: string;
  show_on_new_chat: boolean;
}

interface FaqItem {
  id: string;
  icon: string;
  label: string;
  question: string;
}

interface ServiceChatFaq {
  section_title: string;
  items: FaqItem[];
}

interface QuickReplyOption {
  id: string;
  label: string;
  type: "question" | "answer";
  value: string;
  answer?: string;
}

interface QuickReplyGroup {
  id: string;
  trigger: "first_message" | "after_answer" | "always";
  title: string;
  options: QuickReplyOption[];
}

interface ServiceChatConfig {
  branding: ServiceChatBranding;
  greeting: ServiceChatGreeting;
  workspace?: string;
  faq: ServiceChatFaq;
  quick_replies: { groups: QuickReplyGroup[] };
  disclaimer: string;
}

interface ServiceMessage {
  role: "user" | "assistant" | "system";
  content: string;
  citations?: Citation[];
  sources?: string[];
  timestamp: Date;
}

// ── ServiceChatPage ─────────────────────────────────────────────────────

export default function ServiceChatPage() {
  const [config, setConfig] = useState<ServiceChatConfig | null>(null);
  const [messages, setMessages] = useState<ServiceMessage[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [showSources, setShowSources] = useState(false);
  const [activeQuickReplies, setActiveQuickReplies] = useState<QuickReplyGroup[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);

  // 설정 로드 + 초기 인사
  useEffect(() => {
    loadConfig();
  }, []);

  async function loadConfig() {
    // 두 API를 개별 호출 — 하나가 실패해도 다른 것은 정상 동작
    let cfgData: ServiceChatConfig | null = null;
    let showSourcesValue = false;

    try {
      cfgData = await fetchAPI<ServiceChatConfig>("/api/service-chat/config");
    } catch (e) {
      console.error("[ServiceChat] 설정 로드 실패:", e);
    }

    try {
      const settingsData = await fetchAPI<{ service_chat?: { show_sources: boolean } }>("/api/settings");
      if (settingsData.service_chat) {
        showSourcesValue = settingsData.service_chat.show_sources;
      }
    } catch (e) {
      console.error("[ServiceChat] show_sources 설정 로드 실패:", e);
    }

    if (cfgData) {
      setConfig(cfgData);
      setShowSources(showSourcesValue);
      // 초기 인사 + 첫 메시지용 객관식
      if (cfgData.greeting.show_on_new_chat) {
        setMessages([
          {
            role: "assistant",
            content: cfgData.greeting.message.replace(/\{\{bot_name\}\}/g, cfgData.branding.bot_name),
            timestamp: new Date(),
          },
        ]);
      }
      // first_message 트리거 객관식 표시
      const initialGroups = cfgData.quick_replies.groups.filter(
        (g) => g.trigger === "first_message" || g.trigger === "always"
      );
      setActiveQuickReplies(initialGroups);
    } else {
      // 설정 로드 완전 실패 시 기본값
      setConfig({
        branding: { bot_name: "AI 어시스턴트", bot_emoji: "🤖", header_title: "서비스 챗봇", header_subtitle: "", primary_color: "#2563eb", placeholder_text: "질문을 입력하세요..." },
        greeting: { message: "안녕하세요! 👋 궁금한 점이 있으시면 자유롭게 질문해 주세요.", show_on_new_chat: true },
        faq: { section_title: "자주 묻는 질문", items: [] },
        quick_replies: { groups: [] },
        disclaimer: "",
      });
    }
  }

  // 자동 스크롤
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, activeQuickReplies]);

  // AI 답변 완료 후 after_answer 객관식 표시
  const showPostAnswerQuickReplies = useCallback(() => {
    if (!config) return;
    const postGroups = config.quick_replies.groups.filter(
      (g) => g.trigger === "after_answer" || g.trigger === "always"
    );
    setActiveQuickReplies(postGroups);
  }, [config]);

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
      setActiveQuickReplies([]); // 객관식 숨기기
      setIsLoading(true);
      setIsStreaming(true);

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
            workspace_id: config?.workspace || undefined,
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
              showPostAnswerQuickReplies();
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
    [input, isLoading, isStreaming, sessionId, messages.length, showPostAnswerQuickReplies]
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
          workspace_id: config?.workspace || undefined,
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
      showPostAnswerQuickReplies();
    },
    [sessionId, showPostAnswerQuickReplies]
  );

  // 객관식 선택지 클릭
  const handleQuickReply = useCallback(
    (option: QuickReplyOption) => {
      if (option.type === "answer" && option.answer) {
        // 고정 답변 표시
        const userMsg: ServiceMessage = {
          role: "user",
          content: option.label,
          timestamp: new Date(),
        };
        const aiMsg: ServiceMessage = {
          role: "assistant",
          content: option.answer,
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, userMsg, aiMsg]);
        setActiveQuickReplies([]);
        showPostAnswerQuickReplies();
      } else {
        // LLM에 질문 전송
        handleSend(option.value || option.label);
      }
    },
    [handleSend, showPostAnswerQuickReplies]
  );

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleNewChat = () => {
    if (!config) return;
    if (config.greeting.show_on_new_chat) {
      setMessages([
        {
          role: "assistant",
          content: config.greeting.message.replace(/\{\{bot_name\}\}/g, config.branding.bot_name),
          timestamp: new Date(),
        },
      ]);
    } else {
      setMessages([]);
    }
    setSessionId(null);
    setInput("");
    const initialGroups = config.quick_replies.groups.filter(
      (g) => g.trigger === "first_message" || g.trigger === "always"
    );
    setActiveQuickReplies(initialGroups);
  };

  // 설정 로딩 중
  if (!config) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="flex items-center gap-2 text-gray-400">
          <div className="flex gap-1">
            <span className="w-2 h-2 rounded-full bg-blue-400" style={{ animation: "bounce 1s infinite" }} />
            <span className="w-2 h-2 rounded-full bg-blue-400" style={{ animation: "bounce 1s 0.15s infinite" }} />
            <span className="w-2 h-2 rounded-full bg-blue-400" style={{ animation: "bounce 1s 0.3s infinite" }} />
          </div>
          설정을 불러오는 중...
        </div>
      </div>
    );
  }

  const showFaq = messages.length <= 1 && config.faq.items.length > 0;

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-full bg-gradient-to-b from-blue-50 to-white dark:from-gray-900 dark:to-gray-950">
      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div className="shrink-0 bg-white dark:bg-gray-900 border-b border-blue-100 dark:border-gray-700 shadow-sm">
        <div className="max-w-3xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div
              className="w-10 h-10 rounded-full flex items-center justify-center text-white text-lg font-bold shadow-md"
              style={{ backgroundColor: config.branding.primary_color }}
            >
              {config.branding.bot_emoji}
            </div>
            <div>
              <h1 className="text-lg font-bold text-gray-900 dark:text-white">
                {config.branding.header_title}
              </h1>
              {config.branding.header_subtitle && (
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  {config.branding.header_subtitle}
                </p>
              )}
            </div>
          </div>
          <button
            onClick={handleNewChat}
            className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg border border-gray-200 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
            title="새 대화 시작"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 5v14M5 12h14" />
            </svg>
            새 대화
          </button>
        </div>
      </div>

      {/* ── Messages ─────────────────────────────────────────────────────── */}
      <div ref={chatContainerRef} className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-4 py-6 space-y-4">
          {messages.map((message, index) => (
            <div key={index}>
              {message.role === "user" ? (
                /* ── 사용자 메시지 ────────────────────────────────────── */
                <div className="flex justify-end">
                  <div
                    className="max-w-[80%] px-4 py-3 rounded-2xl rounded-tr-sm text-white shadow-sm"
                    style={{ backgroundColor: config.branding.primary_color }}
                  >
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
                        {config.branding.bot_emoji}
                      </div>
                      <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
                        {config.branding.bot_name}
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
                            <span className="w-2 h-2 rounded-full bg-blue-400" style={{ animation: "bounce 1s infinite" }} />
                            <span className="w-2 h-2 rounded-full bg-blue-400" style={{ animation: "bounce 1s 0.15s infinite" }} />
                            <span className="w-2 h-2 rounded-full bg-blue-400" style={{ animation: "bounce 1s 0.3s infinite" }} />
                          </div>
                          답변을 생성하고 있어요...
                        </div>
                      )}

                      {/* 출처 표시 */}
                      {showSources && message.sources && message.sources.length > 0 && (
                        <div className="mt-3 pt-3 border-t border-gray-100 dark:border-gray-700">
                          <details className="group">
                            <summary className="text-xs font-medium text-blue-600 dark:text-blue-400 cursor-pointer hover:text-blue-700 dark:hover:text-blue-300 flex items-center gap-1">
                              <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                                <polyline points="14 2 14 8 20 8" />
                              </svg>
                              출처 ({message.sources.length}건)
                            </summary>
                            <div className="mt-2 flex flex-wrap gap-1.5">
                              {message.sources.map((source, i) => (
                                <span key={i} className="inline-flex items-center px-2 py-0.5 text-xs rounded-full bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-800">
                                  📄 {source}
                                </span>
                              ))}
                            </div>
                          </details>
                        </div>
                      )}

                      {/* 인용 뱃지 */}
                      {showSources && message.citations && message.citations.length > 0 && (
                        <div className="mt-2">
                          <details className="group">
                            <summary className="text-xs font-medium text-gray-500 dark:text-gray-400 cursor-pointer hover:text-gray-700 dark:hover:text-gray-200">
                              인용 상세 ({message.citations.length}건)
                            </summary>
                            <div className="mt-2 space-y-2">
                              {message.citations.map((c, i) => (
                                <div key={i} className="text-xs p-2 rounded-lg bg-gray-50 dark:bg-gray-900 border border-gray-100 dark:border-gray-700">
                                  <div className="font-medium text-gray-700 dark:text-gray-300 mb-0.5">
                                    {c.source}{c.page && ` (p.${c.page})`}
                                  </div>
                                  <div className="text-gray-500 dark:text-gray-400 line-clamp-2">{c.text}</div>
                                </div>
                              ))}
                            </div>
                          </details>
                        </div>
                      )}
                    </div>

                    {/* 타임스탬프 */}
                    <p className="text-[10px] text-gray-400 dark:text-gray-500 mt-1 ml-9">
                      {message.timestamp.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" })}
                    </p>
                  </div>
                </div>
              )}
            </div>
          ))}

          {/* ── 자주 묻는 질문 ─────────────────────────────────────────── */}
          {showFaq && (
            <div className="pt-2">
              <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-3 text-center">
                {config.faq.section_title}
              </p>
              <div className="grid grid-cols-2 gap-2">
                {config.faq.items.map((faq) => (
                  <button
                    key={faq.id}
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

          {/* ── 객관식 선택지 (Quick Replies) ──────────────────────────── */}
          {activeQuickReplies.length > 0 && !isLoading && !isStreaming && (
            <div className="space-y-3">
              {activeQuickReplies.map((group) => (
                <div key={group.id}>
                  {group.title && (
                    <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">
                      {group.title}
                    </p>
                  )}
                  <div className="flex flex-wrap gap-2">
                    {group.options.map((option) => (
                      <button
                        key={option.id}
                        onClick={() => handleQuickReply(option)}
                        className="px-4 py-2 rounded-full border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-800 hover:border-blue-400 dark:hover:border-blue-500 hover:bg-blue-50 dark:hover:bg-gray-700 transition-all text-sm text-gray-700 dark:text-gray-300 hover:text-blue-600 dark:hover:text-blue-400 shadow-sm"
                      >
                        {option.label}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
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
                placeholder={config.branding.placeholder_text}
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
              <button
                onClick={() => handleSend()}
                disabled={!input.trim() || isLoading || isStreaming}
                className="absolute right-2 bottom-2 w-8 h-8 flex items-center justify-center rounded-full text-white hover:opacity-90 disabled:bg-gray-300 dark:disabled:bg-gray-600 disabled:cursor-not-allowed transition-colors"
                style={{ backgroundColor: config.branding.primary_color }}
                title="전송"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="22" y1="2" x2="11" y2="13" />
                  <polygon points="22 2 15 22 11 13 2 9 22 2" />
                </svg>
              </button>
            </div>
          </div>
          {config.disclaimer && (
            <p className="text-[10px] text-gray-400 dark:text-gray-500 text-center mt-2">
              {config.disclaimer}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}