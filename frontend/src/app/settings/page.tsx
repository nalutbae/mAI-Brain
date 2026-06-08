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
  type LLMProvider,
  type EmbeddingProvider,
  type LLMProviderConfig,
  type EmbeddingConfig,
  type ProviderDefaults,
  type ConnectionTestResult,
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

const EMBEDDING_LABELS: Record<string, string> = {
  local: "bge-m3 (로컬)",
  openai: "OpenAI",
  jina: "Jina AI",
  ollama: "Ollama",
  cohere: "Cohere",
};

export default function SettingsPage() {
  // ── LLM providers ────────────────────────────────────────────────────
  const [providers, setProviders] = useState<LLMProviderConfig[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [availableLLM, setAvailableLLM] = useState<ProviderDefaults[]>([]);
  const [llmLoading, setLlmLoading] = useState(true);

  // ── Embedding ────────────────────────────────────────────────────────
  const [embedding, setEmbedding] = useState<EmbeddingConfig | null>(null);
  const [availableEmb, setAvailableEmb] = useState<any[]>([]);
  const [embLoading, setEmbLoading] = useState(true);

  // ── Add provider form ────────────────────────────────────────────────
  const [showAddForm, setShowAddForm] = useState(false);
  const [newProvider, setNewProvider] = useState<LLMProvider>("ollama");
  const [newName, setNewName] = useState("");
  const [newApiKey, setNewApiKey] = useState("");
  const [newBaseUrl, setNewBaseUrl] = useState("");
  const [newModel, setNewModel] = useState("");
  const [saving, setSaving] = useState(false);

  // ── Connection test ──────────────────────────────────────────────────
  const [testResult, setTestResult] = useState<ConnectionTestResult | null>(null);
  const [testing, setTesting] = useState(false);
  const [testProvider, setTestProvider] = useState<LLMProvider>("ollama");
  const [testApiKey, setTestApiKey] = useState("");
  const [testBaseUrl, setTestBaseUrl] = useState("");
  const [testModel, setTestModel] = useState("");

  // ── Embedding form ───────────────────────────────────────────────────
  const [embProvider, setEmbProvider] = useState<EmbeddingProvider>("local");
  const [embApiKey, setEmbApiKey] = useState("");
  const [embBaseUrl, setEmbBaseUrl] = useState("");
  const [embModel, setEmbModel] = useState("");
  const [embDim, setEmbDim] = useState(0);
  const [embSaving, setEmbSaving] = useState(false);
  const [embMessage, setEmbMessage] = useState("");

  // ── Load data ────────────────────────────────────────────────────────
  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLlmLoading(true);
    setEmbLoading(true);
    try {
      const [llmRes, availRes, embRes, availEmbRes] = await Promise.all([
        listLLMProviders(),
        listAvailableLLMProviders(),
        getEmbeddingProvider(),
        listAvailableEmbeddingProviders(),
      ]);
      setProviders(llmRes.providers);
      setActiveId(llmRes.active_id);
      setAvailableLLM(availRes.providers);
      setEmbedding(embRes);
      setEmbProvider(embRes.provider);
      setEmbApiKey("");
      setEmbBaseUrl(embRes.base_url);
      setEmbModel(embRes.model);
      setEmbDim(embRes.dim);
      setAvailableEmb(availEmbRes.providers);
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
        api_key: newApiKey || undefined,
        base_url: newBaseUrl || undefined,
        model: newModel || undefined,
        is_active: providers.length === 0,
      });
      setProviders((prev) => [...prev, created]);
      if (created.is_active) setActiveId(created.id);
      setShowAddForm(false);
      setNewProvider("ollama");
      setNewName("");
      setNewApiKey("");
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
        api_key: testApiKey || undefined,
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
        api_key: embApiKey || undefined,
        base_url: embBaseUrl || undefined,
        model: embModel || undefined,
        dim: embDim || 0,
      });
      setEmbedding(updated);
      setEmbApiKey("");
      setEmbMessage("✅ 임베딩 설정 저장 완료");
      setTimeout(() => setEmbMessage(""), 3000);
    } catch (e: any) {
      setEmbMessage("❌ 저장 실패: " + e.message);
    } finally {
      setEmbSaving(false);
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

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-8">
      <h1 className="text-2xl font-bold">⚙️ 설정</h1>

      {/* ── LLM 프로바이더 ──────────────────────────────────────────────── */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold">🔗 LLM 프로바이더</h2>
          <button
            onClick={() => setShowAddForm(!showAddForm)}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm"
          >
            {showAddForm ? "취소" : "+ 프로바이더 추가"}
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
                className={`p-4 rounded-lg border ${
                  p.is_active
                    ? "border-blue-500 bg-blue-50"
                    : "border-gray-200 bg-white"
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <span className="text-xl">
                      {PROVIDER_ICONS[p.provider] || "🔌"}
                    </span>
                    <div>
                      <div className="font-medium">
                        {p.name || p.display_name}
                        {p.is_active && (
                          <span className="ml-2 text-xs bg-blue-600 text-white px-2 py-0.5 rounded-full">
                            활성
                          </span>
                        )}
                      </div>
                      <div className="text-sm text-gray-500">
                        {p.effective_model} · {p.effective_base_url}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {!p.is_active && (
                      <button
                        onClick={() => handleActivate(p.id)}
                        className="px-3 py-1 text-sm border border-gray-300 rounded hover:bg-gray-100"
                      >
                        활성화
                      </button>
                    )}
                    <button
                      onClick={() => handleDelete(p.id)}
                      className="px-3 py-1 text-sm text-red-600 border border-red-200 rounded hover:bg-red-50"
                    >
                      삭제
                    </button>
                  </div>
                </div>
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
          <div className="mt-4 p-4 border border-gray-300 rounded-lg bg-gray-50 space-y-3">
            <h3 className="font-semibold">새 프로바이더 추가</h3>

            <div>
              <label className="block text-sm font-medium mb-1">프로바이더</label>
              <select
                value={newProvider}
                onChange={(e) => setNewProvider(e.target.value as LLMProvider)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
              >
                {availableLLM.map((p) => (
                  <option key={p.provider} value={p.provider}>
                    {PROVIDER_ICONS[p.provider] || ""} {PROVIDER_LABELS[p.provider] || p.provider}
                  </option>
                ))}
              </select>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium mb-1">이름 (선택)</label>
                <input
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="예: Ollama Cloud"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">API 키</label>
                <input
                  type="password"
                  value={newApiKey}
                  onChange={(e) => setNewApiKey(e.target.value)}
                  placeholder="필요한 경우에만 입력"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium mb-1">Base URL (선택)</label>
                <input
                  type="text"
                  value={newBaseUrl}
                  onChange={(e) => setNewBaseUrl(e.target.value)}
                  placeholder="빈값 → 기본 URL 사용"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">모델 (선택)</label>
                <input
                  type="text"
                  value={newModel}
                  onChange={(e) => setNewModel(e.target.value)}
                  placeholder="빈값 → 기본 모델 사용"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                />
              </div>
            </div>

            <button
              onClick={handleAddProvider}
              disabled={saving}
              className="w-full py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors text-sm disabled:opacity-50"
            >
              {saving ? "저장 중..." : "추가"}
            </button>
          </div>
        )}
      </section>

      {/* ── 연결 테스트 ──────────────────────────────────────────────────── */}
      <section>
        <h2 className="text-xl font-semibold mb-4">🔍 연결 테스트</h2>
        <div className="p-4 border border-gray-200 rounded-lg space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium mb-1">프로바이더</label>
              <select
                value={testProvider}
                onChange={(e) => handleTestProviderChange(e.target.value as LLMProvider)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
              >
                {availableLLM.map((p) => (
                  <option key={p.provider} value={p.provider}>
                    {PROVIDER_LABELS[p.provider] || p.provider}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">API 키 (선택)</label>
              <input
                type="password"
                value={testApiKey}
                onChange={(e) => setTestApiKey(e.target.value)}
                placeholder="환경변수에 설정된 경우 생략"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium mb-1">Base URL</label>
              <input
                type="text"
                value={testBaseUrl}
                onChange={(e) => setTestBaseUrl(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">모델</label>
              <input
                type="text"
                value={testModel}
                onChange={(e) => setTestModel(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
              />
            </div>
          </div>

          <button
            onClick={handleTestConnection}
            disabled={testing}
            className="w-full py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors text-sm disabled:opacity-50"
          >
            {testing ? "테스트 중..." : "연결 테스트"}
          </button>

          {testResult && (
            <div
              className={`p-3 rounded-lg text-sm ${
                testResult.success
                  ? "bg-green-50 border border-green-200 text-green-800"
                  : "bg-red-50 border border-red-200 text-red-800"
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

      {/* ── 임베딩 프로바이더 ──────────────────────────────────────────── */}
      <section>
        <h2 className="text-xl font-semibold mb-4">🧬 임베딩 프로바이더</h2>
        {embLoading ? (
          <p className="text-gray-500">로딩 중...</p>
        ) : (
          <div className="p-4 border border-gray-200 rounded-lg space-y-3">
            <div className="flex items-center gap-3">
              <span className="text-sm font-medium text-gray-600">현재:</span>
              <span className="px-3 py-1 bg-gray-100 rounded-full text-sm font-medium">
                {EMBEDDING_LABELS[embedding?.provider || "local"] || embedding?.provider}
              </span>
              {embedding?.model && (
                <span className="text-sm text-gray-500">({embedding.model})</span>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">프로바이더</label>
              <select
                value={embProvider}
                onChange={(e) => handleEmbProviderChange(e.target.value as EmbeddingProvider)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
              >
                {availableEmb.map((p) => (
                  <option key={p.provider} value={p.provider}>
                    {EMBEDDING_LABELS[p.provider] || p.provider} — {p.description}
                  </option>
                ))}
              </select>
            </div>

            {embProvider !== "local" && (
              <>
                <div>
                  <label className="block text-sm font-medium mb-1">API 키</label>
                  <input
                    type="password"
                    value={embApiKey}
                    onChange={(e) => setEmbApiKey(e.target.value)}
                    placeholder="빈값 → 환경변수에서 자동 로드"
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                  />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-sm font-medium mb-1">Base URL (선택)</label>
                    <input
                      type="text"
                      value={embBaseUrl}
                      onChange={(e) => setEmbBaseUrl(e.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">모델</label>
                    <input
                      type="text"
                      value={embModel}
                      onChange={(e) => setEmbModel(e.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                    />
                  </div>
                </div>
              </>
            )}

            <div className="flex items-center gap-3">
              <button
                onClick={handleSaveEmbedding}
                disabled={embSaving}
                className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors text-sm disabled:opacity-50"
              >
                {embSaving ? "저장 중..." : "임베딩 저장"}
              </button>
              {embMessage && (
                <span className={`text-sm ${embMessage.startsWith("✅") ? "text-green-600" : "text-red-600"}`}>
                  {embMessage}
                </span>
              )}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
