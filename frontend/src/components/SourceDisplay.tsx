"use client";

/**
 * 출처 표시 컴포넌트
 * 접기/펼치기 기능
 */

interface SourceDisplayProps {
  sources: string[];
  isOpen: boolean;
  onToggle: () => void;
}

export default function SourceDisplay({ sources, isOpen, onToggle }: SourceDisplayProps) {
  if (!sources || sources.length === 0) {
    return null;
  }

  return (
    <div className="mt-2 w-full">
      <button
        onClick={onToggle}
        className="flex items-center gap-2 text-sm text-gray-600 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-200"
      >
        <span className="transform transition-transform duration-200" style={{ transform: isOpen ? 'rotate(180deg)' : 'rotate(0deg)' }}>
          ▼
        </span>
        <span>출처 {sources.length}건</span>
      </button>
      {isOpen && (
        <div className="mt-2 p-3 bg-gray-100 rounded-lg text-sm text-gray-700 dark:bg-gray-800 dark:text-gray-300 max-h-60 overflow-y-auto">
          {sources.map((source, index) => (
            <div key={index} className="mb-1 last:mb-0">
              <span className="font-medium">[{index + 1}]</span> {source}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}