"use client";

import { useState, useEffect, useCallback } from "react";
import {
  SystemPrompt,
  SystemPromptCreate,
  PromptMode,
  SystemPromptPreview,
  listPrompts,
  createPrompt,
  updatePrompt,
  deletePrompt,
  previewPrompt,
  listDefaultPrompts,
  listSupportedVariables,
} from "../../../lib/api";

// ── 모드 탭 설정 ───────────────────────────────────────────────────────

const MODES: { key: PromptMode; label: string; icon: string; desc: string }[] = [
  { key: "fact", label: "팩트", icon: "🔍", desc: "정확한 사실 조회" },
  { key: "summary", label: "요약", icon: "📋", desc: "문서 종합 요약" },
  { key: "column", label: "컬럼", icon: "✍️", desc: "종합 글 작성" },
  { key: "reasoning", label: "추론", icon: "🧠", desc: "문서 교차 분석" },
  { key: "creative", label: "창의", icon: "💡", desc: "자유로운 대화" },
];

// ── 변수 삽입 도우미 ───────────────────────────────────────────────────

function VariableHelper({
  variables,
  onInsert,
}: {
  variables: Record<string, string>;
  onInsert: (varName: string) => void;
}) {
  return (
    <div className="mt-2">
      <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">
        사용 가능한 변수 (클릭하여 삽입):
      </p>
      <div className="flex flex-wrap gap-1.5">
        {Object.entries(variables).map(([name, desc]) => (
          <button
            key={name}
            type="button"
            onClick={() => onInsert(name)}
            className="inline-flex items-center gap-1 px-2 py-1 text-xs rounded-md
              bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300
              hover:bg-blue-100 dark:hover:bg-blue-900/50 border border-blue-200 dark:border-blue-800
              transition-colors"
            title={desc}
          >
            {`{{${name}}}`}
          </button>
        ))}
      </div>
    </div>
  );
}

// ── 미리보기 패널 ─────────────────────────────────────────────────────

