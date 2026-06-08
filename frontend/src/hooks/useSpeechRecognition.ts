"use client";

import { useState, useCallback, useRef, useEffect } from "react";

/**
 * Web Speech API STT 훅
 * 브라우저 내장 SpeechRecognition으로 음성 → 텍스트 변환
 * 한국어(ko-KR) 기본, 연속 인식 지원
 */

export interface UseSpeechRecognitionOptions {
  /** 인식 언어 (기본: ko-KR) */
  lang?: string;
  /** 연속 인식 여부 (기본: false — 한 번만 인식) */
  continuous?: boolean;
  /** 중간 결과 반환 여부 (기본: true) */
  interimResults?: boolean;
  /** 최대 대기 시간 ms (기본: 10000) — 이 시간 후 자동 중지 */
  maxDuration?: number;
}

export interface UseSpeechRecognitionReturn {
  /** 현재 인식된 텍스트 (중간 결과 포함) */
  transcript: string;
  /** 최종 확정된 텍스트 (인식 종료 시) */
  finalTranscript: string;
  /** 음성 인식 활성 상태 */
  isListening: boolean;
  /** 브라우저 지원 여부 */
  isSupported: boolean;
  /** 음성 인식 시작 */
  startListening: () => void;
  /** 음성 인식 중지 */
  stopListening: () => void;
  /** 인식 결과 초기화 */
  resetTranscript: () => void;
  /** 에러 메시지 */
  error: string | null;
}

interface SpeechRecognitionEvent {
  results: SpeechRecognitionResultList;
  resultIndex: number;
}

interface SpeechRecognitionErrorEvent {
  error: string;
  message: string;
}

// Web Speech API 타입 (브라우저 전역)
type SpeechRecognitionInstance = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
  onstart: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
};

function getSpeechRecognition(): (new () => SpeechRecognitionInstance) | null {
  if (typeof window === "undefined") return null;
  return (
    (window as unknown as Record<string, unknown>).SpeechRecognition ??
    (window as unknown as Record<string, unknown>).webkitSpeechRecognition
  ) as (new () => SpeechRecognitionInstance) | null;
}

export function useSpeechRecognition({
  lang = "ko-KR",
  continuous = false,
  interimResults = true,
  maxDuration = 10000,
}: UseSpeechRecognitionOptions = {}): UseSpeechRecognitionReturn {
  const [transcript, setTranscript] = useState("");
  const [finalTranscript, setFinalTranscript] = useState("");
  const [isListening, setIsListening] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const SpeechRecognition = getSpeechRecognition();
  const isSupported = SpeechRecognition !== null;

  const resetTranscript = useCallback(() => {
    setTranscript("");
    setFinalTranscript("");
  }, []);

  const stopListening = useCallback(() => {
    if (recognitionRef.current) {
      recognitionRef.current.stop();
    }
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
    setIsListening(false);
  }, []);

  const startListening = useCallback(() => {
    if (!SpeechRecognition) {
      setError("이 브라우저는 음성 인식을 지원하지 않습니다.");
      return;
    }

    // 기존 인식 중지
    if (recognitionRef.current) {
      recognitionRef.current.abort();
    }

    setError(null);
    resetTranscript();

    const recognition = new SpeechRecognition();
    recognition.lang = lang;
    recognition.continuous = continuous;
    recognition.interimResults = interimResults;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
      setIsListening(true);
    };

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      let interim = "";
      let final = "";

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        if (result.isFinal) {
          final += result[0].transcript;
        } else {
          interim += result[0].transcript;
        }
      }

      if (final) {
        setFinalTranscript((prev) => prev + final);
        setTranscript((prev) => prev + final);
      }
      if (interim) {
        setTranscript((prev) => {
          // 중간 결과는 마지막 확정 이후 텍스트 교체
          const finalPart = finalTranscript || prev.replace(/\s*$/, "");
          return finalPart + interim;
        });
      }
    };

    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      const errorMessages: Record<string, string> = {
        "not-allowed": "마이크 접근 권한이 거부되었습니다.",
        "no-speech": "음성이 감지되지 않았습니다.",
        "audio-capture": "오디오 입력을 사용할 수 없습니다.",
        network: "네트워크 오류가 발생했습니다.",
        aborted: "음성 인식이 중단되었습니다.",
      };
      setError(errorMessages[event.error] || `음성 인식 오류: ${event.error}`);
      setIsListening(false);
    };

    recognition.onend = () => {
      setIsListening(false);
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
    };

    recognitionRef.current = recognition;

    try {
      recognition.start();

      // 최대 대기 시간 초과 시 자동 중지
      if (maxDuration > 0) {
        timeoutRef.current = setTimeout(() => {
          recognition.stop();
        }, maxDuration);
      }
    } catch (err) {
      setError("음성 인식을 시작할 수 없습니다.");
      setIsListening(false);
    }
  }, [SpeechRecognition, lang, continuous, interimResults, maxDuration, resetTranscript, finalTranscript]);

  // 컴포넌트 언마운트 시 정리
  useEffect(() => {
    return () => {
      if (recognitionRef.current) {
        recognitionRef.current.abort();
      }
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  return {
    transcript,
    finalTranscript,
    isListening,
    isSupported,
    startListening,
    stopListening,
    resetTranscript,
    error,
  };
}