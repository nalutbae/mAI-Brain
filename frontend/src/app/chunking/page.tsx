"use client";

import { useState, useEffect } from "react";
import {
  listProfiles,
  createProfile,
  deleteProfile,
  previewChunking,
  type ChunkingProfile,
  type ChunkingStrategy,
  STRATEGY_LABELS,
  STRATEGY_DESCRIPTIONS,
} from "../../lib/chunking";

// ── 전략 아이콘 매핑 ─────────────────────────────────────────────────────
const STRATEGY_ICONS: Record<ChunkingStrategy, string> = {
  fixed: "📄",
  sentence: "📝",
  paragraph: "📰",
  section: "📋",
  article: "⚖️",
};

export default function ChunkingPage() {
  const [profiles, setProfiles] = useState<ChunkingProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedProfile, setSelectedProfile] = useState<string | null>(null);
  const [previewText, setPreviewText] = useState("");
  const [previewResult, setPreviewResult] = useState<any>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  // 새 프로파일 폼 상태
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [newStrategy, setNewStrategy] = useState<ChunkingStrategy>("fixed");
  const [newChunkSize, setNewChunkSize] = useState(700);
  const [newChunkOverlap, setNewChunkOverlap] = useState(150);
  const [newSeparator, setNewSeparator] = useState("");
  const [newMinSize, setNewMinSize] = useState(50);

  useEffect(() => {
    loadProfiles();
  }, []);

  const loadProfiles = async () => {
    try {
      const data = await listProfiles();
      setProfiles(data);
    } catch (e) {
      console.error("프로파일 로드 실패:", e);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    if (!newName.trim()) return;
    try {
      await createProfile({
        name: newName.trim(),
        description: newDescription.trim(),
        strategy: newStrategy,
        chunk_size: newChunkSize,
        chunk_overlap: newChunkOverlap,
        separator_pattern: newSeparator.trim(),
        min_chunk_size: newMinSize,
      });
      setShowCreateForm(false);
      setNewName("");
      setNewDescription("");
      setNewStrategy("fixed");
      setNewChunkSize(700);
      setNewChunkOverlap(150);
      setNewSeparator("");
      setNewMinSize(50);
      await loadProfiles();
    } catch (e) {
      console.error("프로파일 생성 실패:", e);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("이 프로파일을 삭제하시겠습니까?")) return;
    try {
      await deleteProfile(id);
      await loadProfiles();
    } catch (e) {
      console.error("삭제 실패:", e);
    }
  };

  const handlePreview = async () => {
    if (!previewText.trim()) return;
    setPreviewLoading(true);
    try {
      const result = await previewChunking({
        text: previewText,
        profile_id: selectedProfile || undefined,
      });
      setPreviewResult(result);
    } catch (e) {
      console.error("미리보기 실패:", e);
    } finally {
      setPreviewLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-gray-500">로딩 중...</p>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto p-4 sm:p-6 lg:p-8 space-y-6">
      {/* 헤더 */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-white">
            ⚙️ 청킹 프로파일
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            도메인별 시맨틱 청킹 프로파일 관리 — 법률, 논문, 뉴스 등 문서 유형에 최적화된 청킹 전략
          </p>
        </div>
        <button
          onClick={() => setShowCreateForm(!showCreateForm)}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm whitespace-nowrap"
        >
          + 새 프로파일
        </button>
      </div>

      {/* 새 프로파일 생성 폼 */}
      {showCreateForm && (
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-4 sm:p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            새 커스텀 프로파일
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                이름
              </label>
              <input
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                className="w-full rounded-lg border border-gray-300 dark:border-gray-600 px-3 py-2 text-sm dark:bg-gray-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:outline-none"
                placeholder="예: legal_custom"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                전략
              </label>
              <select
                value={newStrategy}
                onChange={(e) => setNewStrategy(e.target.value as ChunkingStrategy)}
                className="w-full rounded-lg border border-gray-300 dark:border-gray-600 px-3 py-2 text-sm dark:bg-gray-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:outline-none"
              >
                {Object.entries(STRATEGY_LABELS).map(([key, label]) => (
                  <option key={key} value={key}>
                    {STRATEGY_ICONS[key as ChunkingStrategy]} {label} — {STRATEGY_DESCRIPTIONS[key as ChunkingStrategy]}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                청크 크기
              </label>
              <input
                type="number"
                value={newChunkSize}
                onChange={(e) => setNewChunkSize(Number(e.target.value))}
                className="w-full rounded-lg border border-gray-300 dark:border-gray-600 px-3 py-2 text-sm dark:bg-gray-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:outline-none"
                min={100}
                max={5000}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                오버랩
              </label>
              <input
                type="number"
                value={newChunkOverlap}
                onChange={(e) => setNewChunkOverlap(Number(e.target.value))}
                className="w-full rounded-lg border border-gray-300 dark:border-gray-600 px-3 py-2 text-sm dark:bg-gray-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:outline-none"
                min={0}
                max={1000}
              />
            </div>
            <div className="sm:col-span-2">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                구분자 패턴 (정규식, 선택)
              </label>
              <input
                type="text"
                value={newSeparator}
                onChange={(e) => setNewSeparator(e.target.value)}
                className="w-full rounded-lg border border-gray-300 dark:border-gray-600 px-3 py-2 text-sm dark:bg-gray-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:outline-none"
                placeholder="예: 제\d+조|제\d+장"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                최소 청크 크기
              </label>
              <input
                type="number"
                value={newMinSize}
                onChange={(e) => setNewMinSize(Number(e.target.value))}
                className="w-full rounded-lg border border-gray-300 dark:border-gray-600 px-3 py-2 text-sm dark:bg-gray-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:outline-none"
                min={10}
                max={500}
              />
            </div>
            <div className="sm:col-span-2">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                설명
              </label>
              <input
                type="text"
                value={newDescription}
                onChange={(e) => setNewDescription(e.target.value)}
                className="w-full rounded-lg border border-gray-300 dark:border-gray-600 px-3 py-2 text-sm dark:bg-gray-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:outline-none"
                placeholder="프로파일 용도 설명"
              />
            </div>
          </div>
          <div className="flex justify-end gap-3 mt-4">
            <button
              onClick={() => setShowCreateForm(false)}
              className="px-4 py-2 text-gray-600 dark:text-gray-400 hover:text-gray-800 text-sm"
            >
              취소
            </button>
            <button
              onClick={handleCreate}
              disabled={!newName.trim()}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors text-sm"
            >
              생성
            </button>
          </div>
        </div>
      )}

      {/* 프로파일 카드 그리드 */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {profiles.map((profile) => (
          <div
            key={profile.id}
            className={`bg-white dark:bg-gray-800 rounded-xl shadow-sm border-2 p-4 transition-all cursor-pointer ${
              selectedProfile === profile.id
                ? "border-blue-500 ring-2 ring-blue-200"
                : "border-gray-200 dark:border-gray-700 hover:border-blue-300"
            }`}
            onClick={() => setSelectedProfile(selectedProfile === profile.id ? null : profile.id)}
          >
            <div className="flex items-start justify-between mb-2">
              <div className="flex items-center gap-2">
                <span className="text-xl">{STRATEGY_ICONS[profile.strategy]}</span>
                <h3 className="font-semibold text-gray-900 dark:text-white">
                  {profile.name}
                </h3>
              </div>
              {profile.is_default && (
                <span className="px-2 py-0.5 bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300 text-xs rounded-full">
                  기본값
                </span>
              )}
            </div>
            <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
              {profile.description}
            </p>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-2">
                <span className="text-gray-500 dark:text-gray-400">전략</span>
                <p className="font-medium text-gray-900 dark:text-white">
                  {STRATEGY_LABELS[profile.strategy]}
                </p>
              </div>
              <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-2">
                <span className="text-gray-500 dark:text-gray-400">크기</span>
                <p className="font-medium text-gray-900 dark:text-white">
                  {profile.chunk_size}자
                </p>
              </div>
              <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-2">
                <span className="text-gray-500 dark:text-gray-400">오버랩</span>
                <p className="font-medium text-gray-900 dark:text-white">
                  {profile.chunk_overlap}자
                </p>
              </div>
              <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-2">
                <span className="text-gray-500 dark:text-gray-400">최소</span>
                <p className="font-medium text-gray-900 dark:text-white">
                  {profile.min_chunk_size}자
                </p>
              </div>
            </div>
            {!profile.is_default && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  handleDelete(profile.id);
                }}
                className="mt-3 text-xs text-red-500 hover:text-red-700 transition-colors"
              >
                삭제
              </button>
            )}
          </div>
        ))}
      </div>

      {/* 청킹 미리보기 */}
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-4 sm:p-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          🔍 청킹 미리보기
        </h2>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-3">
          {selectedProfile
            ? `프로파일: ${profiles.find((p) => p.id === selectedProfile)?.name || selectedProfile}`
            : "기본 프로파일로 미리보기 (프로파일 카드를 클릭하여 선택)"}
        </p>
        <textarea
          value={previewText}
          onChange={(e) => setPreviewText(e.target.value)}
          className="w-full rounded-lg border border-gray-300 dark:border-gray-600 px-4 py-3 text-sm dark:bg-gray-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:outline-none mb-3"
          rows={5}
          placeholder="청킹할 텍스트를 입력하세요..."
        />
        <button
          onClick={handlePreview}
          disabled={!previewText.trim() || previewLoading}
          className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors text-sm"
        >
          {previewLoading ? "처리 중..." : "미리보기 실행"}
        </button>

        {previewResult && (
          <div className="mt-4 space-y-3">
            <div className="flex flex-wrap gap-3 text-sm">
              <span className="px-3 py-1 bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300 rounded-full">
                총 청크: {previewResult.total_chunks}개
              </span>
              <span className="px-3 py-1 bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-300 rounded-full">
                평균 크기: {previewResult.avg_chunk_size.toFixed(0)}자
              </span>
              <span className="px-3 py-1 bg-yellow-100 dark:bg-yellow-900 text-yellow-700 dark:text-yellow-300 rounded-full">
                전체 글자: {previewResult.total_chars.toLocaleString()}자
              </span>
            </div>
            <div className="space-y-2">
              {previewResult.chunks.map((chunk: any, idx: number) => (
                <div
                  key={idx}
                  className="bg-gray-50 dark:bg-gray-700 rounded-lg p-3 border-l-4 border-blue-400"
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
                      청크 {idx + 1}
                    </span>
                    <span className="text-xs text-gray-400 dark:text-gray-500">
                      {chunk.length}자
                    </span>
                  </div>
                  <p className="text-sm text-gray-800 dark:text-gray-200 whitespace-pre-wrap">
                    {chunk.text}
                  </p>
                </div>
              ))}
              {previewResult.total_chunks > 10 && (
                <p className="text-xs text-center text-gray-400 dark:text-gray-500">
                  ... 총 {previewResult.total_chunks}개 중 처음 10개만 표시
                </p>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}