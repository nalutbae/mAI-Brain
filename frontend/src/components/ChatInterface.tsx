"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import MessageBubble from "./MessageBubble";
import ModeSelector from "./ModeSelector";
import VoiceInput from "./VoiceInput";
import TTSButton from "./TTSButton";
import type { AgentToolResult, ChatMode, ReasoningStrength } from "../lib/api";
import SourceDisplay from "./SourceDisplay";
import AgentToolSelector from "./AgentToolSelector";
import type { AgentToolInfo } from "../lib/api";
import AgentResult from "./AgentResult";
import { chatApi, getSession, submitFeedback, listAgentTools } from "../lib/api";
import type { FeedbackType as ApiFeedbackType, FeedbackTag as ApiFeedbackTag, FeedbackCreate } from "../lib/api";
import type { AgentStep } from "../lib/api";
import { analyzeCrossReasoning } from "../lib/cross-reasoning";
import type { CrossReasoningReport } from "../lib/cross-reasoning";

interface ChatInterfaceProps {
  sessionId?: string;
  onSessionStart?: (sessionId: string) => void;
}

interface Message {
  role: "user" | "assistant";
  content: string;
  sources?: string[];
  agentResults?: AgentToolResult[];  // 에이전트 도구 결과
}

const FEEDBACK_TAGS: { value: ApiFeedbackTag; label: string }[] = [
  { value: "wrong_source", label: "부정확" },
  { value: "irrelevant", label: "관련 없음" },
  { value: "incomplete", label: "불완전" },
  { value: "hallucination", label: "환각" },
  { value: "outdated", label: "구식 정보" },
];

const AGENT_TRIGGER = "@agent";

