"use client";

import { useState, useRef, useEffect } from "react";
import MessageBubble from "./MessageBubble";
import ModeSelector from "./ModeSelector";
import type { ChatMode, ReasoningStrength } from "../lib/api";
import SourceDisplay from "./SourceDisplay";
import { chatApi, getSession } from "../lib/api";
import { analyzeCrossDocument, type CrossAnalysis } from "../lib/cross-reasoning";
import { submitFeedback, type FeedbackType, type FeedbackTag } from "../lib/feedback";

interface ChatInterfaceProps {
  sessionId?: string;
  onSessionStart?: (sessionId: string) => void;
}

interface Message {
  role: "user" | "assistant";
  content: string;
  sources?: string[];
}

export default function ChatInterface({ sessionId, onSessionStart }: ChatInterfaceProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [mode, setMode] = useState<ChatMode>("fact");
  const [reasoningStrength, setReasoningStrength] = useState<ReasoningStrength>("all");
  const [isLoading, setIsLoading] = useState(false);
  const [sourceOpen, setSourceOpen] = useState(false);
  const [crossAnalysis, setCrossAnalysis] = useState<CrossAnalysis | null>(null);
  const [isCrossAnalyzing, setIsCrossAnalyzing] = useState(false);
  const [showCrossResult, setShowCrossResult] = useState(false);
  const [feedbackGiven, setFeedbackGiven] = useState<Record<number, FeedbackType>>({});
  const [showFeedbackTags, setShowFeedbackTags] = useState<number | null>(null);
  const [feedbackComment, setFeedbackComment] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 세션이 변경될 때 메시지 로드
  useEffect(() => {
    if (sessionId) {
      // TODO: 세션 메시지 로드
      loadSessionMessages(sessionId);
    }
  }, [sessionId]);

  // 자동 스크롤
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

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

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;

    const userMessage: Message = {
      role: "user",
      content: input.trim(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
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
        sources: response.sources?.map((s) => s.source),
      };

      setMessages((prev) => [...prev, aiMessage]);

      // 새 세션이 생성된 경우 session_id를 상위로 전달
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

  const handleCrossAnalysis = async () => {
    const lastUserMessage = [...messages].reverse().find((m) => m.role === "user");
    if (!lastUserMessage) return;

    setIsCrossAnalyzing(true);
    setCrossAnalysis(null);
    setShowCrossResult(true);

    try {
      const result = await analyzeCrossDocument({
        query: lastUserMessage.content,
        mode,
        max_sub_queries: 3,
      });
      setCrossAnalysis(result);
    } catch (error) {
      console.error("Cross-document analysis failed:", error);
      setCrossAnalysis(null);
    } finally {
      setIsCrossAnalyzing(false);
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 ? (
          <div className="flex items-center justify-center h-full text-gray-400">
            <p>질문을 입력해주세요</p>
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
        <div className="p-4 flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="질문을 입력하세요..."
            className="flex-1 resize-none rounded-lg border border-gray-300 px-4 py-3 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-800 dark:text-white"
            rows={2}
            disabled={isLoading}
          />
          <div className="flex flex-col gap-2">
            <button
              onClick={handleSend}
              disabled={!input.trim() || isLoading}
              className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
            >
              {isLoading ? "전송 중..." : "전송"}
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
                    합의: {crossAnalysis.consensuses.length}개
                  </span>
                  <span className="text-blue-600 dark:text-blue-400">
                    신뢰도: {(crossAnalysis.confidence_score * 100).toFixed(0)}%
                  </span>
                </div>
                {crossAnalysis.conflicts.length > 0 && (
                  <details open>
                    <summary className="cursor-pointer font-medium text-red-700 dark:text-red-300">
                      모순/충돌 지점
                    </summary>
                    <div className="mt-1 space-y-1">
                      {crossAnalysis.conflicts.map((c, i) => (
                        <div key={i} className="pl-2 border-l-2 border-red-300 dark:border-red-600">
                          <p className="font-medium">{c.topic}</p>
                          <p className="text-xs text-gray-600 dark:text-gray-400">
                            {c.source_a}: {c.claim_a.slice(0, 80)}...
                          </p>
                          <p className="text-xs text-gray-600 dark:text-gray-400">
                            {c.source_b}: {c.claim_b.slice(0, 80)}...
                          </p>
                        </div>
                      ))}
                    </div>
                  </details>
                )}
                {crossAnalysis.consensuses.length > 0 && (
                  <details>
                    <summary className="cursor-pointer font-medium text-green-700 dark:text-green-300">
                      합의/일치 지점
                    </summary>
                    <div className="mt-1 space-y-1">
                      {crossAnalysis.consensuses.map((c, i) => (
                        <div key={i} className="pl-2 border-l-2 border-green-300 dark:border-green-600">
                          <p className="font-medium">{c.topic}</p>
                          <p className="text-xs text-gray-600 dark:text-gray-400">
                            {c.consensus.slice(0, 100)}... (출처: {c.sources.join(", ")})
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