function PreviewPanel({
  preview,
  loading,
}: {
  preview: SystemPromptPreview | null;
  loading: boolean;
}) {
  if (loading) {
    return (
      <div className="p-4 text-center text-gray-500 text-sm">미리보기 로딩 중...</div>
    );
  }

  if (!preview) {
    return (
      <div className="p-4 text-center text-gray-400 text-sm">
        프롬프트를 선택하고 미리보기를 실행하세요
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {preview.variables_used.length > 0 && (
        <div>
          <p className="text-xs font-medium text-gray-500 mb-1">치환된 변수:</p>
          <div className="flex flex-wrap gap-1">
            {preview.variables_used.map((v) => (
              <span key={v} className="px-2 py-0.5 text-xs rounded bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300">
                {`{{${v}}}`}
              </span>
            ))}
          </div>
        </div>
      )}
      {preview.variables_missing.length > 0 && (
        <div>
          <p className="text-xs font-medium text-gray-500 mb-1">치환 불가 변수:</p>
          <div className="flex flex-wrap gap-1">
            {preview.variables_missing.map((v) => (
              <span key={v} className="px-2 py-0.5 text-xs rounded bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300">
                {`{{${v}}}`}
              </span>
            ))}
          </div>
        </div>
      )}
      <div>
        <p className="text-xs font-medium text-gray-500 mb-1">치환 결과:</p>
        <div className="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg text-sm text-gray-900 dark:text-gray-200 whitespace-pre-wrap font-mono max-h-64 overflow-y-auto">
          {preview.rendered_text}
        </div>
      </div>
    </div>
  );
}

// ── 메인 페이지 ────────────────────────────────────────────────────────

export default function PromptsPage() {
  const [activeMode, setActiveMode] = useState<PromptMode>("fact");
  const [prompts, setPrompts] = useState<SystemPrompt[]>([]);
  const [defaults, setDefaults] = useState<SystemPrompt[]>([]);
  const [variables, setVariables] = useState<Record<string, string>>({});
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [editText, setEditText] = useState("");
  const [preview, setPreview] = useState<SystemPromptPreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const selected = prompts.find((p) => p.id === selectedId) || null;
  const isDefault = selected?.is_default || false;

  // 데이터 로드
  const loadData = useCallback(async () => {
    try {
      const [allRes, defRes, varRes] = await Promise.all([
        listPrompts({ mode: activeMode }),
        listDefaultPrompts(),
        listSupportedVariables(),
      ]);
      setPrompts(allRes.prompts);
      setDefaults(defRes.prompts.filter((p) => p.mode === activeMode));
      setVariables(varRes.variables);
      setError(null);
    } catch {
      setError("프롬프트 목록을 불러오는데 실패했습니다.");
    }
  }, [activeMode]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // 프롬프트 선택
  const handleSelect = (id: string) => {
    const p = prompts.find((pr) => pr.id === id);
    if (p) {
      setSelectedId(id);
      setEditText(p.prompt_text);
      setPreview(null);
    }
  };

  // 변수 삽입
  const handleInsertVariable = (name: string) => {
    setEditText((prev) => prev + `{{${name}}}`);
  };

  // 미리보기
  const handlePreview = async () => {
    if (!selectedId) return;
    setPreviewLoading(true);
    try {
      const result = await previewPrompt(selectedId, selected?.workspace_id ?? undefined);
      setPreview(result);
      setError(null);
    } catch {
      setError("미리보기 생성에 실패했습니다.");
    } finally {
      setPreviewLoading(false);
    }
  };

  // 저장 (기본 프롬프트 = 수정, 커스텀 = 생성/수정)
  const handleSave = async () => {
    if (!editText.trim()) {
      setError("프롬프트 내용을 입력해주세요.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      if (selectedId) {
        await updatePrompt(selectedId, { prompt_text: editText });
        setSuccessMsg("프롬프트가 수정되었습니다.");
      } else {
        await createPrompt({
          mode: activeMode,
          prompt_text: editText,
          workspace_id: null,
        });
        setSuccessMsg("새 프롬프트가 생성되었습니다.");
        setEditText("");
      }
      await loadData();
    } catch (e: any) {
      setError(e?.message || "저장에 실패했습니다.");
    } finally {
      setSaving(false);
    }
  };

  // 삭제
  const handleDelete = async (id: string) => {
    if (!confirm("정말 삭제하시겠습니까?")) return;
    try {
      await deletePrompt(id);
      setSuccessMsg("프롬프트가 삭제되었습니다.");
      if (selectedId === id) {
        setSelectedId(null);
        setEditText("");
        setPreview(null);
      }
      await loadData();
    } catch {
      setError("프롬프트 삭제에 실패했습니다.");
    }
  };

  return (
    <div className="flex-1 flex flex-col h-full">
      {/* 헤더 */}
      <header className="border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-6 py-4">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
          📝 시스템 프롬프트 관리
        </h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          워크스페이스별·모드별 커스텀 시스템 프롬프트를 설정합니다
        </p>
      </header>

      {/* 메인 컨텐츠 */}
      <div className="flex-1 overflow-y-auto p-6">
        {/* 알림 */}
        {error && (
          <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-lg text-sm text-red-700 dark:text-red-300">
            {error}
          </div>
        )}
        {successMsg && (
          <div className="mb-4 p-3 bg-green-50 dark:bg-green-900/30 border border-green-200 dark:border-green-800 rounded-lg text-sm text-green-700 dark:text-green-300">
            {successMsg}
          </div>
        )}

        {/* 모드 탭 */}
        <div className="flex gap-1 mb-6 bg-gray-100 dark:bg-gray-800 rounded-xl p-1">
          {MODES.map((m) => (
            <button
              key={m.key}
              onClick={() => {
                setActiveMode(m.key);
                setSelectedId(null);
                setEditText("");
                setPreview(null);
              }}
              className={`flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-colors
                ${
                  activeMode === m.key
                    ? "bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm"
                    : "text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300"
                }`}
            >
              <span>{m.icon}</span>
              <span>{m.label}</span>
            </button>
          ))}
        </div>

        {/* 기본 프롬프트 표시 */}
        {defaults.length > 0 && (
          <section className="mb-6">
            <h2 className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-3">
              기본 프롬프트 (수정 가능)
            </h2>
            <div className="space-y-2">
              {defaults.map((p) => (
                <button
                  key={p.id}
                  onClick={() => handleSelect(p.id)}
                  className={`w-full text-left p-3 rounded-lg border transition-colors
                    ${
                      selectedId === p.id
                        ? "border-blue-500 bg-blue-50 dark:bg-blue-900/20"
                        : "border-gray-200 dark:border-gray-700 hover:border-blue-300 dark:hover:border-blue-700"
                    }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-gray-900 dark:text-gray-200">
                      기본 프롬프트
                    </span>
                    <span className="text-xs px-2 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-gray-500">
                      기본값
                    </span>
                  </div>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 line-clamp-2">
                    {p.prompt_text.slice(0, 100)}...
                  </p>
                </button>
              ))}
            </div>
          </section>
        )}

        {/* 커스텀 프롬프트 목록 */}
        {prompts.filter((p) => !p.is_default).length > 0 && (
          <section className="mb-6">
            <h2 className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-3">
              커스텀 프롬프트
            </h2>
            <div className="space-y-2">
              {prompts
                .filter((p) => !p.is_default)
                .map((p) => (
                  <button
                    key={p.id}
                    onClick={() => handleSelect(p.id)}
                    className={`w-full text-left p-3 rounded-lg border transition-colors
                      ${
                        selectedId === p.id
                          ? "border-blue-500 bg-blue-50 dark:bg-blue-900/20"
                          : "border-gray-200 dark:border-gray-700 hover:border-blue-300 dark:hover:border-blue-700"
                      }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-gray-900 dark:text-gray-200">
                        {p.workspace_id
                          ? `워크스페이스: ${p.workspace_id}`
                          : "커스텀"}
                      </span>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDelete(p.id);
                        }}
                        className="text-xs text-red-500 hover:text-red-700"
                      >
                        삭제
                      </button>
                    </div>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 line-clamp-2">
                      {p.prompt_text.slice(0, 100)}...
                    </p>
                  </button>
                ))}
            </div>
          </section>
        )}

        {/* 프롬프트 편집기 */}
        <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* 편집 영역 */}
          <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              {selectedId
                ? isDefault
                  ? "기본 프롬프트 수정"
                  : "커스텀 프롬프트 수정"
                : "새 프롬프트 작성"}
            </h2>

            <textarea
              value={editText}
              onChange={(e) => setEditText(e.target.value)}
              placeholder="프롬프트 내용을 입력하세요. {{workspace_name}}와 같은 변수를 사용할 수 있습니다."
              rows={12}
              className="w-full p-3 border border-gray-300 dark:border-gray-600 rounded-lg
                bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-200 text-sm font-mono
                focus:ring-2 focus:ring-blue-500 focus:border-transparent
                placeholder-gray-400 dark:placeholder-gray-500"
            />

            <VariableHelper variables={variables} onInsert={handleInsertVariable} />

            <div className="flex gap-2 mt-4">
              <button
                onClick={handleSave}
                disabled={saving}
                className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700
                  disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
              >
                {saving ? "저장 중..." : selectedId ? "수정 저장" : "생성"}
              </button>
              <button
                onClick={handlePreview}
                disabled={!selectedId || previewLoading}
                className="px-4 py-2 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300
                  text-sm rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600
                  disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {previewLoading ? "미리보기 중..." : "미리보기"}
              </button>
              {selectedId && (
                <button
                  onClick={() => {
                    setSelectedId(null);
                    setEditText("");
                    setPreview(null);
                  }}
                  className="px-4 py-2 text-sm text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
                >
                  취소
                </button>
              )}
            </div>
          </div>

          {/* 미리보기 영역 */}
          <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              미리보기
            </h2>
            <PreviewPanel preview={preview} loading={previewLoading} />
          </div>
        </section>
      </div>
    </div>
  );
}
