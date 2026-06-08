"use client";

import { useState, useEffect, useCallback } from "react";
import {
  QAPair,
  QAPairCreate,
  EvaluationRun,
  EvaluationStats,
  listQAPairs,
  createQAPair,
  deleteQAPair,
  runEvaluation,
  listEvaluationResults,
  getEvaluationStats,
} from "../../lib/api";

// ── 메트릭 바 컴포넌트 ──────────────────────────────────────────────────────

function MetricBar({
  label,
  value,
  color = "blue",
}: {
  label: string;
  value: number;
  color?: string;
}) {
  const pct = Math.round(value * 100);
  const colorMap: Record<string, string> = {
    blue: "bg-blue-500",
    green: "bg-green-500",
    yellow: "bg-yellow-500",
    red: "bg-red-500",
    purple: "bg-purple-500",
    cyan: "bg-cyan-500",
  };
  const bg = colorMap[color] || colorMap.blue;

  return (
    <div className="space-y-1">
      <div className="flex justify-between text-sm">
        <span className="font-medium text-gray-700 dark:text-gray-300">{label}</span>
        <span className="text-gray-500 dark:text-gray-400">{pct}%</span>
      </div>
      <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2.5">
        <div
          className={`${bg} h-2.5 rounded-full transition-all duration-500`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

// ── QA pair 생성 폼 ─────────────────────────────────────────────────────────

function QAPairForm({ onSubmit, onCancel }: { onSubmit: (data: QAPairCreate) => void; onCancel: () => void }) {
  const [question, setQuestion] = useState("");
  const [expectedAnswer, setExpectedAnswer] = useState("");
  const [sources, setSources] = useState("");
  const [mode, setMode] = useState("fact");

  const handleSubmit = () => {
    if (!question.trim() || !expectedAnswer.trim()) return;
    onSubmit({
      question: question.trim(),
      expected_answer: expectedAnswer.trim(),
      expected_sources: sources ? sources.split(",").map((s) => s.trim()) : [],
      mode,
    });
  };

  return (
    <div className="space-y-4 p-4 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">질문 *</label>
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500"
          rows={2}
          placeholder="평가할 질문을 입력하세요"
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">기대 정답 *</label>
        <textarea
          value={expectedAnswer}
          onChange={(e) => setExpectedAnswer(e.target.value)}
          className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500"
          rows={3}
          placeholder="기대하는 정답을 입력하세요"
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">기대 출처 (쉼표 구분)</label>
        <input
          value={sources}
          onChange={(e) => setSources(e.target.value)}
          className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500"
          placeholder="document.pdf, report.txt"
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">채팅 모드</label>
        <select
          value={mode}
          onChange={(e) => setMode(e.target.value)}
          className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-gray-900 dark:text-gray-100"
        >
          <option value="fact">팩트 조회</option>
          <option value="summary">요약</option>
          <option value="column">컬럼 작성</option>
          <option value="reasoning">추론</option>
        </select>
      </div>
      <div className="flex gap-2">
        <button
          onClick={handleSubmit}
          className="px-4 py-2 bg-blue-600 text-white text-sm rounded-md hover:bg-blue-700 disabled:opacity-50"
          disabled={!question.trim() || !expectedAnswer.trim()}
        >
          추가
        </button>
        <button
          onClick={onCancel}
          className="px-4 py-2 bg-gray-200 dark:bg-gray-600 text-gray-700 dark:text-gray-200 text-sm rounded-md hover:bg-gray-300 dark:hover:bg-gray-500"
        >
          취소
        </button>
      </div>
    </div>
  );
}

// ── 평가 결과 상세 ────────────────────────────────────────────────────────

function EvalResultDetail({ result }: { result: EvaluationRun }) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <MetricBar label="Precision@k" value={result.avg_precision} color="blue" />
        <MetricBar label="Recall@k" value={result.avg_recall} color="green" />
        <MetricBar label="MRR" value={result.avg_mrr} color="purple" />
        <MetricBar label="충실도" value={result.avg_faithfulness} color="cyan" />
        <MetricBar label="관련성" value={result.avg_answer_relevance} color="yellow" />
        <MetricBar label="환각 점수" value={1 - result.avg_hallucination_score} color="red" />
      </div>
      <details className="mt-4">
        <summary className="cursor-pointer text-sm font-medium text-gray-700 dark:text-gray-300">
          개별 결과 ({result.results.length}건)
        </summary>
        <div className="mt-2 space-y-3 max-h-96 overflow-y-auto">
          {result.results.map((r) => (
            <div key={r.qa_id} className="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg text-sm space-y-1">
              <p className="font-medium text-gray-900 dark:text-gray-100">Q: {r.question}</p>
              <p className="text-gray-600 dark:text-gray-400 text-xs">기대 정답: {r.expected_answer.slice(0, 100)}...</p>
              <p className="text-blue-600 dark:text-blue-400 text-xs">실제 답변: {r.actual_answer.slice(0, 100)}...</p>
              <div className="flex gap-3 text-xs text-gray-500 dark:text-gray-400">
                <span>P@k: {(r.precision_at_k * 100).toFixed(0)}%</span>
                <span>R@k: {(r.recall_at_k * 100).toFixed(0)}%</span>
                <span>충실도: {(r.faithfulness * 100).toFixed(0)}%</span>
              </div>
            </div>
          ))}
        </div>
      </details>
    </div>
  );
}

// ── 메인评估 페이지 ──────────────────────────────────────────────────────────

export default function EvaluationPage() {
  const [qaPairs, setQAPairs] = useState<QAPair[]>([]);
  const [evalResults, setEvalResults] = useState<EvaluationRun[]>([]);
  const [stats, setStats] = useState<EvaluationStats | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      const [pairs, results, s] = await Promise.all([
        listQAPairs(),
        listEvaluationResults(),
        getEvaluationStats(),
      ]);
      setQAPairs(pairs);
      setEvalResults(results);
      setStats(s);
    } catch (err) {
      setError(err instanceof Error ? err.message : "데이터 로드 실패");
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleCreateQA = async (data: QAPairCreate) => {
    try {
      await createQAPair(data);
      setShowForm(false);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "QA pair 생성 실패");
    }
  };

  const handleDeleteQA = async (id: string) => {
    if (!confirm("이 QA pair를 삭제하시겠습니까?")) return;
    try {
      await deleteQAPair(id);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "삭제 실패");
    }
  };

  const handleRunEval = async () => {
    setRunning(true);
    setError(null);
    try {
      await runEvaluation();
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "평가 실행 실패");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-black">
      <header className="border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-6 py-4">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
          📊 RAG 평가 대시보드
        </h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          검색 품질 정량 평가 — Precision, Recall, MRR, 충실도, 환각 탐지
        </p>
      </header>

      <main className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        {error && (
          <div className="p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-md text-red-700 dark:text-red-300 text-sm">
            {error}
            <button onClick={() => setError(null)} className="ml-2 underline">닫기</button>
          </div>
        )}

        {/* ── 통계 카드 ──────────────────────────── */}
        {stats && (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-7 gap-3">
            {[
              { label: "QA Pairs", value: stats.total_qa_pairs, icon: "📋" },
              { label: "실행 횟수", value: stats.total_evaluations, icon: "🔄" },
              { label: "Precision", value: `${(stats.avg_precision * 100).toFixed(1)}%`, icon: "🎯" },
              { label: "Recall", value: `${(stats.avg_recall * 100).toFixed(1)}%`, icon: "📡" },
              { label: "MRR", value: `${(stats.avg_mrr * 100).toFixed(1)}%`, icon: "📈" },
              { label: "충실도", value: `${(stats.avg_faithfulness * 100).toFixed(1)}%`, icon: "✓" },
              { label: "환각↓", value: `${((1 - stats.avg_hallucination_score) * 100).toFixed(1)}%`, icon: "🛡" },
            ].map((item) => (
              <div key={item.label} className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-3 text-center">
                <div className="text-lg">{item.icon}</div>
                <div className="text-lg font-bold text-gray-900 dark:text-white">{item.value}</div>
                <div className="text-xs text-gray-500 dark:text-gray-400">{item.label}</div>
              </div>
            ))}
          </div>
        )}

        {/* ── 평가 실행 ──────────────────────────── */}
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">평가 실행</h2>
            <button
              onClick={handleRunEval}
              disabled={running || qaPairs.length === 0}
              className="px-4 py-2 bg-blue-600 text-white text-sm rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {running ? "실행 중..." : "전체 평가 실행"}
            </button>
          </div>
          {qaPairs.length === 0 && (
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-2">
              평가를 실행하려면 먼저 QA pairs를 등록하세요.
            </p>
          )}
        </div>

        {/* ── QA Pairs 관리 ──────────────────────── */}
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
              QA Pairs ({qaPairs.length})
            </h2>
            <button
              onClick={() => setShowForm(true)}
              className="px-3 py-1.5 bg-green-600 text-white text-sm rounded-md hover:bg-green-700"
            >
              + 추가
            </button>
          </div>

          {showForm && (
            <QAPairForm
              onSubmit={handleCreateQA}
              onCancel={() => setShowForm(false)}
            />
          )}

          {qaPairs.length === 0 ? (
            <p className="text-sm text-gray-500 dark:text-gray-400">
              등록된 QA pairs가 없습니다. &quot;+ 추가&quot; 버튼으로 시작하세요.
            </p>
          ) : (
            <div className="space-y-2 max-h-80 overflow-y-auto">
              {qaPairs.map((pair) => (
                <div
                  key={pair.id}
                  className="flex items-start justify-between p-3 bg-gray-50 dark:bg-gray-750 rounded-md border border-gray-100 dark:border-gray-700"
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                      {pair.question}
                    </p>
                    <p className="text-xs text-gray-500 dark:text-gray-400 truncate mt-0.5">
                      {pair.expected_answer.slice(0, 80)}...
                    </p>
                    <div className="flex gap-2 mt-1">
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300">
                        {pair.mode}
                      </span>
                      {pair.expected_sources.map((s) => (
                        <span key={s} className="inline-flex items-center px-2 py-0.5 rounded text-xs bg-gray-200 dark:bg-gray-600 text-gray-600 dark:text-gray-300">
                          {s}
                        </span>
                      ))}
                    </div>
                  </div>
                  <button
                    onClick={() => handleDeleteQA(pair.id)}
                    className="ml-2 text-red-500 hover:text-red-700 text-sm"
                  >
                    삭제
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ── 평가 결과 ──────────────────────────── */}
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            평가 결과 ({evalResults.length})
          </h2>
          {evalResults.length === 0 ? (
            <p className="text-sm text-gray-500 dark:text-gray-400">
              아직 실행된 평가가 없습니다.
            </p>
          ) : (
            <div className="space-y-4">
              {evalResults.map((result) => (
                <details key={result.id} className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
                  <summary className="cursor-pointer p-3 bg-gray-50 dark:bg-gray-750 hover:bg-gray-100 dark:hover:bg-gray-700">
                    <div className="flex items-center justify-between">
                      <div>
                        <span className="font-medium text-gray-900 dark:text-gray-100">{result.id}</span>
                        <span className={`ml-2 inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                          result.status === "completed" ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200" :
                          result.status === "running" ? "bg-yellow-100 text-yellow-800 animate-pulse" :
                          result.status === "failed" ? "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200" :
                          "bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300"
                        }`}>
                          {result.status === "completed" ? "완료" : result.status === "running" ? "실행 중" : result.status === "failed" ? "실패" : "대기"}
                        </span>
                        <span className="ml-2 text-xs text-gray-500 dark:text-gray-400">
                          {result.results.length} QA pairs
                        </span>
                      </div>
                      {result.status === "completed" && (
                        <div className="hidden sm:flex gap-3 text-xs text-gray-500 dark:text-gray-400">
                          <span>P@k: {(result.avg_precision * 100).toFixed(0)}%</span>
                          <span>R@k: {(result.avg_recall * 100).toFixed(0)}%</span>
                          <span>충실도: {(result.avg_faithfulness * 100).toFixed(0)}%</span>
                        </div>
                      )}
                    </div>
                  </summary>
                  <div className="p-4">
                    <EvalResultDetail result={result} />
                  </div>
                </details>
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}