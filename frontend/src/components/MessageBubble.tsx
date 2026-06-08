"use client";

/**
 * 메시지 버블 컴포넌트
 * 사용자/AI 메시지 스타일 분리
 */

interface Message {
  role: "user" | "assistant";
  content: string;
  sources?: string[];
}

interface MessageBubbleProps {
  message: Message;
}

export default function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-4`}>
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-3 ${
          isUser
            ? "bg-blue-600 text-white rounded-br-none"
            : "bg-gray-200 text-gray-800 rounded-bl-none"
        }`}
      >
        <p className="text-sm whitespace-pre-wrap">{message.content}</p>
        {message.sources && message.sources.length > 0 && (
          <div className="mt-2 pt-2 border-t border-black/10 text-xs text-gray-600 dark:text-gray-300">
            <span className="font-medium">출처:</span> {message.sources.join(", ")}
          </div>
        )}
      </div>
    </div>
  );
}