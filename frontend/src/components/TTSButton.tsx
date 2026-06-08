"use client";

import { useCallback, useState } from "react";
import { useSpeechSynthesis } from "../hooks/useSpeechSynthesis";

/**
 * TTS 재생 버튼 컴포넌트
 * AI 응답 텍스트를 음성으로 재생하는 스피커 아이콘 버튼
 * 재생/일시정지/중지 상태 표시
 */

interface TTSButtonProps {
  /** 읽어줄 텍스트 */
  text: string;
  /** 추가 CSS 클래스 */
  className?: string;
  /** 비활성화 여부 */
  disabled?: boolean;
}

export default function TTSButton({
  text,
  className = "",
  disabled = false,
}: TTSButtonProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const { isSpeaking, isPaused, isSupported, speak, cancel, pause, resume, error } =
    useSpeechSynthesis({
      lang: "ko-KR",
      rate: 1.0,
      pitch: 1.0,
    });

  const handleClick = useCallback(() => {
    if (disabled || !text) return;

    if (isSpeaking && !isPaused) {
      // 재생 중 → 일시정지
      pause();
    } else if (isPaused) {
      // 일시정지 → 재생
      resume();
    } else {
      // 정지 상태 → 재생 시작
      speak(text);
    }
  }, [disabled, text, isSpeaking, isPaused, speak, pause, resume]);

  const handleStop = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      cancel();
    },
    [cancel]
  );

  const toggleExpand = useCallback(() => {
    setIsExpanded((prev) => !prev);
  }, []);

  if (!isSupported) {
    return null;
  }

  return (
    <div className="relative inline-flex items-center gap-1">
      <button
        onClick={handleClick}
        disabled={disabled || !text}
        className={`flex items-center justify-center w-7 h-7 rounded-full transition-all duration-200 ${
          isSpeaking
            ? "bg-blue-100 dark:bg-blue-900 text-blue-600 dark:text-blue-400 shadow-sm"
            : "text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700"
        } ${disabled || !text ? "opacity-30 cursor-not-allowed" : "cursor-pointer"} ${className}`}
        title={
          isSpeaking && !isPaused
            ? "일시정지"
            : isPaused
            ? "다시 재생"
            : "음성으로 듣기"
        }
        aria-label={
          isSpeaking && !isPaused
            ? "일시정지"
            : isPaused
            ? "다시 재생"
            : "음성으로 듣기"
        }
      >
        {isSpeaking && !isPaused ? (
          // 일시정지 아이콘
          <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
            <rect x="6" y="4" width="4" height="16" rx="1" />
            <rect x="14" y="4" width="4" height="16" rx="1" />
          </svg>
        ) : isPaused ? (
          // 재생 아이콘 (일시정지 해제)
          <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
            <polygon points="5,3 19,12 5,21" />
          </svg>
        ) : (
          // 스피커 아이콘 (기본)
          <svg
            className="w-4 h-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M15.536 8.464a5 5 0 0 1 0 7.072M18.364 5.636a9 9 0 0 1 0 12.728M11 5L6 9H2v6h4l5 4V5z"
            />
          </svg>
        )}
      </button>

      {/* 재생 중 정지 버튼 */}
      {isSpeaking && (
        <button
          onClick={handleStop}
          className="flex items-center justify-center w-6 h-6 rounded-full bg-red-100 dark:bg-red-900 text-red-600 dark:text-red-400 hover:bg-red-200 dark:hover:bg-red-800 transition-colors cursor-pointer"
          title="정지"
          aria-label="정지"
        >
          <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 24 24">
            <rect x="4" y="4" width="16" height="16" rx="2" />
          </svg>
        </button>
      )}

      {/* 에러 툴팁 */}
      {error && (
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-2 py-1 text-xs bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300 rounded shadow-lg whitespace-nowrap z-10">
          {error}
        </div>
      )}
    </div>
  );
}