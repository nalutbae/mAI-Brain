"use client";

import { useCallback, useEffect } from "react";
import { useSpeechRecognition } from "../hooks/useSpeechRecognition";

/**
 * 음성 입력 버튼 컴포넌트
 * 마이크 아이콘 버튼 — 클릭하면 STT 시작, 인식 결과를 텍스트로 채팅 입력에 전달
 * 녹음 중에는 빨간 펄스 애니메이션으로 상태 표시
 */

interface VoiceInputProps {
  /** 인식된 텍스트 콜백 (최종 확정 텍스트) */
  onTranscript: (text: string) => void;
  /** 중간 인식 텍스트 콜백 (실시간 표시용) */
  onInterimTranscript?: (text: string) => void;
  /** 추가 CSS 클래스 */
  className?: string;
  /** 비활성화 여부 */
  disabled?: boolean;
}

export default function VoiceInput({
  onTranscript,
  onInterimTranscript,
  className = "",
  disabled = false,
}: VoiceInputProps) {
  const {
    transcript,
    finalTranscript,
    isListening,
    isSupported,
    startListening,
    stopListening,
    resetTranscript,
    error,
  } = useSpeechRecognition({
    lang: "ko-KR",
    continuous: false,
    interimResults: true,
    maxDuration: 30000,
  });

  // 중간 결과를 부모에게 전달 (실시간 표시)
  useEffect(() => {
    if (isListening && transcript && onInterimTranscript) {
      onInterimTranscript(transcript);
    }
  }, [transcript, isListening, onInterimTranscript]);

  // 최종 결과를 부모에게 전달
  useEffect(() => {
    if (finalTranscript && !isListening) {
      onTranscript(finalTranscript);
      resetTranscript();
      if (onInterimTranscript) {
        onInterimTranscript("");
      }
    }
  }, [finalTranscript, isListening, onTranscript, onInterimTranscript, resetTranscript]);

  const handleClick = useCallback(() => {
    if (disabled) return;

    if (isListening) {
      stopListening();
    } else {
      resetTranscript();
      startListening();
    }
  }, [disabled, isListening, startListening, stopListening, resetTranscript]);

  if (!isSupported) {
    return null;
  }

  return (
    <div className="relative">
      <button
        onClick={handleClick}
        disabled={disabled || !!error}
        className={`relative flex items-center justify-center w-10 h-10 rounded-full transition-all duration-200 ${
          isListening
            ? "bg-red-500 text-white shadow-lg shadow-red-500/30"
            : "bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600"
        } ${disabled || error ? "opacity-50 cursor-not-allowed" : "cursor-pointer"} ${className}`}
        title={isListening ? "녹음 중지" : "음성 입력"}
        aria-label={isListening ? "녹음 중지" : "음성 입력"}
      >
        {/* 마이크 아이콘 */}
        {isListening ? (
          <svg
            className="w-5 h-5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"
            />
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M19 10v2a7 7 0 0 1-14 0v-2"
            />
            <line x1="12" y1="19" x2="12" y2="23" strokeLinecap="round" />
            <line x1="8" y1="23" x2="16" y2="23" strokeLinecap="round" />
          </svg>
        ) : (
          <svg
            className="w-5 h-5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"
            />
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M19 10v2a7 7 0 0 1-14 0v-2"
            />
            <line x1="12" y1="19" x2="12" y2="23" strokeLinecap="round" />
            <line x1="8" y1="23" x2="16" y2="23" strokeLinecap="round" />
          </svg>
        )}

        {/* 녹음 중 펄스 애니메이션 */}
        {isListening && (
          <>
            <span className="absolute inset-0 rounded-full bg-red-500 animate-ping opacity-30" />
            <span className="absolute -top-1 -right-1 w-3 h-3 bg-red-600 rounded-full animate-pulse" />
          </>
        )}
      </button>

      {/* 에러 툴팁 */}
      {error && (
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-2 py-1 text-xs bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300 rounded shadow-lg whitespace-nowrap z-10">
          {error}
        </div>
      )}
    </div>
  );
}