"use client";

import { useState, useEffect, useCallback } from "react";
import { AdminGuard } from "../../../components/AuthGuard";
import {
  ChunkingProfile,
  ChunkingStrategy,
  ChunkPreview,
  listChunkingProfiles,
  createChunkingProfile,
  deleteChunkingProfile,
  setDefaultChunkingProfile,
  previewChunking,
} from "../../../lib/api";

// ── 전략 라벨 ──────────────────────────────────────────────────────────

const STRATEGY_LABELS: Record<ChunkingStrategy, { label: string; desc: string }> = {
  fixed: { label: "고정", desc: "700토큰 고정 크기 청킹" },
  sentence: { label: "문장", desc: "문장 단위 청킹" },
  paragraph: { label: "단락", desc: "빈 줄 기준 단락 청킹" },
  section: { label: "섹션", desc: "섹션 제목 기준 청킹" },
  article: { label: "조문", desc: "제X조 경계 인식 청킹" },
};

// ── 전략 뱃지 ────────────────────────────────────────────────────────────

function StrategyBadge({ strategy }: { strategy: ChunkingStrategy }) {
  const info = STRATEGY_LABELS[strategy];
  const colors: Record<ChunkingStrategy, string> = {
    fixed: "bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300",
    sentence: "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300",
    paragraph: "bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300",
    section: "bg-purple-100 text-purple-700 dark:bg-purple-900 dark:text-purple-300",
    article: "bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300",
  };

  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${colors[strategy]}`}>
      {info?.label || strategy}
    </span>
  );
}

// ── 프로파일 카드 ──────────────────────────────────────────────────────

function ProfileCard({
  profile,
  onSetDefault,
  onDelete,
  onPreview,
}: {
  profile: ChunkingProfile;
  onSetDefault: (id: string) => void;
  onDelete: (id: string) => void;
  onPreview: (profile: ChunkingProfile) => void;
}) {
  const isBuiltin = profile.id.startsWith("builtin_");

  return (
    <div className={`bg-white dark:bg-gray-900 rounded-xl border ${
      profile.is_default
        ? "border-blue-400 dark:border-blue-500 ring-1 ring-blue-200 dark:ring-blue-800"
        : "border-gray-200 dark:border-gray-700"
    } p-4 relative`}>
      {profile.is_default && (
        <div className="absolute top-2 right-2">
          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-600 text-white">
            기본
          </span>
        </div>
      )}

      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-white">
              {profile.name}
            </h3>
            <StrategyBadge strategy={profile.strategy} />
          </div>
          {profile.description && (
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">
              {profile.description}
            </p>
          )}

          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-gray-600 dark:text-gray-400">
            <div>청크 크기: <span className="font-medium text-gray-900 dark:text-gray-200">{profile.chunk_size}</span></div>
            <div>오버랩: <span className="font-medium text-gray-900 dark:text-gray-200">{profile.chunk_overlap}</span></div>
            <div>최소 크기: <span className="font-medium text-gray-900 dark:text-gray-200">{profile.min_chunk_size}</span></div>
            <div>
              패턴: {profile.separator_pattern ? (
                <code className="text-xs bg-gray-100 dark:bg-gray-800 px-1 rounded">
                  {profile.separator_pattern.slice(0, 30)}{profile.separator_pattern.length > 30 ? "..." : ""}
                </code>
              ) : (
                <span className="text-gray-400">없음</span>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2 mt-3 pt-2 border-t border-gray-100 dark:border-gray-800">
        <button
          onClick={() => onPreview(profile)}
          className="px-3 py-1 text-xs font-medium text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300 bg-blue-50 dark:bg-blue-900/30 rounded-lg hover:bg-blue-100 dark:hover:bg-blue-900/50 transition-colors"
        >
          미리보기
        </button>
        {!profile.is_default && (
          <button
            onClick={() => onSetDefault(profile.id)}
            className="px-3 py-1 text-xs font-medium text-gray-600 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300 bg-gray-50 dark:bg-gray-800 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
          >
            기본으로 설정
          </button>
        )}
        {!isBuiltin && (
          <button
            onClick={() => onDelete(profile.id)}
            className="px-3 py-1 text-xs font-medium text-red-600 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300 bg-red-50 dark:bg-red-900/30 rounded-lg hover:bg-red-100 dark:hover:bg-red-900/50 transition-colors ml-auto"
          >
            삭제
          </button>
        )}
      </div>
    </div>
  );
}

// ── 미리보기 모달 ──────────────────────────────────────────────────────

function PreviewModal({
  preview,
  profileName,
  onClose,
}: {
  preview: ChunkPreview;
  profileName: string;
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div
        className="bg-white dark:bg-gray-900 rounded-xl shadow-xl max-w-3xl w-full max-h-[80vh] overflow-hidden mx-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
              청킹 미리보기
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              프로파일: {profileName}
            </p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="p-4 border-b border-gray-200 dark:border-gray-700">
          <div className="grid grid-cols-3 gap-4 text-center">
            <div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">{preview.total_chunks}</p>
              <p className="text-xs text-gray-500">전체 청크 수</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">{preview.avg_chunk_size}</p>
              <p className="text-xs text-gray-500">평균 청크 크기</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">{preview.total_chars}</p>
              <p className="text-xs text-gray-500">전체 글자 수</p>
            </div>
          </div>
        </div>

        <div className="overflow-y-auto p-4 space-y-3" style={{ maxHeight: "calc(80vh - 200px)" }}>
          {preview.chunks.map((chunk, i) => (
            <div key={i} className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
                  청크 #{chunk.index + 1}
                </span>
                <span className="text-xs text-gray-400 dark:text-gray-500">
                  {chunk.full_length}자
                </span>
              </div>
              <p className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap leading-relaxed">
                {chunk.text}
              </p>
            </div>
          ))}
          {preview.total_chunks > 10 && (
            <p className="text-xs text-center text-gray-400 dark:text-gray-500">
              처음 10개 청크만 표시됩니다 (전체 {preview.total_chunks}개)
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

// ── 메인 페이지 ────────────────────────────────────────────────────────

export default function ChunkingPage() {
  return (
    <AdminGuard>
      <ChunkingContent />
    </AdminGuard>
  );
}

function ChunkingContent() {
  const [profiles, setProfiles] = useState<ChunkingProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // 미리보기 상태
  const [previewText, setPreviewText] = useState("");
  const [selectedProfileId, setSelectedProfileId] = useState<string>("");
  const [previewResult, setPreviewResult] = useState<ChunkPreview | null>(null);
  const [previewProfile, setPreviewProfile] = useState<ChunkingProfile | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  // 새 프로파일 폼 상태
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [newStrategy, setNewStrategy] = useState<ChunkingStrategy>("fixed");
  const [newChunkSize, setNewChunkSize] = useState(700);
  const [newChunkOverlap, setNewChunkOverlap] = useState(150);
  const [newMinChunkSize, setNewMinChunkSize] = useState(50);
  const [newSeparatorPattern, setNewSeparatorPattern] = useState("");
  const [createLoading, setCreateLoading] = useState(false);

  const loadProfiles = useCallback(async () => {
    try {
      const data = await listChunkingProfiles();
      setProfiles(data);
      setError(null);
    } catch {
      setError("프로파일 목록을 불러오는데 실패했습니다.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadProfiles();
  }, [loadProfiles]);

  const handleSetDefault = async (id: string) => {
    try {
      await setDefaultChunkingProfile(id);
      setSuccess("기본 프로파일이 변경되었습니다.");
      await loadProfiles();
    } catch {
      setError("기본 프로파일 변경에 실패했습니다.");
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("정말 삭제하시겠습니까?")) return;
    try {
      await deleteChunkingProfile(id);
      setSuccess("프로파일이 삭제되었습니다.");
      await loadProfiles();
    } catch (e: any) {
      setError(e?.message || "프로파일 삭제에 실패했습니다.");
    }
  };

  const handleCreate = async () => {
    if (!newName.trim()) {
      setError("프로파일 이름을 입력해주세요.");
      return;
    }
    setCreateLoading(true);
    try {
      await createChunkingProfile({
        name: newName.trim(),
        description: newDesc.trim() || undefined,
        strategy: newStrategy,
        chunk_size: newChunkSize,
        chunk_overlap: newChunkOverlap,
        min_chunk_size: newMinChunkSize,
        separator_pattern: newSeparatorPattern.trim() || undefined,
      });
      setSuccess("프로파일이 생성되었습니다.");
      setShowCreateForm(false);
      setNewName("");
      setNewDesc("");
      setNewStrategy("fixed");
      setNewChunkSize(700);
      setNewChunkOverlap(150);
      setNewMinChunkSize(50);
      setNewSeparatorPattern("");
      await loadProfiles();
    } catch (e: any) {
      setError(e?.message || "프로파일 생성에 실패했습니다.");
    } finally {
      setCreateLoading(false);
    }
  };

  const handlePreview = async (profile: ChunkingProfile) => {
    setPreviewProfile(profile);
    setPreviewLoading(true);
    try {
      const result = await previewChunking({
        text: previewText || "제1조(목적) 이 법은 국가의 재정운영에 필요한 세입·세출의 기준과 그에 따른 재정운영 및 책임에 관한 사항을 규정함으로써 재정의 건전성을 유지하게 함을 목적으로 한다. 제2조(정의) 이 법에서 사용하는 용어의 뜻은 다음과 같다. 1. '세입'이란 국가가 어떠한 방법으로도 수익을 얻을 목적으로 하는 수입으로서 그 원본의 보전을 요하지 아니하는 것을 말한다. 2. '세출'이란 국가가 어떠한 목적을 위하여 지출하는 경비를 말한다.",
        profile_id: profile.id,
      });
      setPreviewResult(result);
    } catch (e: any) {
      setError(e?.message || "미리보기에 실패했습니다.");
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleCustomPreview = async () => {
    if (!previewText.trim()) {
      setError("미리보기할 텍스트를 입력해주세요.");
      return;
    }
    setPreviewLoading(true);
    try {
      const result = await previewChunking({
        text: previewText,
        profile_id: selectedProfileId || undefined,
        chunk_size: selectedProfileId ? undefined : 700,
        chunk_overlap: selectedProfileId ? undefined : 150,
      });
      const profile = selectedProfileId
        ? profiles.find((p) => p.id === selectedProfileId)
        : null;
      setPreviewProfile(profile || null);
      setPreviewResult(result);
    } catch (e: any) {
      setError(e?.message || "미리보기에 실패했습니다.");
    } finally {
      setPreviewLoading(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col h-full">
      {/* 헤더 */}
      <header className="border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
              ⚙️ 청킹 프로파일
            </h1>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              도메인별 시맨틱 청킹 프로파일 관리 및 미리보기
            </p>
          </div>
          <button
            onClick={() => setShowCreateForm(true)}
            className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 transition-colors"
          >
            + 새 프로파일
          </button>
        </div>
      </header>

      {/* 알림 */}
      {error && (
        <div className="mx-6 mt-4 p-3 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-lg text-sm text-red-700 dark:text-red-300">
          {error}
          <button onClick={() => setError(null)} className="ml-2 text-red-500 hover:text-red-700">&times;</button>
        </div>
      )}
      {success && (
        <div className="mx-6 mt-4 p-3 bg-green-50 dark:bg-green-900/30 border border-green-200 dark:border-green-800 rounded-lg text-sm text-green-700 dark:text-green-300">
          {success}
          <button onClick={() => setSuccess(null)} className="ml-2 text-green-500 hover:text-green-700">&times;</button>
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-6 space-y-8">
        {/* 프로파일 목록 */}
        <section>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            프로파일 목록
          </h2>
          {loading ? (
            <div className="text-center text-gray-500 py-12">로딩 중...</div>
          ) : profiles.length === 0 ? (
            <div className="text-center text-gray-500 py-12">프로파일이 없습니다.</div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {profiles.map((p) => (
                <ProfileCard
                  key={p.id}
                  profile={p}
                  onSetDefault={handleSetDefault}
                  onDelete={handleDelete}
                  onPreview={handlePreview}
                />
              ))}
            </div>
          )}
        </section>

        {/* 미리보기 */}
        <section className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            청킹 미리보기
          </h2>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                프로파일 선택
              </label>
              <select
                value={selectedProfileId}
                onChange={(e) => setSelectedProfileId(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm"
              >
                <option value="">커스텀 설정</option>
                {profiles.map((p) => (
                  <option key={p.id} value={p.id}>{p.name} ({p.strategy})</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                미리보기 텍스트
              </label>
              <textarea
                value={previewText}
                onChange={(e) => setPreviewText(e.target.value)}
                rows={6}
                placeholder="청킹할 텍스트를 입력하세요..."
                className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm font-mono resize-y"
              />
            </div>
            <button
              onClick={handleCustomPreview}
              disabled={previewLoading || !previewText.trim()}
              className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
            >
              {previewLoading ? "처리 중..." : "미리보기 실행"}
            </button>
          </div>
        </section>
      </div>

      {/* 새 프로파일 생성 모달 */}
      {showCreateForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setShowCreateForm(false)}>
          <div
            className="bg-white dark:bg-gray-900 rounded-xl shadow-xl max-w-lg w-full mx-4 max-h-[80vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                  새 청킹 프로파일
                </h2>
                <button onClick={() => setShowCreateForm(false)} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>

              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">이름 *</label>
                  <input
                    type="text"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    placeholder="예: legal_custom"
                    className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">설명</label>
                  <input
                    type="text"
                    value={newDesc}
                    onChange={(e) => setNewDesc(e.target.value)}
                    placeholder="프로파일 설명"
                    className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">청킹 전략</label>
                  <select
                    value={newStrategy}
                    onChange={(e) => setNewStrategy(e.target.value as ChunkingStrategy)}
                    className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm"
                  >
                    {Object.entries(STRATEGY_LABELS).map(([key, info]) => (
                      <option key={key} value={key}>{info.label} — {info.desc}</option>
                    ))}
                  </select>
                </div>

                <div className="grid grid-cols-3 gap-3">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">청크 크기</label>
                    <input
                      type="number"
                      value={newChunkSize}
                      onChange={(e) => setNewChunkSize(Number(e.target.value))}
                      className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">오버랩</label>
                    <input
                      type="number"
                      value={newChunkOverlap}
                      onChange={(e) => setNewChunkOverlap(Number(e.target.value))}
                      className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">최소 크기</label>
                    <input
                      type="number"
                      value={newMinChunkSize}
                      onChange={(e) => setNewMinChunkSize(Number(e.target.value))}
                      className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">분할 패턴 (정규식)</label>
                  <input
                    type="text"
                    value={newSeparatorPattern}
                    onChange={(e) => setNewSeparatorPattern(e.target.value)}
                    placeholder="예: (?=제\d+조) 또는 \n\s*\n"
                    className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm font-mono"
                  />
                  <p className="text-xs text-gray-400 mt-1">비워두면 전략 기본값이 사용됩니다.</p>
                </div>

                <button
                  onClick={handleCreate}
                  disabled={createLoading || !newName.trim()}
                  className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
                >
                  {createLoading ? "생성 중..." : "프로파일 생성"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 미리보기 결과 모달 */}
      {previewResult && previewProfile && (
        <PreviewModal
          preview={previewResult}
          profileName={previewProfile.name}
          onClose={() => {
            setPreviewResult(null);
            setPreviewProfile(null);
          }}
        />
      )}
    </div>
  );
}