"use client";

import { useState } from "react";
import { submitFeedback, type FeedbackType, type FeedbackTag } from "../lib/api";

/**
 * 메시지 버블 컴포넌트
 * 사용자/AI 메시지 스타일 분리 + 👍👎 피드백 버튼
 */

interface Message {
  role: "user" | "assistant";
  content: string;
  sources?: string[];
}

interface MessageBubbleProps {
  message: Message;
  sessionId?: string;
  messageIndex?: number;
}

const FEEDBACK_TAGS: { value: FeedbackTag; label: string }[] = [
  { value: "irrelevant", label: "관련 없음" },
  { value: "incomplete", label: "불완전" },
  { value: "outdated", label: "구식 정보" },
  { value: "hallucination", label: "환각" },
  { value: "wrong_source", label: "잘못된 출처" },
  { value: "biased", label: "편향" },
  { value: "unclear", label: "불분명" },
];

export default function MessageBubble({ message, sessionId, messageIndex }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const [feedbackGiven, setFeedbackGiven] = useState<FeedbackType | null>(null);
  const [showTags, setShowTags] = useState(false);
  const [selectedTags, setSelectedTags] = useState<FeedbackTag[]>([]);
  const [comment, setComment] = useState("");
  const [correctionType, setCorrectionType] = useState<"retrieval" | "answer">("answer");
  const [correctionText, setCorrectionText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [showCorrection, setShowCorrection] = useState(false);

  const handleThumbsUp = async () => {
    if (feedbackGiven || submitting) return;
    setFeedbackGiven("thumbs_up");
    setSubmitting(true);
    try {
      await submitFeedback({
        session_id: sessionId,
        query: "", // will be filled by ChatInterface
        answer: message.content.slice(0, 500),
        feedback_type: "thumbs_up",
      });
    } catch (err) {
      console.error("피드백 제출 실패:", err);
    } finally {
      setSubmitting(false);
    }
  };

  const handleThumbsDown = () => {
    if (feedbackGiven) return;
    setFeedbackGiven("thumbs_down");
    setShowTags(true);
  };

  const handleTagToggle = (tag: FeedbackTag) => {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]
    );
  };

  const handleSubmitNegativeFeedback = async () => {
    if (submitting) return;
    setSubmitting(true);
    try {
      await submitFeedback({
        session_id: sessionId,
        query: "",
        answer: message.content.slice(0, 500),
        feedback_type: "thumbs_down",
        tags: selectedTags,
        comment,
        ...(showCorrection && correctionText
          ? { correction_type: correctionType, correction_text: correctionText }
          : {}),
      });
      setShowTags(false);
    } catch (err) {
      console.error("피드백 제출 실패:", err);
    } finally {
      setSubmitting(false);
    }
  };

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

        {/* 👍👎 피드백 버튼 — AI 메시지에만 표시 */}
        {!isUser && !feedbackGiven && (
          <div className="mt-2 pt-2 border-t border-black/10 flex gap-2">
            <button
              onClick={handleThumbsUp}
              disabled={submitting}
              className="text-lg hover:scale-110 transition-transform opacity-60 hover:opacity-100"
              title="좋은 답변이에요"
            >
              👍
            </button>
            <button
              onClick={handleThumbsDown}
              className="text-lg hover:scale-110 transition-transform opacity-60 hover:opacity-100"
              title="답변에 문제가 있어요"
            >
              👎
            </button>
          </div>
        )}

        {/* 피드백 완료 표시 */}
        {!isUser && feedbackGiven && (
          <div className="mt-2 pt-2 border-t border-black/10 text-xs opacity-60">
            {feedbackGiven === "thumbs_up" ? "👍 평가해 주셔서 감사합니다" : "👎 피드백을 남겨주셔서 감사합니다"}
          </div>
        )}

        {/* 👎 피드백 상세 폼 */}
        {!isUser && showTags && (
          <div className="mt-3 pt-3 border-t border-black/10 space-y-3">
            <p className="text-xs font-medium text-gray-700 dark:text-gray-300">어떤 문제가 있었나요?</p>
            <div className="flex flex-wrap gap-1.5">
              {FEEDBACK_TAGS.map((tag) => (
                <button
                  key={tag.value}
                  onClick={() => handleTagToggle(tag.value)}
                  className={`px-2 py-1 text-xs rounded-full border transition-colors ${
                    selectedTags.includes(tag.value)
                      ? "bg-red-100 border-red-300 text-red-700 dark:bg-red-900 dark:border-red-700 dark:text-red-300"
                      : "bg-white border-gray-300 text-gray-600 hover:bg-gray-50 dark:bg-gray-700 dark:border-gray-500 dark:text-gray-300"
                  }`}
                >
                  {tag.label}
                </button>
              ))}
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                코멘트 (선택)
              </label>
              <textarea
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-2 py-1.5 text-xs text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500"
                rows={2}
                placeholder="어떻게 개선되면 좋을지 알려주세요"
              />
            </div>

            <button
              onClick={() => setShowCorrection(!showCorrection)}
              className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
            >
              {showCorrection ? "− 정정 정보 숨기기" : "+ 정정 정보 추가"}
            </button>

            {showCorrection && (
              <div className="space-y-2">
                <div className="flex gap-2">
                  <button
                    onClick={() => setCorrectionType("retrieval")}
                    className={`px-2 py-1 text-xs rounded-md ${
                      correctionType === "retrieval"
                        ? "bg-blue-600 text-white"
                        : "bg-gray-200 dark:bg-gray-600 text-gray-700 dark:text-gray-300"
                    }`}
                  >
                    검색 정정
                  </button>
                  <button
                    onClick={() => setCorrectionType("answer")}
                    className={`px-2 py-1 text-xs rounded-md ${
                      correctionType === "answer"
                        ? "bg-blue-600 text-white"
                        : "bg-gray-200 dark:bg-gray-600 text-gray-700 dark:text-gray-300"
                    }`}
                  >
                    응답 정정
                  </button>
                </div>
                <textarea
                  value={correctionText}
                  onChange={(e) => setCorrectionText(e.target.value)}
                  className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-2 py-1.5 text-xs text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500"
                  rows={2}
                  placeholder="올바른 정보를 입력해주세요"
                />
              </div>
            )}

            <div className="flex gap-2">
              <button
                onClick={handleSubmitNegativeFeedback}
                disabled={submitting}
                className="px-3 py-1.5 bg-red-600 text-white text-xs rounded-md hover:bg-red-700 disabled:opacity-50"
              >
                {submitting ? "제출 중..." : "피드백 제출"}
              </button>
              <button
                onClick={() => {
                  setShowTags(false);
                  setFeedbackGiven(null);
                }}
                className="px-3 py-1.5 bg-gray-200 dark:bg-gray-600 text-gray-700 dark:text-gray-200 text-xs rounded-md hover:bg-gray-300"
              >
                취소
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}