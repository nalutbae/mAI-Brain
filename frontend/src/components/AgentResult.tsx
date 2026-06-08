"use client";

import type { AgentToolResult } from "../lib/api";

interface AgentResultProps {
  results: AgentToolResult[];
}

export default function AgentResult({ results }: AgentResultProps) {
  if (!results || results.length === 0) return null;

  return (
    <div className="space-y-3 mt-2">
      {results.map((result, index) => (
        <div
          key={index}
          className={`border rounded-lg p-3 ${
            result.success
              ? "border-green-200 dark:border-green-700 bg-green-50 dark:bg-gray-800"
              : "border-red-200 dark:border-red-700 bg-red-50 dark:bg-gray-800"
          }`}
        >
          <div className="flex items-center gap-2 mb-2">
            <span className="text-sm font-semibold">
              {getToolIcon(result.tool_name)} {getToolLabel(result.tool_name)}
            </span>
            <span
              className={`text-xs px-2 py-0.5 rounded-full ${
                result.success
                  ? "bg-green-200 text-green-800 dark:bg-green-700 dark:text-green-100"
                  : "bg-red-200 text-red-800 dark:bg-red-700 dark:text-red-100"
              }`}
            >
              {result.success ? "성공" : "실패"}
            </span>
          </div>

          {!result.success && result.error && (
            <p className="text-sm text-red-600 dark:text-red-400">
              {result.error}
            </p>
          )}

          {result.success && result.display_type === "chart" && (
            <ChartDisplay data={result.data} />
          )}

          {result.success && result.display_type === "text" && (
            <TextDisplay data={result.data} toolName={result.tool_name} />
          )}

          {result.success && result.display_type === "file" && (
            <FileDisplay data={result.data} />
          )}
        </div>
      ))}
    </div>
  );
}

function ChartDisplay({ data }: { data: Record<string, unknown> }) {
  const labels = (data.labels as string[]) || [];
  const datasets = (data.datasets as Array<{ label: string; data: number[] }>) || [];
  const chartType = (data.type as string) || "bar";
  const title = (data.title as string) || "차트";

  if (!labels.length || !datasets.length) {
    return <p className="text-sm text-gray-500">차트 데이터가 없습니다.</p>;
  }

  const maxVal = Math.max(...datasets.flatMap((d) => d.data), 1);

  return (
    <div className="mt-2">
      <p className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-2">
        📊 {title}
      </p>
      {/* Simple bar chart visualization */}
      <div className="space-y-1">
        {labels.map((label, i) => {
          const values = datasets.map((d) => d.data[i] || 0);
          return (
            <div key={i} className="flex items-center gap-2 text-xs">
              <span className="w-24 text-right text-gray-600 dark:text-gray-400 truncate">
                {String(label).slice(0, 15)}
              </span>
              <div className="flex-1 flex gap-1">
                {values.map((val, j) => (
                  <div
                    key={j}
                    className="h-5 rounded-sm flex items-center justify-end pr-1 text-white text-[10px] font-medium min-w-[20px]"
                    style={{
                      width: `${Math.max((val / maxVal) * 100, 2)}%`,
                      backgroundColor: CHART_COLORS[j % CHART_COLORS.length],
                    }}
                  >
                    {val > 0 ? val : ""}
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
      {/* Legend */}
      <div className="flex gap-3 mt-2 text-xs">
        {datasets.map((ds, j) => (
          <div key={j} className="flex items-center gap-1">
            <div
              className="w-3 h-3 rounded-sm"
              style={{ backgroundColor: CHART_COLORS[j % CHART_COLORS.length] }}
            />
            <span className="text-gray-600 dark:text-gray-400">{ds.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function TextDisplay({
  data,
  toolName,
}: {
  data: Record<string, unknown>;
  toolName: string;
}) {
  if (toolName === "web_search") {
    const results = (data.results as Array<{ title: string; snippet: string; url: string }>) || [];
    if (!results.length) {
      return <p className="text-sm text-gray-500">{String(data.message || "검색 결과가 없습니다.")}</p>;
    }
    return (
      <div className="mt-2 space-y-2">
        {results.map((r, i) => (
          <div key={i} className="text-sm">
            <a
              href={r.url}
              target="_blank"
              rel="noopener noreferrer"
              className="font-medium text-blue-600 dark:text-blue-400 hover:underline"
            >
              {r.title}
            </a>
            <p className="text-gray-700 dark:text-gray-300 mt-0.5 text-xs">
              {r.snippet}
            </p>
          </div>
        ))}
      </div>
    );
  }

  if (toolName === "summarize_document") {
    return (
      <div className="mt-2 text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap">
        {String(data.summary || "")}
      </div>
    );
  }

  // Default text display
  return (
    <div className="mt-2 text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap">
      {JSON.stringify(data, null, 2)}
    </div>
  );
}

function FileDisplay({ data }: { data: Record<string, unknown> }) {
  return (
    <div className="mt-2 text-sm">
      <p className="text-green-700 dark:text-green-300">
        ✅ {String(data.message || "파일 저장 완료")}
      </p>
      {Boolean(data.file_path) && (
        <p className="text-xs text-gray-500 mt-1 font-mono">
          {String(data.file_path)}
        </p>
      )}
    </div>
  );
}

const CHART_COLORS = [
  "#3B82F6", "#EF4444", "#10B981", "#F59E0B",
  "#8B5CF6", "#EC4899", "#06B6D4", "#F97316",
];

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
