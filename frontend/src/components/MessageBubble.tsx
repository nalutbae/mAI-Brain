"use client";

import { useState, useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { submitFeedback, type FeedbackType, type FeedbackTag } from "../lib/api";

// ── Types ──────────────────────────────────────────────────────────────────

interface Citation {
  index: number;
  source: string;
  page?: number;
  text: string;
  score: number;
}

interface Message {
  role: "user" | "assistant";
  content: string;
  sources?: string[];
  citations?: Citation[];
}

interface MessageBubbleProps {
  message: Message;
  sessionId?: string;
  messageIndex?: number;
  isStreaming?: boolean;
}

// ── Inline citation renderer ──────────────────────────────────────────────

/** [[N]] 마커를 치환하여 인용 뱃지가 인라인으로 포함된 텍스트로 변환.
 *  react-markdown의 인라인 HTML 파싱을 위해 [[N]] → <sup class="cite-badge" data-cite="N">N</sup> 치환 후
 *  렌더링 결과에서 클릭 이벤트를 연결합니다. */
function preprocessCitations(
  content: string,
  citations: Citation[] | undefined,
): string {
  if (!citations || citations.length === 0) return content;
  return content.replace(/\[\[(\d+)\]\]/g, (_m, num) => {
    const idx = parseInt(num, 10);
    const c = citations.find((c) => c.index === idx);
    const title = c ? `${c.source}${c.page ? `, p.${c.page}` : ""}` : `인용 ${idx}`;
    return `<sup class="cite-badge" data-cite="${idx}" title="${title}">${idx}</sup>`;
  });
}

// ── Citation detail card ───────────────────────────────────────────────────

function CitationCard({ citation }: { citation: Citation }) {
  return (
    <div className="bg-blue-50 dark:bg-blue-900/30 rounded-lg p-2 text-xs border border-blue-200 dark:border-blue-700">
      <div className="flex items-center gap-1 mb-1">
        <span className="inline-flex items-center justify-center w-5 h-5 text-[10px] font-bold rounded-full bg-blue-500 text-white">
          {citation.index}
        </span>
        <span className="font-medium text-blue-800 dark:text-blue-300 truncate max-w-[200px]">
          {citation.source}
        </span>
        {citation.page != null && (
          <span className="text-gray-500 dark:text-gray-400">
            p.{citation.page}
          </span>
        )}
      </div>
      {citation.text && (
        <p className="text-gray-700 dark:text-gray-300 leading-relaxed line-clamp-3">
          {citation.text}
        </p>
      )}
    </div>
  );
}

// ── Feedback tags ───────────────────────────────────────────────────────────

const FEEDBACK_TAGS: { value: FeedbackTag; label: string }[] = [
  { value: "irrelevant", label: "관련 없음" },
  { value: "incomplete", label: "불완전" },
  { value: "outdated", label: "구식 정보" },
  { value: "hallucination", label: "환각" },
  { value: "wrong_source", label: "잘못된 출처" },
  { value: "biased", label: "편향" },
  { value: "unclear", label: "불분명" },
];

// ── Main component ─────────────────────────────────────────────────────────

export default function MessageBubble({ message, sessionId, messageIndex, isStreaming }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const [feedbackGiven, setFeedbackGiven] = useState<FeedbackType | null>(null);
  const [showTags, setShowTags] = useState(false);
  const [selectedTags, setSelectedTags] = useState<FeedbackTag[]>([]);
  const [comment, setComment] = useState("");
  const [correctionType, setCorrectionType] = useState<"retrieval" | "answer">("answer");
  const [correctionText, setCorrectionText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [showCorrection, setShowCorrection] = useState(false);

  // 인용 상세 팝업 상태
  const [activeCitation, setActiveCitation] = useState<number | null>(null);

  const handleCitationClick = (index: number) => {
    setActiveCitation(activeCitation === index ? null : index);
  };

  // 인용 뱃지가 포함된 콘텐츠 (마크다운 전에 치환)
  const processedContent = useMemo(
    () => preprocessCitations(message.content, message.citations),
    [message.content, message.citations],
  );

  // 렌더링 후 인용 뱃지 클릭 이벤트 연결
  const handleMarkdownRef = (el: HTMLElement | null) => {
    if (!el) return;
    el.querySelectorAll(".cite-badge").forEach((badge) => {
      const idx = parseInt((badge as HTMLElement).dataset.cite || "0", 10);
      badge.addEventListener("click", (e) => {
        e.stopPropagation();
        handleCitationClick(idx);
      });
    });
  };

  // 활성 인용 정보
  const activeCitationData = message.citations?.find((c) => c.index === activeCitation);

  const handleThumbsUp = async () => {
    if (feedbackGiven || submitting) return;
    setFeedbackGiven("thumbs_up");
    setSubmitting(true);
    try {
      await submitFeedback({
        session_id: sessionId ?? "",
        message_index: messageIndex ?? 0,
        feedback_type: "thumbs_up",
      });
    } catch (err) {
      console.error("피드백 제출 실패:", err);
      setFeedbackGiven(null);
    } finally {
      setSubmitting(false);
    }
  };

  const handleThumbsDown = async () => {
    if (feedbackGiven || submitting) return;
    setShowTags(true);
  };

  const handleTagToggle = (tag: FeedbackTag) => {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag],
    );
  };

  const handleSubmitNegativeFeedback = async () => {
    if (submitting) return;
    setSubmitting(true);
    try {
      await submitFeedback({
        session_id: sessionId ?? "",
        message_index: messageIndex ?? 0,
        feedback_type: "thumbs_down",
        tags: selectedTags.length > 0 ? selectedTags : undefined,
        comment: comment || undefined,
        correction_type: showCorrection ? correctionType : undefined,
        correction_text: showCorrection ? correctionText : undefined,
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
            : "bg-gray-200 text-gray-800 dark:bg-gray-700 dark:text-gray-100 rounded-bl-none"
        }`}
      >
        {/* ── 메시지 본문 (마크다운 + 인용 뱃지) ── */}
        <div ref={handleMarkdownRef} className="markdown-body text-sm leading-relaxed">
          {isUser ? (
            <p className="whitespace-pre-wrap">{message.content}</p>
          ) : (
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              rehypePlugins={[rehypeHighlight]}
            >
              {processedContent || (isStreaming ? "" : "")}
            </ReactMarkdown>
          )}
          {isStreaming && (
            <span className="inline-block w-1.5 h-4 ml-0.5 bg-gray-600 dark:bg-gray-300 animate-pulse align-text-bottom rounded-sm" />
          )}
        </div>

        {/* ── 인용 상세 카드 (클릭한 인용) ── */}
        {activeCitationData && (
          <div className="mt-2">
            <CitationCard citation={activeCitationData} />
          </div>
        )}

        {/* ── 전체 출처 목록 (citations가 있으면 인용 카드 목록으로 대체) ── */}
        {message.citations && message.citations.length > 0 && !activeCitation && (
          <div className="mt-2 pt-2 border-t border-black/10 dark:border-white/10">
            <details className="text-xs">
              <summary className="font-medium text-gray-600 dark:text-gray-300 cursor-pointer hover:text-blue-600 dark:hover:text-blue-400">
                📚 출처 {message.citations.length}개
              </summary>
              <div className="mt-1.5 space-y-1.5">
                {message.citations.map((c) => (
                  <button
                    key={c.index}
                    onClick={() => handleCitationClick(c.index)}
                    className="w-full text-left"
                  >
                    <CitationCard citation={c} />
                  </button>
                ))}
              </div>
            </details>
          </div>
        )}

        {/* ── 기존 sources (citations가 없을 때만 표시) ── */}
        {(!message.citations || message.citations.length === 0) && message.sources && message.sources.length > 0 && (
          <div className="mt-2 pt-2 border-t border-black/10 text-xs text-gray-600 dark:text-gray-300">
            <span className="font-medium">출처:</span> {message.sources.join(", ")}
          </div>
        )}

        {/* 👍👎 피드백 버튼 — AI 메시지에만 표시, 스트리밍 중에는 숨김 */}
        {!isUser && !feedbackGiven && !isStreaming && (
          <div className="mt-2 pt-2 border-t border-black/10 dark:border-white/10 flex gap-2">
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
          <div className="mt-2 pt-2 border-t border-black/10 dark:border-white/10 text-xs opacity-60">
            {feedbackGiven === "thumbs_up" ? "👍 평가해 주셔서 감사합니다" : "👎 피드백을 남겨주셔서 감사합니다"}
          </div>
        )}

        {/* 👎 상세 피드백 폼 */}
        {!isUser && feedbackGiven === null && showTags && (
          <div className="mt-2 pt-2 border-t border-black/10 dark:border-white/10 space-y-2">
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