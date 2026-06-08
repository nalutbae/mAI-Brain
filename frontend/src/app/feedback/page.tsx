"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Feedback,
  FeedbackStats,
  FeedbackSuggestion,
  FeedbackType,
  listFeedback,
  getFeedbackStats,
  getFeedbackSuggestions,
} from "../../lib/api";

// ── 통계 카드 ──────────────────────────────────────────────────────────────

function StatCard({
  icon,
  label,
  value,
  subtext,
  color = "blue",
}: {
  icon: string;
  label: string;
  value: string | number;
  subtext?: string;
  color?: string;
}) {
  const colorMap: Record<string, string> = {
    blue: "bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800",
    green: "bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800",
    red: "bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800",
    yellow: "bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800",
    purple: "bg-purple-50 dark:bg-purple-900/20 border-purple-200 dark:border-purple-800",
  };
  const bg = colorMap[color] || colorMap.blue;

  return (
    <div className={`rounded-lg border p-3 text-center ${bg}`}>
      <div className="text-2xl">{icon}</div>
      <div className="text-xl font-bold text-gray-900 dark:text-white">{value}</div>
      <div className="text-xs text-gray-600 dark:text-gray-400">{label}</div>
      {subtext && <div className="text-xs text-gray-500 dark:text-gray-500">{subtext}</div>}
    </div>
  );
}

// ── 만족률 바 ─────────────────────────────────────────────────────────────

