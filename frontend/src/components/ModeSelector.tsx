"use client";

/**
 * 모드 선택 토글 컴포넌트
 * [팩트 조회] [요약] [컬럼 작성] [추론 ▼] 모드 전환
 * 컬럼 작성·추론 선택 시 하위 신뢰도 선택기 표시
 */

import type { ChatMode, ReasoningStrength } from "@/lib/api";

interface ModeSelectorProps {
  mode: ChatMode;
  onChange: (mode: ChatMode) => void;
  reasoningStrength: ReasoningStrength;
  onStrengthChange: (strength: ReasoningStrength) => void;
}

const modes: { key: ChatMode; label: string }[] = [
  { key: "fact", label: "팩트 조회" },
  { key: "summary", label: "요약" },
  { key: "column", label: "컬럼 작성" },
  { key: "reasoning", label: "추론" },
  { key: "creative", label: "창의적 대화" },
];

const strengths: { key: ReasoningStrength; label: string }[] = [
  { key: "all", label: "전체" },
  { key: "strong", label: "강한 근거만" },
  { key: "mid", label: "중간 근거만" },
  { key: "weak", label: "약한 근거만" },
];

export default function ModeSelector({
  mode,
  onChange,
  reasoningStrength,
  onStrengthChange,
}: ModeSelectorProps) {
  return (
    <div className="flex flex-wrap gap-2 p-2 items-center">
      {modes.map(({ key, label }) => (
        <button
          key={key}
          onClick={() => onChange(key)}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            mode === key
              ? "bg-blue-600 text-white"
              : "bg-gray-200 text-gray-700 hover:bg-gray-300"
          }`}
        >
          {label}
        </button>
      ))}

      {/* 컬럼 작성·추론 모드 선택 시 하위 신뢰도 선택기 */}
      {(mode === "reasoning" || mode === "column") && (
        <div className="flex gap-1 ml-2 border-l-2 border-blue-300 pl-3">
          {strengths.map(({ key, label }) => (
            <button
              key={key}
              onClick={() => onStrengthChange(key)}
              className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                reasoningStrength === key
                  ? "bg-blue-100 text-blue-700 border border-blue-300"
                  : "bg-gray-100 text-gray-500 hover:bg-gray-200 border border-gray-200"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}