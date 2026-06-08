"use client";

import { useState } from "react";
import type {
  ConflictType,
  DocumentConflict,
  DocumentAgreement,
  CrossReasoningReport,
} from "../lib/cross-reasoning";
import { analyzeCrossReasoning } from "../lib/cross-reasoning";

// ── 모순 유형 라벨 매핑 ──────────────────────────────────────────────────

const CONFLICT_TYPE_LABELS: Record<ConflictType, string> = {
  direct_contradiction: "직접적 모순",
  temporal_conflict: "시간적 충돌",
  partial_disagreement: "부분적 불일치",
  evidence_gap: "근거 차이",
};

const SEVERITY_COLORS: Record<string, string> = {
  low: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200",
  medium:
    "bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200",
  high: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
};

const STRENGTH_COLORS: Record<string, string> = {
  weak: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300",
  moderate:
    "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
  strong: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
};

// ── 메인 컴포넌트 ─────────────────────────────────────────────────────

export default function CrossReasoningPage() {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<string>("reasoning");
  const [reasoningStrength, setReasoningStrength] = useState<string>("all");
  const [isLoading, setIsLoading] = useState(false);
  const [report, setReport] = useState<CrossReasoningReport | null>(null);
  const [answer, setAnswer] = useState<string>("");
  const [error, setError] = useState<string>("");

  const handleAnalyze = async () => {
    if (!query.trim() || isLoading) return;

    setIsLoading(true);
    setError("");
    setReport(null);
    setAnswer("");

    try {
      const response = await analyzeCrossReasoning({
        query: query.trim(),
        mode,
        reasoning_strength: reasoningStrength === "all" ? undefined : reasoningStrength,
      });

      setReport(response.report);
      setAnswer(response.answer);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "분석 중 오류가 발생했습니다.";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  };

  const confidencePercent = report
    ? Math.round(report.confidence * 100)
    : 0;

  return (
    <div className="max-w-5xl mx-auto p-4 sm:p-6 lg:p-8 space-y-6">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            교차 문서 추론
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            여러 문서 간 모순과 일치를 자동으로 탐지하고 분석합니다
          </p>
        </div>
      </div>

      {/* 입력 영역 */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            분석할 질문
          </label>
          <textarea
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="여러 문서를 교차 검증할 질문을 입력하세요... 예: '북한 경제개혁 정책의 변화와 남한의 대응'"
            className="w-full resize-none rounded-lg border border-gray-300 dark:border-gray-600 px-4 py-3 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-white"
            rows={3}
            disabled={isLoading}
          />
        </div>

        {/* 모드 & 강도 선택 */}
        <div className="flex flex-wrap gap-4">
          <div className="flex-1 min-w-[200px]">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              검색 모드
            </label>
            <select
              value={mode}
              onChange={(e) => setMode(e.target.value)}
              className="w-full rounded-lg border border-gray-300 dark:border-gray-600 px-3 py-2 dark:bg-gray-700 dark:text-white"
              disabled={isLoading}
            >
              <option value="fact">팩트 조회 (top-5)</option>
              <option value="summary">요약 (top-8)</option>
              <option value="column">컬럼 작성 (top-18)</option>
              <option value="reasoning">추론 (top-15) ★</option>
            </select>
          </div>

          <div className="flex-1 min-w-[200px]">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              추론 강도
            </label>
            <select
              value={reasoningStrength}
              onChange={(e) => setReasoningStrength(e.target.value)}
              className="w-full rounded-lg border border-gray-300 dark:border-gray-600 px-3 py-2 dark:bg-gray-700 dark:text-white"
              disabled={isLoading}
            >
              <option value="all">전체 (모든 강도)</option>
              <option value="strong">강한 추론만</option>
              <option value="mid">중간 추론만</option>
              <option value="weak">약한 추론만</option>
            </select>
          </div>
        </div>

        <button
          onClick={handleAnalyze}
          disabled={!query.trim() || isLoading}
          className="w-full px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 dark:disabled:bg-gray-600 disabled:cursor-not-allowed transition-colors font-medium"
        >
          {isLoading ? "분석 중..." : "교차 추론 분석"}
        </button>
      </div>

      {/* 에러 메시지 */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4 text-red-700 dark:text-red-300">
          {error}
        </div>
      )}

      {/* 분석 결과 */}
      {report && (
        <div className="space-y-6">
          {/* 신뢰도 및 상태 */}
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                분석 결과
              </h2>
              <div className="flex items-center gap-3">
                <span
                  className={`px-3 py-1 rounded-full text-xs font-medium ${
                    report.status === "completed"
                      ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
                      : report.status === "failed"
                        ? "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200"
                        : "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200"
                  }`}
                >
                  {report.status === "completed"
                    ? "완료"
                    : report.status === "failed"
                      ? "실패"
                      : "분석 중"}
                </span>
                <span className="text-sm text-gray-500 dark:text-gray-400">
                  신뢰도: {confidencePercent}%
                </span>
              </div>
            </div>

            {/* 신뢰도 바 */}
            <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
              <div
                className={`h-2 rounded-full transition-all ${
                  confidencePercent >= 70
                    ? "bg-green-500"
                    : confidencePercent >= 40
                      ? "bg-yellow-500"
                      : "bg-red-500"
                }`}
                style={{ width: `${confidencePercent}%` }}
              />
            </div>
          </div>

          {/* 하위 질문 분해 */}
          {report.sub_queries.length > 0 && (
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
                질문 분해
              </h3>
              <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
                원본: &ldquo;{report.original_query}&rdquo;
              </p>
              <div className="space-y-2">
                {report.sub_queries.map((sq, i) => (
                  <div
                    key={sq.id}
                    className="flex items-start gap-3 p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg"
                  >
                    <span className="flex-shrink-0 w-6 h-6 bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300 rounded-full flex items-center justify-center text-xs font-bold">
                      {i + 1}
                    </span>
                    <div>
                      <p className="text-gray-900 dark:text-white text-sm">
                        {sq.query}
                      </p>
                      <span className="text-xs text-gray-400 dark:text-gray-500">
                        {sq.aspect}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 모순 탐지 결과 */}
          {report.conflicts.length > 0 && (
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
                모순 탐지 ({report.conflicts.length}건)
              </h3>
              <div className="space-y-4">
                {report.conflicts.map((conflict, i) => (
                  <ConflictCard key={i} conflict={conflict} />
                ))}
              </div>
            </div>
          )}

          {/* 일치 분석 결과 */}
          {report.agreements.length > 0 && (
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
                일치 분석 ({report.agreements.length}건)
              </h3>
              <div className="space-y-4">
                {report.agreements.map((agreement, i) => (
                  <AgreementCard key={i} agreement={agreement} />
                ))}
              </div>
            </div>
          )}

          {/* 검색 결과 요약 */}
          {report.sub_query_results.length > 0 && (
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
                하위 질문 검색 결과
              </h3>
              <div className="space-y-4">
                {report.sub_query_results.map((result, i) => (
                  <div
                    key={i}
                    className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg"
                  >
                    <p className="font-medium text-gray-900 dark:text-white mb-2">
                      {result.sub_query.query}{" "}
                      <span className="text-xs text-gray-400">
                        ({result.sub_query.aspect})
                      </span>
                    </p>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                      {result.hits.length}개 검색 결과
                    </p>
                    {result.hits.slice(0, 3).map((hit, j) => (
                      <div
                        key={j}
                        className="mt-2 text-sm text-gray-600 dark:text-gray-300 border-l-2 border-blue-300 dark:border-blue-600 pl-3"
                      >
                        <span className="font-medium">{hit.source}</span>
                        {hit.page && (
                          <span className="text-gray-400 dark:text-gray-500">
                            {" "}
                            p.{hit.page}
                          </span>
                        )}
                        <p className="text-gray-500 dark:text-gray-400 line-clamp-2">
                          {hit.text.slice(0, 150)}...
                        </p>
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 종합 분석 */}
          {answer && (
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
                종합 분석
              </h3>
              <div className="prose dark:prose-invert max-w-none whitespace-pre-wrap text-gray-800 dark:text-gray-200">
                {answer}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── 모순 카드 ────────────────────────────────────────────────────────

function ConflictCard({ conflict }: { conflict: DocumentConflict }) {
  return (
    <div className="border border-orange-200 dark:border-orange-800 rounded-lg p-4 space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="font-semibold text-orange-800 dark:text-orange-200">
          {CONFLICT_TYPE_LABELS[conflict.conflict_type] ||
            conflict.conflict_type}
        </span>
        <span
          className={`px-2 py-0.5 rounded text-xs font-medium ${SEVERITY_COLORS[conflict.severity] || SEVERITY_COLORS.medium}`}
        >
          {conflict.severity === "high"
            ? "심각"
            : conflict.severity === "medium"
              ? "보통"
              : "경미"}
        </span>
      </div>
      <p className="text-gray-700 dark:text-gray-300 text-sm">
        {conflict.description}
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="bg-red-50 dark:bg-red-900/20 rounded p-3">
          <p className="text-xs font-medium text-red-600 dark:text-red-400 mb-1">
            {conflict.document_a}
          </p>
          <p className="text-sm text-gray-700 dark:text-gray-300">
            {conflict.claim_a}
          </p>
        </div>
        <div className="bg-blue-50 dark:bg-blue-900/20 rounded p-3">
          <p className="text-xs font-medium text-blue-600 dark:text-blue-400 mb-1">
            {conflict.document_b}
          </p>
          <p className="text-sm text-gray-700 dark:text-gray-300">
            {conflict.claim_b}
          </p>
        </div>
      </div>
      {conflict.resolution_hint && (
        <p className="text-xs text-gray-500 dark:text-gray-400 italic">
          해소 힌트: {conflict.resolution_hint}
        </p>
      )}
    </div>
  );
}

// ── 일치 카드 ────────────────────────────────────────────────────────

function AgreementCard({ agreement }: { agreement: DocumentAgreement }) {
  return (
    <div className="border border-green-200 dark:border-green-800 rounded-lg p-4 space-y-2">
      <div className="flex items-center gap-2 flex-wrap">
        <span
          className={`px-2 py-0.5 rounded text-xs font-medium ${STRENGTH_COLORS[agreement.strength] || STRENGTH_COLORS.moderate}`}
        >
          {agreement.strength === "strong"
            ? "강한 일치"
            : agreement.strength === "moderate"
              ? "보통 일치"
              : "약한 일치"}
        </span>
        {agreement.theme && (
          <span className="text-xs text-gray-400 dark:text-gray-500">
            {agreement.theme}
          </span>
        )}
      </div>
      <p className="text-gray-700 dark:text-gray-300 text-sm">
        {agreement.description}
      </p>
      <div className="flex flex-wrap gap-1">
        {agreement.documents.map((doc, i) => (
          <span
            key={i}
            className="px-2 py-0.5 bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-300 rounded text-xs"
          >
            {doc}
          </span>
        ))}
      </div>
    </div>
  );
}