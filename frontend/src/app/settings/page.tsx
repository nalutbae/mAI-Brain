"use client";

import { useState, useEffect } from "react";
import {
  listLLMProviders,
  createLLMProvider,
  updateLLMProvider,
  deleteLLMProvider,
  activateLLMProvider,
  getEmbeddingProvider,
  updateEmbeddingProvider,
  listAvailableLLMProviders,
  listAvailableEmbeddingProviders,
  testProviderConnection,
  getRerankerConfig,
  updateRerankerConfig,
  getOcrConfig,
  updateOcrConfig,
  type LLMProvider,
  type EmbeddingProvider,
  type LLMProviderConfig,
  type EmbeddingConfig,
  type ProviderDefaults,
  type ConnectionTestResult,
  type RerankerConfig,
} from "@/lib/api";

// ── 프로바이더 아이콘 ──────────────────────────────────────────────────────
const PROVIDER_ICONS: Record<string, string> = {
  ollama: "🦙",
  openai: "🧠",
  anthropic: "🧪",
  groq: "⚡",
  deepseek: "🔍",
  custom: "🔧",
};

const PROVIDER_LABELS: Record<string, string> = {
  ollama: "Ollama",
  openai: "OpenAI",
  anthropic: "Anthropic",
  groq: "Groq",
  deepseek: "DeepSeek",
  custom: "Custom (OpenAI 호환)",
};

const EMBEDDING_ICONS: Record<string, string> = {
  local: "🏠",
  openai: "🧠",
  jina: "🔮",
  ollama: "🦙",
  cohere: "🎯",
};

const EMBEDDING_LABELS: Record<string, string> = {
  local: "bge-m3 (로컬)",
  openai: "OpenAI",
  jina: "Jina AI",
  ollama: "Ollama",
  cohere: "Cohere",
};

// 임베딩 프로바이더 변경 시 경고 메시지
const EMBEDDING_CHANGE_WARNING =
  "⚠️ 임베딩 모델을 변경하면 기존에 인덱싱된 문서와 호환되지 않습니다. " +
  "새 모델로 모든 문서를 다시 인덱싱해야 합니다.";