function SatisfactionBar({ rate }: { rate: number }) {
  const pct = Math.round(rate * 100);
  const color = pct >= 70 ? "bg-green-500" : pct >= 50 ? "bg-yellow-500" : "bg-red-500";

  return (
    <div className="space-y-1">
      <div className="flex justify-between text-sm">
        <span className="font-medium text-gray-700 dark:text-gray-300">만족률</span>
        <span className="text-gray-500 dark:text-gray-400">{pct}%</span>
      </div>
      <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-3">
        <div
          className={`${color} h-3 rounded-full transition-all duration-500`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

// ── 태그 분포 ──────────────────────────────────────────────────────────────

const TAG_LABELS: Record<string, string> = {
  irrelevant: "관련 없음",
  incomplete: "불완전",
  outdated: "구식 정보",
  hallucination: "환각",
  wrong_source: "잘못된 출처",
  biased: "편향",
  unclear: "불분명",
};

function TagDistribution({ distribution }: { distribution: Record<string, number> }) {
  const entries = Object.entries(distribution).sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) {
    return <p className="text-sm text-gray-500 dark:text-gray-400">아직 태그 데이터가 없습니다.</p>;
  }
  const max = Math.max(...entries.map((e) => e[1]));

  return (
    <div className="space-y-2">
      {entries.map(([tag, count]) => (
        <div key={tag} className="flex items-center gap-2">
          <span className="text-xs w-20 text-right text-gray-600 dark:text-gray-400">
            {TAG_LABELS[tag] || tag}
          </span>
          <div className="flex-1 bg-gray-200 dark:bg-gray-700 rounded-full h-2">
            <div
              className="bg-red-500 h-2 rounded-full"
              style={{ width: `${(count / max) * 100}%` }}
            />
          </div>
          <span className="text-xs text-gray-500 dark:text-gray-400 w-8">{count}건</span>
        </div>
      ))}
    </div>
  );
}

// ── 개선 제안 카드 ─────────────────────────────────────────────────────────

const TARGET_LABELS: Record<string, string> = {
  top_k: "🔍 검색 결과 수 (top-k)",
  chunk_size: "📄 청킹 크기",
  embedding_model: "🧠 임베딩 모델",
  prompt: "💬 시스템 프롬프트",
  reindex: "📚 문서 재인덱싱",
};

const TARGET_COLORS: Record<string, string> = {
  top_k: "border-blue-300 bg-blue-50 dark:bg-blue-900/20 dark:border-blue-800",
  chunk_size: "border-purple-300 bg-purple-50 dark:bg-purple-900/20 dark:border-purple-800",
  embedding_model: "border-red-300 bg-red-50 dark:bg-red-900/20 dark:border-red-800",
  prompt: "border-yellow-300 bg-yellow-50 dark:bg-yellow-900/20 dark:border-yellow-800",
  reindex: "border-green-300 bg-green-50 dark:bg-green-900/20 dark:border-green-800",
};

const PRIORITY_BADGE: Record<string, string> = {
  high: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
  medium: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200",
  low: "bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300",
};

function SuggestionCard({ suggestion }: { suggestion: FeedbackSuggestion }) {
  return (
    <div className={`rounded-lg border-2 p-4 ${TARGET_COLORS[suggestion.target] || "border-gray-300 bg-white dark:bg-gray-800"}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${PRIORITY_BADGE[suggestion.priority] || PRIORITY_BADGE.medium}`}>
              {suggestion.priority === "high" ? "🔥 높음" : suggestion.priority === "medium" ? "⚡ 보통" : "📝 낮음"}
            </span>
            <span className="text-xs text-gray-500 dark:text-gray-400">
              {TARGET_LABELS[suggestion.target] || suggestion.target}
            </span>
          </div>
          <h3 className="font-semibold text-gray-900 dark:text-white text-sm">{suggestion.title}</h3>
          <p className="text-xs text-gray-600 dark:text-gray-400 mt-1 whitespace-pre-wrap">{suggestion.description}</p>
        </div>
        {suggestion.affected_feedback_ids.length > 0 && (
          <span className="text-xs text-gray-400 dark:text-gray-500 shrink-0">
            {suggestion.affected_feedback_ids.length}건 피드백
          </span>
        )}
      </div>
    </div>
  );
}

// ── 피드백 목록 아이템 ────────────────────────────────────────────────────

const TYPE_EMOJI: Record<string, string> = {
  thumbs_up: "👍",
  thumbs_down: "👎",
  correction: "✏️",
};

function FeedbackItem({ feedback }: { feedback: Feedback }) {
  return (
    <div className="p-3 bg-gray-50 dark:bg-gray-800 rounded-md border border-gray-100 dark:border-gray-700">
      <div className="flex items-center gap-2 mb-1">
        <span className="text-lg">{TYPE_EMOJI[feedback.feedback_type] || "💬"}</span>
        <span className="text-xs text-gray-500 dark:text-gray-400">
          {new Date(feedback.created_at).toLocaleString("ko-KR")}
        </span>
        <span className="text-xs text-gray-400 dark:text-gray-500">
          {feedback.session_id ? `세션: ${feedback.session_id.slice(0, 12)}...` : "세션 없음"}
        </span>
      </div>
      {feedback.query && (
        <p className="text-xs text-gray-600 dark:text-gray-400 truncate">Q: {feedback.query}</p>
      )}
      {feedback.tags.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-1">
          {feedback.tags.map((tag) => (
            <span key={tag} className="inline-flex px-1.5 py-0.5 rounded text-xs bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-300">
              {TAG_LABELS[tag] || tag}
            </span>
          ))}
        </div>
      )}
      {feedback.comment && (
        <p className="text-xs text-gray-600 dark:text-gray-400 mt-1">{feedback.comment}</p>
      )}
      {feedback.correction_text && (
        <div className="mt-1 p-2 bg-blue-50 dark:bg-blue-900/20 rounded text-xs">
          <span className="font-medium text-blue-700 dark:text-blue-300">
            {feedback.correction_type === "retrieval" ? "🔍 검색 정정" : "✏️ 응답 정정"}:
          </span>{" "}
          <span className="text-gray-700 dark:text-gray-300">{feedback.correction_text.slice(0, 150)}{feedback.correction_text.length > 150 ? "..." : ""}</span>
        </div>
      )}
    </div>
  );
}

// ── 메인 피드백 대시보드 ──────────────────────────────────────────────────

export default function FeedbackPage() {
  const [feedbacks, setFeedbacks] = useState<Feedback[]>([]);
  const [stats, setStats] = useState<FeedbackStats | null>(null);
  const [suggestions, setSuggestions] = useState<FeedbackSuggestion[]>([]);
  const [filterType, setFilterType] = useState<FeedbackType | "">("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"overview" | "suggestions" | "list">("overview");

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const [fbs, st, sgs] = await Promise.all([
        listFeedback(filterType ? { feedback_type: filterType } : undefined),
        getFeedbackStats(),
        getFeedbackSuggestions(),
      ]);
      setFeedbacks(fbs);
      setStats(st);
      setSuggestions(sgs);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "데이터 로드 실패");
    } finally {
      setLoading(false);
    }
  }, [filterType]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const tabs = [
    { key: "overview" as const, label: "📊 개요" },
    { key: "suggestions" as const, label: "💡 개선 제안" },
    { key: "list" as const, label: "📋 피드백 목록" },
  ];

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-black">
      <header className="border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-6 py-4">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
          🔄 Human-in-the-Loop 피드백
        </h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          사용자 피드백 수집 → 통계 분석 → 자동 개선 제안
        </p>
      </header>

      <main className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        {error && (
          <div className="p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-md text-red-700 dark:text-red-300 text-sm">
            {error}
            <button onClick={() => setError(null)} className="ml-2 underline">닫기</button>
          </div>
        )}

        {/* 탭 네비게이션 */}
        <div className="flex gap-1 border-b border-gray-200 dark:border-gray-700">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab.key
                  ? "border-blue-600 text-blue-600 dark:border-blue-400 dark:text-blue-400"
                  : "border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {loading && !stats ? (
          <div className="flex items-center justify-center py-12 text-gray-400">
            <p>데이터를 불러오는 중...</p>
          </div>
        ) : (
          <>
            {/* ── 개요 탭 ─── */}
            {activeTab === "overview" && stats && (
              <div className="space-y-6">
                {/* 통계 카드 */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <StatCard icon="💬" label="전체 피드백" value={stats.total_feedbacks} color="blue" />
                  <StatCard icon="👍" label="긍정 평가" value={stats.thumbs_up} color="green" />
                  <StatCard icon="👎" label="부정 평가" value={stats.thumbs_down} color="red" />
                  <StatCard icon="✏️" label="정정 제안" value={stats.corrections} color="yellow" />
                </div>

                {/* 만족률 + 최근 트렌드 */}
                <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
                  <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">만족률</h2>
                  <SatisfactionBar rate={stats.satisfaction_rate} />
                  {stats.recent_trend && (
                    <div className="mt-3 flex gap-4 text-sm text-gray-600 dark:text-gray-400">
                      <span>최근 7일 👍 {stats.recent_trend.thumbs_up}</span>
                      <span>최근 7일 👎 {stats.recent_trend.thumbs_down}</span>
                    </div>
                  )}
                </div>

                {/* 태그 분포 */}
                <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
                  <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">부정 평가 태그 분포</h2>
                  <TagDistribution distribution={stats.tag_distribution} />
                </div>
              </div>
            )}

            {/* ── 개선 제안 탭 ─── */}
            {activeTab === "suggestions" && (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                    💡 자동 개선 제안 ({suggestions.length})
                  </h2>
                  <button
                    onClick={() => loadData()}
                    className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700"
                  >
                    새로고침
                  </button>
                </div>

                {suggestions.length === 0 ? (
                  <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-8 text-center">
                    <p className="text-4xl mb-2">✨</p>
                    <p className="text-gray-600 dark:text-gray-400">
                      현재 개선 제안이 없습니다. 피드백이 축적되면 자동으로 제안이 생성됩니다.
                    </p>
                    <p className="text-xs text-gray-400 dark:text-gray-500 mt-2">
                      부정 평가 2건 이상 시 자동 제안 생성
                    </p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {suggestions.map((s) => (
                      <SuggestionCard key={s.id} suggestion={s} />
                    ))}
                  </div>
                )}

                {/* 제안 생성 조건 안내 */}
                <div className="bg-gray-50 dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 text-xs text-gray-500 dark:text-gray-400">
                  <p className="font-medium mb-1">📊 제안 생성 조건</p>
                  <ul className="list-disc list-inside space-y-0.5">
                    <li>환각(hallucination) 2건 이상 → 임베딩 모델 재평가 제안</li>
                    <li>관련 없는 결과(irrelevant) 2건 이상 → top-k 증설 제안</li>
                    <li>불완전 응답(incomplete) 2건 이상 → 청킹 크기 증설 제안</li>
                    <li>구식 정보(outdated) 2건 이상 → 재인덱싱 제안</li>
                    <li>잘못된 출처(wrong_source) 2건 이상 → 검색 정확도 개선 제안</li>
                    <li>만족률 70% 미만 (5건 이상) → 전반적 개선 제안</li>
                  </ul>
                </div>
              </div>
            )}

            {/* ── 피드백 목록 탭 ─── */}
            {activeTab === "list" && (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                    피드백 목록 ({feedbacks.length})
                  </h2>
                  <div className="flex gap-2">
                    {["", "thumbs_up", "thumbs_down", "correction"].map((type) => (
                      <button
                        key={type}
                        onClick={() => setFilterType(type as FeedbackType | "")}
                        className={`px-3 py-1 text-xs rounded-md ${
                          filterType === type
                            ? "bg-blue-600 text-white"
                            : "bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300"
                        }`}
                      >
                        {type === "" ? "전체" : type === "thumbs_up" ? "👍 긍정" : type === "thumbs_down" ? "👎 부정" : "✏️ 정정"}
                      </button>
                    ))}
                  </div>
                </div>

                {feedbacks.length === 0 ? (
                  <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-8 text-center">
                    <p className="text-gray-600 dark:text-gray-400">
                      아직 피드백이 없습니다. 채팅에서 👍👎 버튼으로 피드백을 남겨보세요.
                    </p>
                  </div>
                ) : (
                  <div className="space-y-2 max-h-[60vh] overflow-y-auto">
                    {feedbacks.map((fb) => (
                      <FeedbackItem key={fb.id} feedback={fb} />
                    ))}
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}