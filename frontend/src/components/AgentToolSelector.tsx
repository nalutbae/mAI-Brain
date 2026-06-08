"use client";

import { useState } from "react";

export interface AgentTool {
  name: string;
  description: string;
  display_type?: string;
}

interface AgentToolSelectorProps {
  tools: AgentTool[];
  selectedTools: string[];
  onToggle: (toolName: string) => void;
  onCancel: () => void;
  onSubmit: () => void;
  isLoading: boolean;
}

export default function AgentToolSelector({
  tools,
  selectedTools,
  onToggle,
  onCancel,
  onSubmit,
  isLoading,
}: AgentToolSelectorProps) {
  return (
    <div className="border-t border-blue-200 dark:border-blue-700 bg-blue-50 dark:bg-gray-800 p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-semibold text-blue-700 dark:text-blue-300">
          🤖 에이전트 모드 — 사용할 도구를 선택하세요
        </span>
        <button
          onClick={onCancel}
          className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 text-sm"
        >
          ✕ 취소
        </button>
      </div>
      <div className="flex flex-wrap gap-2 mb-3">
        {tools.map((tool) => (
          <button
            key={tool.name}
            onClick={() => onToggle(tool.name)}
            className={`px-3 py-1.5 rounded-full text-sm border transition-colors ${
              selectedTools.includes(tool.name)
                ? "bg-blue-600 text-white border-blue-600 shadow-sm"
                : "bg-white text-gray-700 border-gray-300 hover:bg-blue-50 dark:bg-gray-700 dark:text-gray-200 dark:border-gray-600 dark:hover:bg-gray-600"
            }`}
            title={tool.description}
          >
            {getToolIcon(tool.name)} {getToolLabel(tool.name)}
          </button>
        ))}
      </div>
      <div className="flex gap-2">
        <button
          onClick={onSubmit}
          disabled={selectedTools.length === 0 || isLoading}
          className="px-4 py-1.5 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
        >
          {isLoading ? "실행 중..." : `선택한 도구 실행 (${selectedTools.length}개)`}
        </button>
      </div>
    </div>
  );
}

function getToolIcon(name: string): string {
  switch (name) {
    case "web_search": return "🔍";
    case "summarize_document": return "📝";
    case "generate_chart": return "📊";
    case "save_file": return "💾";
    default: return "🔧";
  }
}

function getToolLabel(name: string): string {
  switch (name) {
    case "web_search": return "웹 검색";
    case "summarize_document": return "문서 요약";
    case "generate_chart": return "차트 생성";
    case "save_file": return "파일 저장";
    default: return name;
  }
}
