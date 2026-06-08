"use client";

import { useState, useRef, useEffect } from "react";
import MessageBubble from "./MessageBubble";
import ModeSelector from "./ModeSelector";
import type { ChatMode, ReasoningStrength } from "../lib/api";
import SourceDisplay from "./SourceDisplay";
import { chatApi, getSession } from "../lib/api";

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
              <MessageBubble message={message} />
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
          <button
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
            className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
          >
            {isLoading ? "전송 중..." : "전송"}
          </button>
        </div>
      </div>
    </div>
  );
}