export default function ChatInterface({ sessionId, onSessionStart }: ChatInterfaceProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [mode, setMode] = useState<ChatMode>("fact");
  const [reasoningStrength, setReasoningStrength] = useState<ReasoningStrength>("all");
  const [isLoading, setIsLoading] = useState(false);
  const [sourceOpen, setSourceOpen] = useState(false);
  const [crossAnalysis, setCrossAnalysis] = useState<CrossReasoningReport | null>(null);
  const [isCrossAnalyzing, setIsCrossAnalyzing] = useState(false);
  const [showCrossResult, setShowCrossResult] = useState(false);
  const [feedbackGiven, setFeedbackGiven] = useState<Record<number, ApiFeedbackType>>({});
  const [showFeedbackTags, setShowFeedbackTags] = useState<number | null>(null);
  const [feedbackComment, setFeedbackComment] = useState("");
  const [selectedTags, setSelectedTags] = useState<ApiFeedbackTag[]>([]);
  const [interimTranscript, setInterimTranscript] = useState("");

  // Agent mode state
  const [availableTools, setAvailableTools] = useState<AgentToolInfo[]>([]);
  const [selectedTools, setSelectedTools] = useState<string[]>([]);
  const [showAgentTools, setShowAgentTools] = useState(false);
  const [agentToolsLoaded, setAgentToolsLoaded] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 세션이 변경될 때 메시지 로드
  useEffect(() => {
    if (sessionId) {
      loadSessionMessages(sessionId);
    }
  }, [sessionId]);

  // 자동 스크롤
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // @agent 프리픽스 감지 → 도구 목록 로드
  useEffect(() => {
    const trimmed = input.trim();
    if (trimmed.startsWith(AGENT_TRIGGER) && !agentToolsLoaded && !isLoading) {
      loadAgentTools();
    }
    // @agent가 아닌 다른 입력으로 바뀌면 도구 선택 UI 숨기기
    if (!trimmed.startsWith(AGENT_TRIGGER) && showAgentTools) {
      setShowAgentTools(false);
      setSelectedTools([]);
    }
  }, [input]);

  const loadAgentTools = async () => {
    try {
      const data = await listAgentTools();
      setAvailableTools(data);
      setAgentToolsLoaded(true);
      // 기본으로 모든 도구 선택
      setSelectedTools(data.map((t) => t.name));
      setShowAgentTools(true);
    } catch (error) {
      console.error("Failed to load agent tools:", error);
    }
  };

  const loadSessionMessages = async (id: string) => {
    try {
      const data = await getSession(id);
      const loadedMessages: Message[] = data.messages.map((msg: any) => ({
        role: msg.role,
        content: msg.content,
        sources: msg.sources?.map((s: any) => s.source || ""),
      }));
      setMessages(loadedMessages);
    } catch (error) {
      console.error("Failed to load session:", error);
    }
  };

  const handleToggleTool = (toolName: string) => {
    setSelectedTools((prev) =>
      prev.includes(toolName)
        ? prev.filter((t) => t !== toolName)
        : [...prev, toolName]
    );
  };

  const handleAgentSubmit = async () => {
    if (!input.trim() || isLoading || selectedTools.length === 0) return;

    // @agent 프리픽스 제거한 질문 추출
    const question = input.trim().replace(new RegExp(`^${AGENT_TRIGGER}\\s*`), "");

    const userMessage: Message = {
      role: "user",
      content: input.trim(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setInterimTranscript("");
    setShowAgentTools(false);
    setIsLoading(true);

    try {
      const response = await chatApi({
        question: question || input.trim(),
        mode: "fact",
        session_id: sessionId,
      });

      const aiMessage: Message = {
        role: "assistant",
        content: response.answer,
        agentResults: response.sources?.map((s) => ({
          type: "tool_result" as const,
          content: s.text.slice(0, 200),
          tool_name: "agent",
        })),
      };

      setMessages((prev) => [...prev, aiMessage]);

      if (!sessionId && response.session_id && onSessionStart) {
        onSessionStart(response.session_id);
      }
    } catch (error) {
      console.error("Failed to execute agent:", error);
      const errorMessage: Message = {
        role: "assistant",
        content: "에이전트 실행 중 오류가 발생했습니다.",
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
      setSelectedTools([]);
    }
  };

  const handleCancelAgent = () => {
    setShowAgentTools(false);
    setSelectedTools([]);
    setInput("");
  };

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;

    // @agent 모드인 경우 → agent 핸들러로 위임
    if (input.trim().startsWith(AGENT_TRIGGER)) {
      if (!agentToolsLoaded) {
        await loadAgentTools();
      }
      if (availableTools.length > 0) {
        setShowAgentTools(true);
      }
      return;
    }

    const userMessage: Message = {
      role: "user",
      content: input.trim(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setInterimTranscript("");
    setIsLoading(true);

    try {
      const response = await chatApi({
        question: userMessage.content,
        mode,
        session_id: sessionId,
        ...((mode === "reasoning" || mode === "column") && { reasoning_strength: reasoningStrength }),
      });

      const aiMessage: Message = {
        role: "assistant",
        content: response.answer,
        sources: mode === "creative" ? undefined : response.sources?.map((s) => s.source),
      };

      setMessages((prev) => [...prev, aiMessage]);

      if (!sessionId && response.session_id && onSessionStart) {
        onSessionStart(response.session_id);
      }
    } catch (error) {
      console.error("Failed to send message:", error);
      const errorMessage: Message = {
        role: "assistant",
        content: "메시지 전송 중 오류가 발생했습니다.",
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // 음성 인식 완료 시 텍스트 입력에 반영
  const handleVoiceTranscript = useCallback(
    (text: string) => {
      if (!text.trim()) return;
      // 기존 입력에 이어서 추가 (띄어쓰기 구분)
      setInput((prev) => {
        const separator = prev && !prev.endsWith(" ") && !prev.endsWith("\n") ? " " : "";
        return prev + separator + text.trim();
      });
    },
    []
  );

  // 음성 인식 중간 결과 표시
  const handleInterimTranscript = useCallback((text: string) => {
    setInterimTranscript(text);
  }, []);

  const handleCrossAnalysis = async () => {
    const lastUserMessage = [...messages].reverse().find((m) => m.role === "user");
    if (!lastUserMessage) return;

    setIsCrossAnalyzing(true);
    setCrossAnalysis(null);
    setShowCrossResult(true);

    try {
      const result = await analyzeCrossReasoning({
        query: lastUserMessage.content,
        mode,
        sub_queries: undefined,
      });
      setCrossAnalysis(result.report);
    } catch (error) {
      console.error("Cross-document analysis failed:", error);
      setCrossAnalysis(null);
    } finally {
      setIsCrossAnalyzing(false);
    }
  };

  const handleFeedback = async (
    messageIndex: number,
    feedbackType: ApiFeedbackType,
    messageContent: string
  ) => {
    if (feedbackGiven[messageIndex]) return;

    if (feedbackType === "thumbs_down") {
      setShowFeedbackTags(messageIndex);
      setSelectedTags([]);
      setFeedbackComment("");
      return;
    }

    // 긍정 피드백은 즉시 전송
    setFeedbackGiven((prev) => ({ ...prev, [messageIndex]: feedbackType }));
    try {
      await submitFeedback({
        session_id: sessionId || "anonymous",
        feedback_type: feedbackType,
      } as FeedbackCreate);
    } catch (error) {
      console.error("Failed to submit feedback:", error);
    }
  };

  const handleSubmitNegativeFeedback = async (messageIndex: number) => {
    setFeedbackGiven((prev) => ({ ...prev, [messageIndex]: "thumbs_down" }));
    setShowFeedbackTags(null);

    try {
      await submitFeedback({
        session_id: sessionId || "anonymous",
        feedback_type: "thumbs_down",
        tags: selectedTags,
        comment: feedbackComment || undefined,
      } as FeedbackCreate);
    } catch (error) {
      console.error("Failed to submit negative feedback:", error);
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 ? (
          <div className="flex items-center justify-center h-full text-gray-400">
            <div className="text-center space-y-2">
              <p>질문을 입력해주세요</p>
              <p className="text-xs text-gray-300 dark:text-gray-600">
                Tip: <code className="bg-gray-100 dark:bg-gray-800 px-1 rounded">@agent</code>를 입력하면 에이전트 모드가 활성화됩니다
              </p>
            </div>
          </div>
        ) : (
          messages.map((message, index) => (
            <div key={index}>
              <MessageBubble message={message} sessionId={sessionId} messageIndex={index} />
              {message.sources && message.sources.length > 0 && (
                <SourceDisplay
                  sources={message.sources}
                  isOpen={sourceOpen}
                  onToggle={() => setSourceOpen(!sourceOpen)}
                />
              )}
              {/* Agent tool results display */}
              {message.agentResults && message.agentResults.length > 0 && (
                <AgentResult steps={message.agentResults} />
              )}
              {/* AI 응답에만 피드백 + TTS 버튼 표시 */}
              {message.role === "assistant" && !isLoading && (
                <div className="flex items-center gap-2 mt-1 ml-2">
                  {feedbackGiven[index] ? (
                    <span className="text-xs text-gray-400">
                      {feedbackGiven[index] === "thumbs_up" ? "👍 피드백 감사합니다" : "👎 피드백 감사합니다"}
                    </span>
                  ) : (
                    <>
                      <button
                        onClick={() => handleFeedback(index, "thumbs_up", message.content)}
                        className="text-sm px-2 py-1 rounded hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-500 hover:text-green-600 transition-colors"
                        title="도움이 되었어요"
                      >
                        👍
                      </button>
                      <button
                        onClick={() => handleFeedback(index, "thumbs_down", message.content)}
                        className="text-sm px-2 py-1 rounded hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-500 hover:text-red-600 transition-colors"
                        title="개선이 필요해요"
                      >
                        👎
                      </button>
                    </>
                  )}
                  {/* 음성 재생 버튼 */}
                  <TTSButton text={message.content} />
                </div>
              )}
              {/* 부정 피드백 태그 선택 UI */}
              {showFeedbackTags === index && (
                <div className="ml-2 p-3 bg-red-50 dark:bg-gray-800 rounded-lg border border-red-200 dark:border-gray-600">
                  <p className="text-xs font-medium text-red-700 dark:text-red-300 mb-2">
                    어떤 점이 아쉬운가요?
                  </p>
                  <div className="flex flex-wrap gap-1 mb-2">
                    {FEEDBACK_TAGS.map((tag) => (
                      <button
                        key={tag.value}
                        onClick={() =>
                          setSelectedTags((prev) =>
                            prev.includes(tag.value)
                              ? prev.filter((t) => t !== tag.value)
                              : [...prev, tag.value]
                          )
                        }
                        className={`text-xs px-2 py-1 rounded-full border transition-colors ${
                          selectedTags.includes(tag.value)
                            ? "bg-red-200 text-red-800 border-red-400 dark:bg-red-700 dark:text-red-100 dark:border-red-500"
                            : "bg-white text-gray-600 border-gray-300 hover:bg-gray-100 dark:bg-gray-700 dark:text-gray-300 dark:border-gray-500"
                        }`}
                      >
                        {tag.label}
                      </button>
                    ))}
                  </div>
                  <textarea
                    value={feedbackComment}
                    onChange={(e) => setFeedbackComment(e.target.value)}
                    placeholder="추가 의견을 남겨주세요 (선택사항)"
                    className="w-full text-xs rounded border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white px-2 py-1 mb-2 resize-none"
                    rows={2}
                  />
                  <div className="flex gap-2">
                    <button
                      onClick={() => handleSubmitNegativeFeedback(index)}
                      className="text-xs px-3 py-1 bg-red-600 text-white rounded hover:bg-red-700 transition-colors"
                    >
                      제출
                    </button>
                    <button
                      onClick={() => setShowFeedbackTags(null)}
                      className="text-xs px-3 py-1 bg-gray-200 text-gray-700 rounded hover:bg-gray-300 dark:bg-gray-600 dark:text-gray-200 transition-colors"
                    >
                      취소
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900">
        <ModeSelector
          mode={mode}
          onChange={setMode}
          reasoningStrength={reasoningStrength}
          onStrengthChange={setReasoningStrength}
        />
        {/* Agent tool selector */}
        {showAgentTools && availableTools.length > 0 && (
          <AgentToolSelector
            tools={availableTools}
            selectedTools={selectedTools}
            onToggle={handleToggleTool}
            onCancel={handleCancelAgent}
            onSubmit={handleAgentSubmit}
            isLoading={isLoading}
          />
        )}
        <div className="p-4 flex gap-2 items-end">
          {/* 음성 입력 버튼 */}
          <VoiceInput
            onTranscript={handleVoiceTranscript}
            onInterimTranscript={handleInterimTranscript}
            disabled={isLoading}
          />
          <div className="flex-1 relative">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder={
                interimTranscript
                  ? `🎤 ${interimTranscript}`
                  : mode === "creative"
                    ? "무엇이든 자유롭게 물어보세요..."
                    : "질문을 입력하세요... (@agent 로 에이전트 모드)"
              }
              className={`w-full resize-none rounded-lg border px-4 py-3 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-800 dark:text-white ${
                interimTranscript
                  ? "border-red-300 dark:border-red-600 ring-2 ring-red-200 dark:ring-red-800"
                  : input.trim().startsWith(AGENT_TRIGGER)
                  ? "border-blue-400 dark:border-blue-500 ring-2 ring-blue-200 dark:ring-blue-800"
                  : "border-gray-300 dark:border-gray-600"
              }`}
              rows={2}
              disabled={isLoading}
            />
            {/* 음성 인식 중 표시 */}
            {interimTranscript && (
              <div className="absolute -top-6 left-0 text-xs text-red-500 dark:text-red-400 flex items-center gap-1">
                <span className="inline-block w-2 h-2 bg-red-500 rounded-full animate-pulse" />
                녹음 중...
              </div>
            )}
            {/* 에이전트 모드 표시 */}
            {input.trim().startsWith(AGENT_TRIGGER) && !interimTranscript && (
              <div className="absolute -top-6 left-0 text-xs text-blue-500 dark:text-blue-400 flex items-center gap-1">
                <span>🤖</span> 에이전트 모드
              </div>
            )}
          </div>
          <div className="flex flex-col gap-2">
            <button
              onClick={handleSend}
              disabled={!input.trim() || isLoading}
              className={`px-6 py-3 text-white rounded-lg transition-colors disabled:bg-gray-300 disabled:cursor-not-allowed ${
                input.trim().startsWith(AGENT_TRIGGER)
                  ? "bg-indigo-600 hover:bg-indigo-700"
                  : "bg-blue-600 hover:bg-blue-700"
              }`}
            >
              {isLoading ? "전송 중..." : input.trim().startsWith(AGENT_TRIGGER) ? "🤖 실행" : "전송"}
            </button>
            {messages.some((m) => m.role === "user") && (
              <button
                onClick={handleCrossAnalysis}
                disabled={isCrossAnalyzing}
                className="px-4 py-2 bg-purple-600 text-white text-sm rounded-lg hover:bg-purple-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors whitespace-nowrap"
                title="마지막 질문에 대해 교차 검증 분석을 실행합니다"
              >
                {isCrossAnalyzing ? "🔍 분석 중..." : "🔍 교차 검증"}
              </button>
            )}
          </div>
        </div>
        {showCrossResult && (
          <div className="border-t border-gray-200 dark:border-gray-700 bg-purple-50 dark:bg-gray-800 p-4 max-h-64 overflow-y-auto">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-semibold text-purple-900 dark:text-purple-300">
                🔍 교차 검증 결과
              </h3>
              <button
                onClick={() => setShowCrossResult(false)}
                className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 text-sm"
              >
                닫기
              </button>
            </div>
            {isCrossAnalyzing ? (
              <p className="text-sm text-gray-600 dark:text-gray-400 animate-pulse">
                문서 간 교차 검증을 분석하고 있습니다...
              </p>
            ) : crossAnalysis ? (
              <div className="space-y-2 text-sm">
                <div className="flex gap-4">
                  <span className="text-red-600 dark:text-red-400">
                    모순: {crossAnalysis.conflicts.length}개
                  </span>
                  <span className="text-green-600 dark:text-green-400">
                    합의: {crossAnalysis.agreements.length}개
                  </span>
                  <span className="text-blue-600 dark:text-blue-400">
                    신뢰도: {(crossAnalysis.confidence * 100).toFixed(0)}%
                  </span>
                </div>
                {crossAnalysis.conflicts.length > 0 && (
                  <details open>
                    <summary className="cursor-pointer font-medium text-red-700 dark:text-red-300">
                      모순/충돌 지점
                    </summary>
                    <div className="mt-1 space-y-1">
                      {crossAnalysis.conflicts.map((c: any, i: number) => (
                        <div key={i} className="pl-2 border-l-2 border-red-300 dark:border-red-600">
                          <p className="font-medium">{c.description}</p>
                          <p className="text-xs text-gray-600 dark:text-gray-400">
                            {c.document_a}: {String(c.claim_a).slice(0, 80)}...
                          </p>
                          <p className="text-xs text-gray-600 dark:text-gray-400">
                            {c.document_b}: {String(c.claim_b).slice(0, 80)}...
                          </p>
                        </div>
                      ))}
                    </div>
                  </details>
                )}
                {crossAnalysis.agreements.length > 0 && (
                  <details>
                    <summary className="cursor-pointer font-medium text-green-700 dark:text-green-300">
                      합의/일치 지점
                    </summary>
                    <div className="mt-1 space-y-1">
                      {crossAnalysis.agreements.map((a: any, i: number) => (
                        <div key={i} className="pl-2 border-l-2 border-green-300 dark:border-green-600">
                          <p className="font-medium">{a.theme}</p>
                          <p className="text-xs text-gray-600 dark:text-gray-400">
                            {String(a.description).slice(0, 100)}... (출처: {a.documents.join(", ")})
                          </p>
                        </div>
                      ))}
                    </div>
                  </details>
                )}
                {crossAnalysis.synthesis && (
                  <details>
                    <summary className="cursor-pointer font-medium text-gray-700 dark:text-gray-300">
                      종합 요약
                    </summary>
                    <p className="mt-1 text-xs text-gray-600 dark:text-gray-400 whitespace-pre-wrap">
                      {crossAnalysis.synthesis}
                    </p>
                  </details>
                )}
              </div>
            ) : (
              <p className="text-sm text-red-600 dark:text-red-400">
                교차 검증 분석에 실패했습니다.
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
