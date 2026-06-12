"use client";

import { useState, useEffect, useCallback } from "react";
import {
  ApiKeyResponse,
  ApiKeyCreateResponse,
  listApiKeys,
  createApiKey,
  rotateApiKey,
  deactivateApiKey,
  deleteApiKey,
} from "../../../lib/api";

// ── API 키 관리 페이지 ──────────────────────────────────────────────────────

export default function ApiKeysPage() {
  const [keys, setKeys] = useState<ApiKeyResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 키 생성 폼
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [newRateLimit, setNewRateLimit] = useState(60);
  const [creating, setCreating] = useState(false);

  // 생성된 키 표시 (1회만)
  const [createdKey, setCreatedKey] = useState<ApiKeyCreateResponse | null>(null);

  // 회전/비활성화 로딩
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const fetchKeys = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await listApiKeys();
      setKeys(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "API 키 목록을 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchKeys();
  }, [fetchKeys]);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    try {
      setCreating(true);
      const result = await createApiKey({
        name: newName.trim(),
        description: newDesc.trim() || undefined,
        rate_limit: newRateLimit,
      });
      setCreatedKey(result);
      setNewName("");
      setNewDesc("");
      setNewRateLimit(60);
      await fetchKeys();
    } catch (err) {
      setError(err instanceof Error ? err.message : "API 키 생성에 실패했습니다.");
    } finally {
      setCreating(false);
    }
  };

  const handleRotate = async (keyId: string) => {
    if (!confirm("키를 회전하시겠습니까? 기존 키는 즉시 비활성화되고 새 키가 발급됩니다.")) return;
    try {
      setActionLoading(keyId);
      const result = await rotateApiKey(keyId);
      setCreatedKey(result);
      await fetchKeys();
    } catch (err) {
      setError(err instanceof Error ? err.message : "키 회전에 실패했습니다.");
    } finally {
      setActionLoading(null);
    }
  };

  const handleDeactivate = async (keyId: string) => {
    if (!confirm("이 키를 비활성화하시겠습니까? 비활성화된 키로는 API를 호출할 수 없습니다.")) return;
    try {
      setActionLoading(keyId);
      await deactivateApiKey(keyId);
      await fetchKeys();
    } catch (err) {
      setError(err instanceof Error ? err.message : "비활성화에 실패했습니다.");
    } finally {
      setActionLoading(null);
    }
  };

  const handleDelete = async (keyId: string) => {
    if (!confirm("이 키를 완전히 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.")) return;
    try {
      setActionLoading(keyId);
      await deleteApiKey(keyId);
      await fetchKeys();
    } catch (err) {
      setError(err instanceof Error ? err.message : "삭제에 실패했습니다.");
    } finally {
      setActionLoading(null);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text).then(() => {
      alert("클립보드에 복사되었습니다.");
    });
  };

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 p-6">
      <div className="max-w-4xl mx-auto">
        {/* 헤더 */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
              🔑 API 키 관리
            </h1>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              외부 서비스 연동을 위한 API 키를 발급하고 관리합니다.
            </p>
          </div>
          <button
            onClick={() => setShowCreate(!showCreate)}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-medium"
          >
            + 새 키 발급
          </button>
        </div>

        {/* 에러 메시지 */}
        {error && (
          <div className="mb-4 p-4 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-lg text-red-700 dark:text-red-300 text-sm">
            {error}
            <button
              onClick={() => setError(null)}
              className="float-right font-bold"
            >
              ✕
            </button>
          </div>
        )}

        {/* 생성된 키 표시 (1회만) */}
        {createdKey && (
          <div className="mb-6 p-4 bg-green-50 dark:bg-green-900/30 border border-green-200 dark:border-green-800 rounded-lg">
            <h3 className="font-semibold text-green-800 dark:text-green-200 mb-2">
              ✅ API 키가 발급되었습니다
            </h3>
            <p className="text-sm text-green-700 dark:text-green-300 mb-2">
              아래 키를 안전한 곳에 보관하세요. 이 키는 다시 표시되지 않습니다.
            </p>
            <div className="flex items-center gap-2">
              <code className="flex-1 p-3 bg-white dark:bg-gray-800 rounded border border-green-300 dark:border-green-700 text-sm font-mono break-all select-all">
                {createdKey.api_key}
              </code>
              <button
                onClick={() => copyToClipboard(createdKey.api_key)}
                className="px-3 py-2 bg-green-600 text-white rounded hover:bg-green-700 text-sm font-medium whitespace-nowrap"
              >
                📋 복사
              </button>
            </div>
            <div className="mt-2 text-xs text-green-600 dark:text-green-400">
              키 접두사: {createdKey.key_prefix} | 분당 제한: {createdKey.rate_limit}회
            </div>
            <button
              onClick={() => setCreatedKey(null)}
              className="mt-3 text-sm text-green-700 dark:text-green-300 underline"
            >
              닫기
            </button>
          </div>
        )}

        {/* 키 생성 폼 */}
        {showCreate && (
          <div className="mb-6 p-5 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-sm">
            <h3 className="font-semibold text-gray-900 dark:text-white mb-4">
              새 API 키 발급
            </h3>
            <div className="space-y-3">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  이름 *
                </label>
                <input
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="예: 홈페이지 챗봇, 파트너 API"
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  설명 (선택)
                </label>
                <input
                  type="text"
                  value={newDesc}
                  onChange={(e) => setNewDesc(e.target.value)}
                  placeholder="키 용도 설명"
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  분당 요청 제한 (rate_limit)
                </label>
                <input
                  type="number"
                  value={newRateLimit}
                  onChange={(e) => setNewRateLimit(parseInt(e.target.value) || 60)}
                  min={1}
                  className="w-32 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:outline-none"
                />
              </div>
              <div className="flex gap-2">
                <button
                  onClick={handleCreate}
                  disabled={!newName.trim() || creating}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium"
                >
                  {creating ? "발급 중..." : "발급"}
                </button>
                <button
                  onClick={() => { setShowCreate(false); setNewName(""); setNewDesc(""); }}
                  className="px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 font-medium"
                >
                  취소
                </button>
              </div>
            </div>
          </div>
        )}

        {/* 키 목록 */}
        {loading ? (
          <div className="text-center py-12 text-gray-500 dark:text-gray-400">
            로딩 중...
          </div>
        ) : keys.length === 0 ? (
          <div className="text-center py-12 text-gray-500 dark:text-gray-400">
            아직 발급된 API 키가 없습니다. &ldquo;+ 새 키 발급&rdquo; 버튼으로 시작하세요.
          </div>
        ) : (
          <div className="space-y-3">
            {keys.map((key) => (
              <div
                key={key.id}
                className={`p-4 bg-white dark:bg-gray-800 border rounded-lg shadow-sm ${
                  key.is_active
                    ? "border-gray-200 dark:border-gray-700"
                    : "border-gray-300 dark:border-gray-600 opacity-60"
                }`}
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <h4 className="font-medium text-gray-900 dark:text-white">
                        {key.name}
                      </h4>
                      <span
                        className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                          key.is_active
                            ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
                            : "bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400"
                        }`}
                      >
                        {key.is_active ? "활성" : "비활성"}
                      </span>
                    </div>
                    <div className="mt-1 text-sm text-gray-500 dark:text-gray-400 space-y-0.5">
                      <div>접두사: <code className="font-mono">{key.key_prefix}</code></div>
                      {key.description && <div>설명: {key.description}</div>}
                      <div>
                        분당 제한: {key.rate_limit}회 |
                        사용 횟수: {key.usage_count}회 |
                        생성: {new Date(key.created_at).toLocaleString("ko-KR")}
                      </div>
                      {key.last_used_at && (
                        <div>마지막 사용: {new Date(key.last_used_at).toLocaleString("ko-KR")}</div>
                      )}
                    </div>
                  </div>

                  {key.is_active && (
                    <div className="flex gap-2 ml-4">
                      <button
                        onClick={() => handleRotate(key.id)}
                        disabled={actionLoading === key.id}
                        className="px-3 py-1.5 text-sm border border-yellow-500 text-yellow-700 dark:text-yellow-400 rounded hover:bg-yellow-50 dark:hover:bg-yellow-900/30 disabled:opacity-50"
                      >
                        🔄 회전
                      </button>
                      <button
                        onClick={() => handleDeactivate(key.id)}
                        disabled={actionLoading === key.id}
                        className="px-3 py-1.5 text-sm border border-orange-500 text-orange-700 dark:text-orange-400 rounded hover:bg-orange-50 dark:hover:bg-orange-900/30 disabled:opacity-50"
                      >
                        ⏸ 비활성화
                      </button>
                      <button
                        onClick={() => handleDelete(key.id)}
                        className="px-3 py-1.5 text-sm border border-red-500 text-red-700 dark:text-red-400 rounded hover:bg-red-50 dark:hover:bg-red-900/30"
                      >
                        🗑 삭제
                      </button>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* API 사용 안내 */}
        <div className="mt-8 p-5 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
          <h3 className="font-semibold text-blue-800 dark:text-blue-200 mb-2">
            📖 OpenAPI 사용 안내
          </h3>
          <div className="text-sm text-blue-700 dark:text-blue-300 space-y-2">
            <p>발급받은 API 키로 외부 서비스에서 mAI-Brain 챗봇 API를 호출할 수 있습니다.</p>
            <div className="bg-white dark:bg-gray-800 p-3 rounded border border-blue-200 dark:border-blue-700 font-mono text-xs">
              <div className="text-gray-500 mb-1"># 채팅 요청 예시</div>
              <div>curl -X POST https://your-domain.com/api/v1/chat \</div>
              <div>  -H &quot;Content-Type: application/json&quot; \</div>
              <div>  -H &quot;X-API-Key: mai_您的키값&quot; \</div>
              <div>  -d &#123;&quot;question&quot;: &quot;질문 내용&quot;, &quot;mode&quot;: &quot;fact&quot;&#125;</div>
            </div>
            <div className="bg-white dark:bg-gray-800 p-3 rounded border border-blue-200 dark:border-blue-700 font-mono text-xs">
              <div className="text-gray-500 mb-1"># 모드 목록 조회</div>
              <div>curl -H &quot;X-API-Key: mai_您的키값&quot; https://your-domain.com/api/v1/modes</div>
            </div>
            <p className="text-xs text-blue-600 dark:text-blue-400 mt-2">
              사용 가능한 모드: fact(팩트), summary(요약), column(컬럼), reasoning(추론), creative(창의적 대화)
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}