export default function SettingsPage() {
  // ── LLM providers ────────────────────────────────────────────────────
  const [providers, setProviders] = useState<LLMProviderConfig[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [availableLLM, setAvailableLLM] = useState<ProviderDefaults[]>([]);
  const [llmLoading, setLlmLoading] = useState(true);
  const [editingKeyId, setEditingKeyId] = useState<string | null>(null);
  const [editApiKeyEnvVar, setEditApiKeyEnvVar] = useState("");

  // ── Embedding ────────────────────────────────────────────────────────
  const [embedding, setEmbedding] = useState<EmbeddingConfig | null>(null);
  const [availableEmb, setAvailableEmb] = useState<any[]>([]);
  const [embLoading, setEmbLoading] = useState(true);

  // ── Add provider form ────────────────────────────────────────────────
  const [showAddForm, setShowAddForm] = useState(false);
  const [newProvider, setNewProvider] = useState<LLMProvider>("ollama");
  const [newName, setNewName] = useState("");
  const [newApiKeyEnvVar, setNewApiKeyEnvVar] = useState("");
  const [newBaseUrl, setNewBaseUrl] = useState("");
  const [newModel, setNewModel] = useState("");
  const [saving, setSaving] = useState(false);

  // ── Connection test ──────────────────────────────────────────────────
  const [testResult, setTestResult] = useState<ConnectionTestResult | null>(null);
  const [testing, setTesting] = useState(false);
  const [testProvider, setTestProvider] = useState<LLMProvider>("ollama");
  const [testApiKeyEnvVar, setTestApiKeyEnvVar] = useState("");
  const [testBaseUrl, setTestBaseUrl] = useState("");
  const [testModel, setTestModel] = useState("");

  // ── Embedding form ───────────────────────────────────────────────────
  const [embProvider, setEmbProvider] = useState<EmbeddingProvider>("local");
  const [embApiKeyEnvVar, setEmbApiKeyEnvVar] = useState("");
  const [embBaseUrl, setEmbBaseUrl] = useState("");
  const [embModel, setEmbModel] = useState("");
  const [embDim, setEmbDim] = useState(0);
  const [embSaving, setEmbSaving] = useState(false);
  const [embMessage, setEmbMessage] = useState("");

  // 원래 임베딩 프로바이더 (변경 감지용)
  const [originalEmbProvider, setOriginalEmbProvider] = useState<string>("local");

  // ── Reranker ─────────────────────────────────────────────────────────
  const [reranker, setReranker] = useState<RerankerConfig>({
    enabled: true,
    model: "BAAI/bge-reranker-v2-m3",
    min_score: 0,
  });
  const [rerankerSaving, setRerankerSaving] = useState(false);
  const [rerankerMessage, setRerankerMessage] = useState("");

  // ── OCR ──────────────────────────────────────────────────────────────
  const [ocr, setOcr] = useState({
    provider: "surya" as "surya" | "tesseract" | "none",
    languages: ["ko", "en"],
    dpi: 200,
    maxPages: 500,
    enableTable: true,
  });
  const [ocrSaving, setOcrSaving] = useState(false);
  const [ocrMessage, setOcrMessage] = useState("");

  // ── Load data ────────────────────────────────────────────────────────
  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLlmLoading(true);
    setEmbLoading(true);
    try {
      const [llmRes, availRes, embRes, availEmbRes, rerankerRes, ocrRes] = await Promise.all([
        listLLMProviders(),
        listAvailableLLMProviders(),
        getEmbeddingProvider(),
        listAvailableEmbeddingProviders(),
        getRerankerConfig(),
        getOcrConfig(),
      ]);
      setProviders(llmRes.providers);
      setActiveId(llmRes.active_id);
      setAvailableLLM(availRes.providers);
      setEmbedding(embRes);
      setEmbProvider(embRes.provider);
      setEmbApiKeyEnvVar(embRes.api_key_env_var || "");
      setEmbBaseUrl(embRes.base_url);
      setEmbModel(embRes.model);
      setEmbDim(embRes.dim);
      setOriginalEmbProvider(embRes.provider);
      setAvailableEmb(availEmbRes.providers);
      setReranker(rerankerRes);
      setOcr({
        provider: ocrRes.provider as "surya" | "tesseract" | "none",
        languages: ocrRes.languages,
        dpi: ocrRes.dpi,
        maxPages: ocrRes.max_pages,
        enableTable: ocrRes.enable_table,
      });
    } catch (e) {
      console.error("설정 로드 실패:", e);
    } finally {
      setLlmLoading(false);
      setEmbLoading(false);
    }
  }

  // ── LLM Provider actions ─────────────────────────────────────────────
  async function handleActivate(id: string) {
    try {
      const updated = await activateLLMProvider(id);
      setProviders((prev) =>
        prev.map((p) => ({ ...p, is_active: p.id === id }))
      );
      setActiveId(id);
    } catch (e: any) {
      alert("활성화 실패: " + e.message);
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("이 프로바이더를 삭제하시겠습니까?")) return;
    try {
      await deleteLLMProvider(id);
      setProviders((prev) => prev.filter((p) => p.id !== id));
      if (activeId === id) setActiveId(null);
    } catch (e: any) {
      alert("삭제 실패: " + e.message);
    }
  }

  async function handleAddProvider() {
    setSaving(true);
    try {
      const created = await createLLMProvider({
        provider: newProvider,
        name: newName || undefined,
        api_key_env_var: newApiKeyEnvVar || undefined,
        base_url: newBaseUrl || undefined,
        model: newModel || undefined,
        is_active: providers.length === 0,
      });
      setProviders((prev) => [...prev, created]);
      if (created.is_active) setActiveId(created.id);
      setShowAddForm(false);
      setNewProvider("ollama");
      setNewName("");
      setNewApiKeyEnvVar("");
      setNewBaseUrl("");
      setNewModel("");
    } catch (e: any) {
      alert("추가 실패: " + e.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleTestConnection() {
    setTesting(true);
    setTestResult(null);
    try {
      const result = await testProviderConnection({
        provider: testProvider,
        api_key_env_var: testApiKeyEnvVar || undefined,
        base_url: testBaseUrl || undefined,
        model: testModel || undefined,
      });
      setTestResult(result);
    } catch (e: any) {
      setTestResult({ success: false, message: e.message });
    } finally {
      setTesting(false);
    }
  }

  // ── Embedding actions ────────────────────────────────────────────────
  async function handleSaveEmbedding() {
    setEmbSaving(true);
    setEmbMessage("");
    try {
      const updated = await updateEmbeddingProvider({
        provider: embProvider,
        api_key_env_var: embApiKeyEnvVar || undefined,
        base_url: embBaseUrl || undefined,
        model: embModel || undefined,
        dim: embDim || 0,
      });
      setEmbedding(updated);
      setOriginalEmbProvider(embProvider);
      setEmbApiKeyEnvVar("");
      setEmbMessage("✅ 임베딩 설정 저장 완료 — 프로바이더가 전환되었습니다.");
      setTimeout(() => setEmbMessage(""), 5000);
    } catch (e: any) {
      setEmbMessage("❌ 저장 실패: " + e.message);
    } finally {
      setEmbSaving(false);
    }
  }

  // ── Reranker save ────────────────────────────────────────────────────
  async function handleSaveReranker() {
    setRerankerSaving(true);
    setRerankerMessage("");
    try {
      const result = await updateRerankerConfig({
        enabled: reranker.enabled,
        model: reranker.model || undefined,
        min_score: reranker.min_score,
      });
      setReranker({ enabled: result.enabled, model: result.model, min_score: result.min_score });
      setRerankerMessage("✅ 리랭커 설정 저장 완료");
      setTimeout(() => setRerankerMessage(""), 5000);
    } catch (e: any) {
      setRerankerMessage("❌ 저장 실패: " + e.message);
    } finally {
      setRerankerSaving(false);
    }
  }

  // ── When embedding provider changes, load defaults ───────────────────
  function handleEmbProviderChange(provider: EmbeddingProvider) {
    setEmbProvider(provider);
    const defaults = availableEmb.find((p) => p.provider === provider);
    if (defaults) {
      setEmbBaseUrl(defaults.default_base_url || "");
      setEmbModel(defaults.default_model || "");
      setEmbDim(defaults.default_dim || 0);
    }
  }

  // ── When test provider changes, load defaults ────────────────────────
  function handleTestProviderChange(provider: LLMProvider) {
    setTestProvider(provider);
    const defaults = availableLLM.find((p) => p.provider === provider);
    if (defaults) {
      setTestBaseUrl(defaults.default_base_url || "");
      setTestModel(defaults.default_model || "");
    }
  }

  // 프로바이더 변경 여부
  const embProviderChanged = embProvider !== originalEmbProvider;

  // 현재 선택된 임베딩 프로바이더의 정보
  const selectedEmbDefaults = availableEmb.find((p) => p.provider === embProvider);
  const requiresApiKey = selectedEmbDefaults?.requires_api_key ?? false;

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 py-6 space-y-8">
      <h1 className="text-2xl font-bold">⚙️ 설정</h1>

      {/* ── 임베딩 프로바이더 (상단으로 이동 — 가장 중요) ────────────── */}
      <section>
        <h2 className="text-lg sm:text-xl font-semibold mb-4">🧬 임베딩 프로바이더</h2>
        {embLoading ? (
          <p className="text-gray-500">로딩 중...</p>
        ) : (
          <div className="space-y-4">
            {/* 현재 선택된 프로바이더 표시 */}
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-medium text-gray-600">현재:</span>
              <span className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded-full text-sm font-medium">
                <span>{EMBEDDING_ICONS[embedding?.provider || "local"] || "📌"}</span>
                {EMBEDDING_LABELS[embedding?.provider || "local"] || embedding?.provider}
              </span>
              {embedding?.model && (
                <span className="text-sm text-gray-500">({embedding.model})</span>
              )}
              {(embedding?.dim ?? 0) > 0 && (
                <span className="text-xs text-gray-400">{embedding!.dim}차원</span>
              )}
            </div>

            {/* 프로바이더 선택 */}
            <div className="p-4 sm:p-5 border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 space-y-4">
              <div>
                <label className="block text-sm font-medium mb-1.5">임베딩 모델 선택</label>
                <select
                  value={embProvider}
                  onChange={(e) => handleEmbProviderChange(e.target.value as EmbeddingProvider)}
                  className="w-full px-3 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-700 dark:text-gray-200 min-h-[44px]"
                >
                  {availableEmb.map((p) => (
                    <option key={p.provider} value={p.provider}>
                      {EMBEDDING_ICONS[p.provider] || "📌"} {EMBEDDING_LABELS[p.provider] || p.provider} — {p.description}
                    </option>
                  ))}
                </select>
              </div>

              {/* 선택된 프로바이더 정보 */}
              {selectedEmbDefaults && (
                <div className="flex flex-wrap gap-2 text-xs">
                  {selectedEmbDefaults.default_dim > 0 && (
                    <span className="px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded">
                      {selectedEmbDefaults.default_dim}차원
                    </span>
                  )}
                  <span className={`px-2 py-1 rounded ${
                    requiresApiKey
                      ? "bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300"
                      : "bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300"
                  }`}>
                    {requiresApiKey ? "🔑 API 키 필요" : "✅ API 키 불필요"}
                  </span>
                  {embProvider === "local" && (
                    <span className="px-2 py-1 bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 rounded">
                      dense + sparse
                    </span>
                  )}
                  {embProvider !== "local" && (
                    <span className="px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded">
                      dense only (sparse → BM25)
                    </span>
                  )}
                </div>
              )}

              {/* 프로바이더 변경 경고 */}
              {embProviderChanged && (
                <div className="p-3 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700 rounded-lg">
                  <p className="text-sm text-amber-800 dark:text-amber-200">{EMBEDDING_CHANGE_WARNING}</p>
                </div>
              )}

              {/* API 키 + 설정 (local이 아닌 경우) */}
              {embProvider !== "local" && (
                <div className="space-y-3">
                  {requiresApiKey && (
                    <div>
                      <label className="block text-sm font-medium mb-1.5">
                        API 키 환경변수명 <span className="text-red-500">*</span>
                      </label>
                      <input
                        type="text"
                        value={embApiKeyEnvVar}
                        onChange={(e) => setEmbApiKeyEnvVar(e.target.value)}
                        placeholder={
                          embedding?.api_key_status?.is_set
                            ? `환경변수 설정됨 (${embedding.api_key_status.masked})`
                            : "환경변수명 입력 (예: OPENAI_API_KEY)"
                        }
                        className="w-full px-3 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-700 dark:text-gray-200 min-h-[44px]"
                      />
                      <p className="text-xs text-gray-400 mt-1">
                        서버에 설정된 환경변수명을 입력하세요 (예: OPENAI_API_KEY)
                      </p>
                    </div>
                  )}

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                      <label className="block text-sm font-medium mb-1.5">Base URL</label>
                      <input
                        type="text"
                        value={embBaseUrl}
                        onChange={(e) => setEmbBaseUrl(e.target.value)}
                        placeholder="프로바이더 기본 URL 사용 시 빈칸"
                        className="w-full px-3 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-700 dark:text-gray-200 min-h-[44px]"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium mb-1.5">모델명</label>
                      <input
                        type="text"
                        value={embModel}
                        onChange={(e) => setEmbModel(e.target.value)}
                        placeholder="프로바이더 기본 모델 사용 시 빈칸"
                        className="w-full px-3 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-700 dark:text-gray-200 min-h-[44px]"
                      />
                    </div>
                  </div>

                  {embDim > 0 && (
                    <div>
                      <label className="block text-sm font-medium mb-1.5">임베딩 차원</label>
                      <input
                        type="number"
                        value={embDim}
                        onChange={(e) => setEmbDim(Number(e.target.value))}
                        className="w-full px-3 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-700 dark:text-gray-200 min-h-[44px]"
                      />
                    </div>
                  )}
                </div>
              )}

              {/* 로컬 bge-m3 설명 */}
              {embProvider === "local" && (
                <div className="p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-700 rounded-lg">
                  <p className="text-sm text-blue-800 dark:text-blue-200">
                    🏠 <strong>bge-m3</strong> — 로컬에서 실행되는 다국어 임베딩 모델입니다.
                    dense(1024차원) + sparse 벡터를 모두 생성하여 하이브리드 검색(RRF)을 지원합니다.
                    별도 API 키가 필요하지 않습니다.
                  </p>
                </div>
              )}

              <div className="flex flex-wrap items-center gap-3">
                <button
                  onClick={handleSaveEmbedding}
                  disabled={embSaving || (requiresApiKey && !embApiKeyEnvVar && !(embedding?.api_key_status?.is_set))}
                  className="px-5 py-2.5 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors text-sm disabled:opacity-50 min-h-[44px]"
                >
                  {embSaving ? "저장 중..." : "💾 임베딩 설정 저장"}
                </button>
                {embMessage && (
                  <span className={`text-sm ${embMessage.startsWith("✅") ? "text-green-600" : "text-red-600"}`}>
                    {embMessage}
                  </span>
                )}
              </div>
            </div>
          </div>
        )}
      </section>

      {/* ── LLM 프로바이더 ──────────────────────────────────────────────── */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg sm:text-xl font-semibold">🔗 LLM 프로바이더</h2>
          <button
            onClick={() => setShowAddForm(!showAddForm)}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm min-h-[44px]"
          >
            {showAddForm ? "취소" : "+ 추가"}
          </button>
        </div>

        {/* Provider list */}
        {llmLoading ? (
          <p className="text-gray-500">로딩 중...</p>
        ) : (
          <div className="space-y-3">
            {providers.map((p) => (
              <div
                key={p.id}
                className={`p-3 sm:p-4 rounded-lg border ${
                  p.is_active
                    ? "border-blue-500 bg-blue-50 dark:bg-blue-900/20 dark:border-blue-600"
                    : "border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800"
                }`}
              >
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                  <div className="flex items-center gap-3">
                    <span className="text-xl">
                      {PROVIDER_ICONS[p.provider] || "🔌"}
                    </span>
                    <div className="min-w-0">
                      <div className="font-medium truncate">
                        {p.name || p.display_name}
                        {p.is_active && (
                          <span className="ml-2 text-xs bg-blue-600 text-white px-2 py-0.5 rounded-full">
                            활성
                          </span>
                        )}
                      </div>
                      <div className="text-sm text-gray-500 dark:text-gray-400 truncate">
                        {p.effective_model} · {p.effective_base_url}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {!p.is_active && (
                      <button
                        onClick={() => handleActivate(p.id)}
                        className="px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded hover:bg-gray-100 dark:hover:bg-gray-700 min-h-[44px]"
                      >
                        활성화
                      </button>
                    )}
                    <button
                      onClick={() => setEditingKeyId(editingKeyId === p.id ? null : p.id)}
                      className="px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded hover:bg-gray-100 dark:hover:bg-gray-700 min-h-[44px]"
                      title="API 키 편집"
                    >
                      🔑
                    </button>
                    <button
                      onClick={() => handleDelete(p.id)}
                      className="px-3 py-1.5 text-sm text-red-600 border border-red-200 dark:border-red-700 rounded hover:bg-red-50 dark:hover:bg-red-900/20 min-h-[44px]"
                    >
                      삭제
                    </button>
                  </div>
                </div>
                {/* API 키 인라인 편집 */}
                {editingKeyId === p.id && (
                  <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700">
                    <label className="block text-sm font-medium mb-1.5">API 키 환경변수명</label>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={editApiKeyEnvVar}
                        onChange={(e) => setEditApiKeyEnvVar(e.target.value)}
                        placeholder={p.api_key_status?.is_set ? `설정됨 (${p.api_key_status.masked}) — 변경하려면 새 환경변수명 입력` : "환경변수명 입력 (예: OLLAMA_CLOUD_API_KEY)"}
                        className="flex-1 px-3 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-700 dark:text-gray-200 min-h-[44px]"
                      />
                      <button
                        onClick={async () => {
                          await updateLLMProvider(p.id, { api_key_env_var: editApiKeyEnvVar || undefined });
                          setEditingKeyId(null);
                          setEditApiKeyEnvVar("");
                          // 설정 다시 로드
                          const [llmRes] = await Promise.all([listLLMProviders()]);
                          setProviders(llmRes.providers);
                        }}
                        className="px-4 py-2.5 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 min-h-[44px] shrink-0"
                      >
                        저장
                      </button>
                      <button
                        onClick={() => { setEditingKeyId(null); setEditApiKeyEnvVar(""); }}
                        className="px-3 py-2.5 text-sm border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 min-h-[44px] shrink-0"
                      >
                        취소
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ))}
            {providers.length === 0 && (
              <p className="text-gray-500 text-center py-8">
                등록된 프로바이더가 없습니다. 추가해주세요.
              </p>
            )}
          </div>
        )}

        {/* Add form */}
        {showAddForm && (
          <div className="mt-4 p-4 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-800 space-y-3">
            <h3 className="font-semibold">새 프로바이더 추가</h3>

            <div>
              <label className="block text-sm font-medium mb-1.5">프로바이더</label>
              <select
                value={newProvider}
                onChange={(e) => setNewProvider(e.target.value as LLMProvider)}
                className="w-full px-3 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-700 dark:text-gray-200 min-h-[44px]"
              >
                {availableLLM.map((p) => (
                  <option key={p.provider} value={p.provider}>
                    {PROVIDER_ICONS[p.provider] || ""} {PROVIDER_LABELS[p.provider] || p.provider}
                  </option>
                ))}
              </select>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium mb-1.5">이름 (선택)</label>
                <input
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="예: Ollama Cloud"
                  className="w-full px-3 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-700 dark:text-gray-200 min-h-[44px]"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1.5">API 키 환경변수명</label>
                <input
                  type="text"
                  value={newApiKeyEnvVar}
                  onChange={(e) => setNewApiKeyEnvVar(e.target.value)}
                  placeholder="예: OPENAI_API_KEY (빈값 → 기본 환경변수)"
                  className="w-full px-3 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-700 dark:text-gray-200 min-h-[44px]"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium mb-1.5">Base URL (선택)</label>
                <input
                  type="text"
                  value={newBaseUrl}
                  onChange={(e) => setNewBaseUrl(e.target.value)}
                  placeholder="빈값 → 기본 URL 사용"
                  className="w-full px-3 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-700 dark:text-gray-200 min-h-[44px]"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1.5">모델 (선택)</label>
                <input
                  type="text"
                  value={newModel}
                  onChange={(e) => setNewModel(e.target.value)}
                  placeholder="빈값 → 기본 모델 사용"
                  className="w-full px-3 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-700 dark:text-gray-200 min-h-[44px]"
                />
              </div>
            </div>

            <button
              onClick={handleAddProvider}
              disabled={saving}
              className="w-full py-2.5 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors text-sm disabled:opacity-50 min-h-[44px]"
            >
              {saving ? "저장 중..." : "추가"}
            </button>
          </div>
        )}
      </section>

      {/* ── 연결 테스트 ──────────────────────────────────────────────────── */}
      <section>
        <h2 className="text-lg sm:text-xl font-semibold mb-4">🔍 연결 테스트</h2>
        <div className="p-4 sm:p-5 border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium mb-1.5">프로바이더</label>
              <select
                value={testProvider}
                onChange={(e) => handleTestProviderChange(e.target.value as LLMProvider)}
                className="w-full px-3 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-700 dark:text-gray-200 min-h-[44px]"
              >
                {availableLLM.map((p) => (
                  <option key={p.provider} value={p.provider}>
                    {PROVIDER_LABELS[p.provider] || p.provider}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1.5">API 키 환경변수명 (선택)</label>
              <input
                type="text"
                value={testApiKeyEnvVar}
                onChange={(e) => setTestApiKeyEnvVar(e.target.value)}
                placeholder="예: OLLAMA_CLOUD_API_KEY (빈값 → 기본 환경변수)"
                className="w-full px-3 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-700 dark:text-gray-200 min-h-[44px]"
              />
            </div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium mb-1.5">Base URL</label>
              <input
                type="text"
                value={testBaseUrl}
                onChange={(e) => setTestBaseUrl(e.target.value)}
                className="w-full px-3 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-700 dark:text-gray-200 min-h-[44px]"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1.5">모델</label>
              <input
                type="text"
                value={testModel}
                onChange={(e) => setTestModel(e.target.value)}
                className="w-full px-3 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-700 dark:text-gray-200 min-h-[44px]"
              />
            </div>
          </div>

          <button
            onClick={handleTestConnection}
            disabled={testing}
            className="w-full py-2.5 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors text-sm disabled:opacity-50 min-h-[44px]"
          >
            {testing ? "테스트 중..." : "연결 테스트"}
          </button>

          {testResult && (
            <div
              className={`p-3 rounded-lg text-sm ${
                testResult.success
                  ? "bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-700 text-green-800 dark:text-green-200"
                  : "bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-700 text-red-800 dark:text-red-200"
              }`}
            >
              <p className="font-medium">{testResult.success ? "✅ 성공" : "❌ 실패"}</p>
              <p>{testResult.message}</p>
              {testResult.model_info && (
                <p className="text-xs mt-1">모델: {testResult.model_info}</p>
              )}
              {testResult.response_time_ms && (
                <p className="text-xs">응답 시간: {testResult.response_time_ms}ms</p>
              )}
            </div>
          )}
        </div>
      </section>

      {/* ── 리랭커 설정 ──────────────────────────────────────────────── */}
      <section>
        <h2 className="text-lg sm:text-xl font-semibold mb-4">🎯 리랭커 (Re-ranker)</h2>
        <div className="p-4 sm:p-5 border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 space-y-4">
          {/* 설명 */}
          <div className="p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-700 rounded-lg">
            <p className="text-sm text-blue-800 dark:text-blue-200">
              🔍 <strong>bge-reranker-v2-m3</strong> — 검색 결과를 질문과의 관련성 순으로 재정렬합니다.
              초기 검색에서 더 많은 후보(20~30개)를 가져온 후, 리랭커가 최적의 5~12개만 선별합니다.
              bge-m3 임베딩과 동일 계열로 한국어 성능이 우수합니다.
            </p>
          </div>

          {/* 토글 */}
          <div className="flex items-center justify-between">
            <label className="text-sm font-medium">리랭커 활성화</label>
            <button
              onClick={() => setReranker({ ...reranker, enabled: !reranker.enabled })}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                reranker.enabled ? "bg-blue-600" : "bg-gray-300 dark:bg-gray-600"
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  reranker.enabled ? "translate-x-6" : "translate-x-1"
                }`}
              />
            </button>
          </div>

          {/* 모델명 */}
          <div>
            <label className="block text-sm font-medium mb-1.5">리랭커 모델</label>
            <input
              type="text"
              value={reranker.model}
              onChange={(e) => setReranker({ ...reranker, model: e.target.value })}
              disabled={!reranker.enabled}
              className="w-full px-3 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-700 dark:text-gray-200 min-h-[44px] disabled:opacity-50 disabled:bg-gray-100 dark:disabled:bg-gray-800"
              placeholder="BAAI/bge-reranker-v2-m3"
            />
            <p className="text-xs text-gray-400 mt-1">
              HuggingFace 모델명을 입력하세요. 기본값: BAAI/bge-reranker-v2-m3
            </p>
          </div>

          {/* 최소 점수 */}
          <div>
            <label className="block text-sm font-medium mb-1.5">최소 관련성 점수 (min_score)</label>
            <input
              type="number"
              value={reranker.min_score}
              onChange={(e) => setReranker({ ...reranker, min_score: Number(e.target.value) })}
              disabled={!reranker.enabled}
              step="0.1"
              min="0"
              max="1"
              className="w-full px-3 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-700 dark:text-gray-200 min-h-[44px] disabled:opacity-50 disabled:bg-gray-100 dark:disabled:bg-gray-800"
            />
            <p className="text-xs text-gray-400 mt-1">
              이 점수 미만의 결과는 필터링됩니다 (0 = 필터링 없음, 범위: 0.0~1.0)
            </p>
          </div>

          {/* 모드별 리랭크 설정 안내 */}
          {reranker.enabled && (
            <div className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
              <p className="text-xs font-medium text-gray-600 dark:text-gray-300 mb-2">📋 모드별 리랭크 설정</p>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                <div className="p-2 bg-white dark:bg-gray-800 rounded border">
                  <div className="font-medium">팩트</div>
                  <div className="text-gray-500">20 → 5</div>
                </div>
                <div className="p-2 bg-white dark:bg-gray-800 rounded border">
                  <div className="font-medium">요약</div>
                  <div className="text-gray-500">25 → 8</div>
                </div>
                <div className="p-2 bg-white dark:bg-gray-800 rounded border">
                  <div className="font-medium">컬럼</div>
                  <div className="text-gray-500">30 → 12</div>
                </div>
                <div className="p-2 bg-white dark:bg-gray-800 rounded border">
                  <div className="font-medium">추론</div>
                  <div className="text-gray-500">30 → 10</div>
                </div>
              </div>
              <p className="text-xs text-gray-400 mt-2">초기 후보 수 → 리랭크 후 최종 결과 수</p>
            </div>
          )}

          {/* 저장 버튼 */}
          <div className="flex flex-wrap items-center gap-3">
            <button
              onClick={handleSaveReranker}
              disabled={rerankerSaving}
              className="px-5 py-2.5 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors text-sm disabled:opacity-50 min-h-[44px]"
            >
              {rerankerSaving ? "저장 중..." : "💾 리랭커 설정 저장"}
            </button>
            {rerankerMessage && (
              <span className={`text-sm ${rerankerMessage.startsWith("✅") ? "text-green-600" : "text-red-600"}`}>
                {rerankerMessage}
              </span>
            )}
          </div>
        </div>
      </section>

      {/* ── OCR 설정 ─────────────────────────────────────────────────── */}
      <section>
        <h2 className="text-lg sm:text-xl font-semibold mb-4">📄 OCR (광학 문자 인식)</h2>
        <div className="p-4 sm:p-5 border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 space-y-4">
          {/* 설명 */}
          <div className="p-3 bg-purple-50 dark:bg-purple-900/20 border border-purple-200 dark:border-purple-700 rounded-lg">
            <p className="text-sm text-purple-800 dark:text-purple-200">
              📝 스캔 문서, 이미지 PDF, 법원 판결문 등에서 한국어 텍스트를 추출합니다.
              <strong> surya-ocr</strong>(한국어 고정밀) → <strong>tesseract</strong>(폴백) 순서로 동작합니다.
            </p>
          </div>

          {/* OCR 엔진 선택 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">OCR 엔진</label>
            <select
              value={ocr.provider}
              onChange={(e) => setOcr({ ...ocr, provider: e.target.value as "surya" | "tesseract" | "none" })}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
            >
              <option value="surya">surya-ocr (한국어 고정밀, GPU 가속)</option>
              <option value="tesseract">tesseract (폴백, CPU)</option>
              <option value="none">비활성화</option>
            </select>
          </div>

          {/* DPI 설정 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              렌더링 DPI <span className="text-gray-400">(기본: 200)</span>
            </label>
            <input
              type="number"
              min={72}
              max={600}
              value={ocr.dpi}
              onChange={(e) => setOcr({ ...ocr, dpi: parseInt(e.target.value) || 200 })}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
            />
            <p className="mt-1 text-xs text-gray-500">높을수록 정밀하지만 메모리 사용량 증가 (권장: 150~300)</p>
          </div>

          {/* 최대 페이지 수 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              최대 OCR 페이지 <span className="text-gray-400">(기본: 500)</span>
            </label>
            <input
              type="number"
              min={1}
              max={5000}
              value={ocr.maxPages}
              onChange={(e) => setOcr({ ...ocr, maxPages: parseInt(e.target.value) || 500 })}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
            />
          </div>

          {/* 표 추출 토글 */}
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-700 dark:text-gray-300">표 추출 활성화</p>
              <p className="text-xs text-gray-500">camelot/img2table로 PDF 내 표를 마크다운으로 변환</p>
            </div>
            <button
              onClick={() => setOcr({ ...ocr, enableTable: !ocr.enableTable })}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                ocr.enableTable ? "bg-purple-600" : "bg-gray-300 dark:bg-gray-600"
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  ocr.enableTable ? "translate-x-6" : "translate-x-1"
                }`}
              />
            </button>
          </div>

          {/* OCR 언어 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">인식 언어</label>
            <div className="flex gap-2">
              {ocr.languages.map((lang, i) => (
                <span key={i} className="px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded text-sm">
                  {lang === "ko" ? "🇰🇷 한국어" : lang === "en" ? "🇺🇸 영어" : lang}
                </span>
              ))}
            </div>
            <p className="mt-1 text-xs text-gray-500">surya-ocr은 90+ 언어 지원. 설정에서 변경 가능.</p>
          </div>

          {/* 저장 버튼 */}
          <div className="flex items-center gap-3">
            <button
              onClick={async () => {
                setOcrSaving(true);
                setOcrMessage("");
                try {
                  const result = await updateOcrConfig({
                    provider: ocr.provider,
                    languages: ocr.languages,
                    dpi: ocr.dpi,
                    max_pages: ocr.maxPages,
                    enable_table: ocr.enableTable,
                  });
                  setOcrMessage(`✅ ${result.message}`);
                } catch (e: any) {
                  setOcrMessage(`❌ 저장 실패: ${e.message}`);
                } finally {
                  setOcrSaving(false);
                }
              }}
              disabled={ocrSaving}
              className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50"
            >
              {ocrSaving ? "저장 중..." : "OCR 설정 저장"}
            </button>
            {ocrMessage && (
              <span className={`text-sm ${ocrMessage.startsWith("✅") ? "text-green-600" : "text-red-600"}`}>
                {ocrMessage}
              </span>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}