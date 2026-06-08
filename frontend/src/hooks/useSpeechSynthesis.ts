"use client";

import { useState, useCallback, useRef, useEffect } from "react";

/**
 * Web Speech API TTS 훅
 * 브라우저 내장 SpeechSynthesis로 텍스트 → 음성 재생
 * 한국어 음성 우선, 재생/일시정지/중지 지원
 */

export interface UseSpeechSynthesisOptions {
  /** 재생 언어 (기본: ko-KR) */
  lang?: string;
  /** 재생 속도 (0.1~10, 기본: 1.0) */
  rate?: number;
  /** 음높이 (0~2, 기본: 1.0) */
  pitch?: number;
  /** 볼륨 (0~1, 기본: 1.0) */
  volume?: number;
}

export interface UseSpeechSynthesisReturn {
  /** 현재 재생 중 여부 */
  isSpeaking: boolean;
  /** 현재 일시정지 상태 */
  isPaused: boolean;
  /** 브라우저 지원 여부 */
  isSupported: boolean;
  /** 텍스트 음성 재생 */
  speak: (text: string) => void;
  /** 재생 중지 */
  cancel: () => void;
  /** 일시정지 */
  pause: () => void;
  /** 일시정지 해제 */
  resume: () => void;
  /** 사용 가능한 한국어 음성 목록 */
  voices: SpeechSynthesisVoice[];
  /** 선택된 음성 */
  selectedVoice: SpeechSynthesisVoice | null;
  /** 음성 선택 */
  setVoice: (voice: SpeechSynthesisVoice) => void;
  /** 에러 메시지 */
  error: string | null;
}

export function useSpeechSynthesis({
  lang = "ko-KR",
  rate = 1.0,
  pitch = 1.0,
  volume = 1.0,
}: UseSpeechSynthesisOptions = {}): UseSpeechSynthesisReturn {
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [selectedVoice, setSelectedVoice] = useState<SpeechSynthesisVoice | null>(null);
  const [error, setError] = useState<string | null>(null);

  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);

  const isSupported =
    typeof window !== "undefined" && typeof window.speechSynthesis !== "undefined";

  // 음성 목록 로드 (비동기로 로드되는 경우 대비)
  const loadVoices = useCallback(() => {
    if (!isSupported) return;

    const allVoices = window.speechSynthesis.getVoices();
    // 한국어 음성 우선, 없으면 모든 음성
    const koVoices = allVoices.filter((v) => v.lang.startsWith("ko"));
    const availableVoices = koVoices.length > 0 ? koVoices : allVoices;
    setVoices(availableVoices);

    // 기본 음성 선택: 한국어 음성 중 default 또는 첫 번째
    if (!selectedVoice && availableVoices.length > 0) {
      const defaultVoice =
        koVoices.find((v) => v.default) || koVoices[0] || availableVoices[0];
      setSelectedVoice(defaultVoice);
    }
  }, [isSupported, selectedVoice]);

  useEffect(() => {
    if (!isSupported) return;

    loadVoices();

    // Chrome에서는 voiceschanged 이벤트로 비동기 로드됨
    window.speechSynthesis.addEventListener("voiceschanged", loadVoices);
    return () => {
      window.speechSynthesis.removeEventListener("voiceschanged", loadVoices);
    };
  }, [isSupported, loadVoices]);

  const speak = useCallback(
    (text: string) => {
      if (!isSupported) {
        setError("이 브라우저는 음성 합성을 지원하지 않습니다.");
        return;
      }

      // 기존 재생 중지
      window.speechSynthesis.cancel();

      // 텍스트가 너무 길면 문단 단위로 분할 (Chrome 제한 대응)
      const chunks = splitTextToChunks(text, 200);

      let currentIndex = 0;

      const speakChunk = () => {
        if (currentIndex >= chunks.length) {
          setIsSpeaking(false);
          setIsPaused(false);
          return;
        }

        const utterance = new SpeechSynthesisUtterance(chunks[currentIndex]);
        utterance.lang = lang;
        utterance.rate = rate;
        utterance.pitch = pitch;
        utterance.volume = volume;

        if (selectedVoice) {
          utterance.voice = selectedVoice;
        }

        utterance.onstart = () => {
          setIsSpeaking(true);
          setIsPaused(false);
        };

        utterance.onend = () => {
          currentIndex++;
          speakChunk();
        };

        utterance.onerror = (event) => {
          if (event.error !== "canceled") {
            setError(`음성 합성 오류: ${event.error}`);
          }
          setIsSpeaking(false);
          setIsPaused(false);
        };

        utterance.onpause = () => setIsPaused(true);
        utterance.onresume = () => setIsPaused(false);

        utteranceRef.current = utterance;
        window.speechSynthesis.speak(utterance);
      };

      setError(null);
      speakChunk();
    },
    [isSupported, lang, rate, pitch, volume, selectedVoice]
  );

  const cancel = useCallback(() => {
    if (isSupported) {
      window.speechSynthesis.cancel();
      setIsSpeaking(false);
      setIsPaused(false);
    }
  }, [isSupported]);

  const pause = useCallback(() => {
    if (isSupported && isSpeaking) {
      window.speechSynthesis.pause();
    }
  }, [isSupported, isSpeaking]);

  const resume = useCallback(() => {
    if (isSupported && isPaused) {
      window.speechSynthesis.resume();
    }
  }, [isSupported, isPaused]);

  const handleSetVoice = useCallback((voice: SpeechSynthesisVoice) => {
    setSelectedVoice(voice);
  }, []);

  // 컴포넌트 언마운트 시 정리
  useEffect(() => {
    return () => {
      if (isSupported) {
        window.speechSynthesis.cancel();
      }
    };
  }, [isSupported]);

  return {
    isSpeaking,
    isPaused,
    isSupported,
    speak,
    cancel,
    pause,
    resume,
    voices,
    selectedVoice,
    setVoice: handleSetVoice,
    error,
  };
}

/**
 * 텍스트를 청크로 분할 (문장 경계 존중)
 * Chrome은 약 15초 분량(약 200자)까지만 원활 재생
 */
function splitTextToChunks(text: string, maxChars: number): string[] {
  if (text.length <= maxChars) return [text];

  const chunks: string[] = [];
  let remaining = text;

  while (remaining.length > 0) {
    if (remaining.length <= maxChars) {
      chunks.push(remaining);
      break;
    }

    // 문장 경계에서 분할 우선 (마침표, 물음표, 느낌표, 개행)
    let splitIndex = remaining.lastIndexOf("\n", maxChars);
    if (splitIndex <= 0 || splitIndex > maxChars) {
      splitIndex = remaining.lastIndexOf(". ", maxChars);
    }
    if (splitIndex <= 0 || splitIndex > maxChars) {
      splitIndex = remaining.lastIndexOf("? ", maxChars);
    }
    if (splitIndex <= 0 || splitIndex > maxChars) {
      splitIndex = remaining.lastIndexOf("! ", maxChars);
    }
    if (splitIndex <= 0 || splitIndex > maxChars) {
      splitIndex = remaining.lastIndexOf(" ", maxChars);
    }
    if (splitIndex <= 0 || splitIndex > maxChars) {
      splitIndex = maxChars;
    }

    chunks.push(remaining.slice(0, splitIndex + 1).trim());
    remaining = remaining.slice(splitIndex + 1).trim();
  }

  return chunks.filter(Boolean);
}