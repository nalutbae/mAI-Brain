"use client";

import { useEffect, useRef, useState } from "react";
import { useAuth } from "../../../lib/auth";

// ── SDK 코드 (복사용) ──────────────────────────────────────────────────
const SDK_INSTALL_CODE = `<!-- mAI-Brain 서비스 챗봇 SDK -->
<script src="${typeof window !== "undefined" ? window.location.origin : ""}/sdk/maibot-sdk.js" data-api-base="API_BASE_URL"></script>`;

const SDK_INIT_CODE = `<script>
  MaibotSDK.init({
    apiBase: 'API_BASE_URL',  // 예: http://localhost:8000
    primaryColor: '#2563eb',  // 선택: 메인 컬러
    position: 'right',        // 선택: 'right' | 'left'
    offsetBottom: 24,          // 선택: 하단 여백 (px)
    offsetSide: 24,            // 선택: 측면 여백 (px)
  });
</script>`;

export default function SdkDemoPage() {
  const { user, loading, isAdmin } = useAuth();
  const demoRef = useRef<HTMLDivElement>(null);
  const [sdkLoaded, setSdkLoaded] = useState(false);
  const [apiBase, setApiBase] = useState("");
  const [activeTab, setActiveTab] = useState<"preview" | "install">("preview");
  const [copied, setCopied] = useState("");

  useEffect(() => {
    // API 베이스 URL 감지
    const url = process.env.NEXT_PUBLIC_API_URL || "";
    setApiBase(url);
  }, []);

  useEffect(() => {
    // 이미 초기화된 경우 스킵
    if ((window as unknown as Record<string, unknown>).MaibotSDK) {
      setSdkLoaded(true);
      return;
    }

    // API 베이스 URL 결정: 환경변수 또는 현재 origin
    const url = process.env.NEXT_PUBLIC_API_URL || window.location.origin;
    setApiBase(url);

    // SDK 스크립트 동적 로드
    const script = document.createElement("script");
    script.src = "/sdk/maibot-sdk.js";
    script.async = true;
    script.onload = () => {
      const SDK = (window as unknown as Record<string, { init: (opts: Record<string, string>) => Promise<unknown> }>).MaibotSDK;
      if (SDK) {
        // 수동 초기화 — data-api-base 동적 삽입 시 document.currentScript가 null이므로
        SDK.init({ apiBase: url }).then(() => {
          setSdkLoaded(true);
        }).catch((err: unknown) => {
          console.error("[SdkDemo] SDK 초기화 실패:", err);
          setSdkLoaded(false);
        });
      } else {
        console.error("[SdkDemo] MaibotSDK 전역 객체를 찾을 수 없음");
      }
    };
    script.onerror = () => {
      console.error("[SdkDemo] SDK 스크립트 로드 실패 — /sdk/maibot-sdk.js를 확인하세요");
    };
    document.body.appendChild(script);

    // cleanup에서는 SDK를 제거하지 않음 (데모 페이지를 벗어나도 챗봇은 유지)
    return () => {
      // script 태그만 제거, SDK UI는 유지
      script.remove();
    };
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="text-gray-400">로딩 중...</div>
      </div>
    );
  }

  if (!user || !isAdmin) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="text-center">
          <p className="text-gray-500 dark:text-gray-400">관리자 권한이 필요합니다.</p>
        </div>
      </div>
    );
  }

  const handleCopy = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    setCopied(label);
    setTimeout(() => setCopied(""), 2000);
  };

  const installCode = SDK_INSTALL_CODE.replace(/API_BASE_URL/g, apiBase || "http://localhost:8000");
  const initCode = SDK_INIT_CODE.replace(/API_BASE_URL/g, apiBase || "http://localhost:8000");

  return (
    <div className="max-w-5xl mx-auto px-6 py-8 space-y-8">
      {/* ── 헤더 ──────────────────────────────────────────────── */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
          🧩 서비스 챗봇 SDK
        </h1>
        <p className="mt-2 text-gray-600 dark:text-gray-400">
          외부 웹사이트에 서비스 챗봇을 임베드하는 JavaScript SDK입니다. 채널톡 스타일의 플로팅 아이콘과 팝업 채팅창을 제공합니다.
        </p>
      </div>

      {/* ── 탭 네비게이션 ──────────────────────────────────────── */}
      <div className="flex border-b border-gray-200 dark:border-gray-700">
        <button
          onClick={() => setActiveTab("preview")}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            activeTab === "preview"
              ? "border-blue-600 text-blue-600 dark:border-blue-400 dark:text-blue-400"
              : "border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
          }`}
        >
          실시간 미리보기
        </button>
        <button
          onClick={() => setActiveTab("install")}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            activeTab === "install"
              ? "border-blue-600 text-blue-600 dark:border-blue-400 dark:text-blue-400"
              : "border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
          }`}
        >
          설치 가이드
        </button>
      </div>

      {/* ── 실시간 미리보기 ──────────────────────────────────────── */}
      {activeTab === "preview" && (
        <div className="space-y-6">
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              실시간 미리보기
            </h2>
            <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
              오른쪽 하단의 플로팅 아이콘을 클릭하면 채팅창이 열립니다. SDK가 {sdkLoaded ? "로드됨 ✅" : "로드 중..."} 상태입니다.
            </p>
            <div className="flex items-center gap-3">
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">
                <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
                API: {apiBase || "(상대 경로)"}
              </span>
              <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium ${sdkLoaded ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400" : "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400"}`}>
                <span className={`w-1.5 h-1.5 rounded-full ${sdkLoaded ? "bg-green-500" : "bg-yellow-500 animate-pulse"}`} />
                SDK {sdkLoaded ? "활성" : "로드 중"}
              </span>
            </div>
          </div>

          {/* 데모 컨테이너 (SDK가 여기에 렌더링됨) */}
          <div
            ref={demoRef}
            className="relative bg-gradient-to-br from-gray-50 to-gray-100 dark:from-gray-900 dark:to-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden"
            style={{ minHeight: "500px" }}
          >
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="text-center space-y-4 p-8">
                <div className="text-6xl">🤖</div>
                <h3 className="text-xl font-semibold text-gray-700 dark:text-gray-300">
                  SDK 미리보기 영역
                </h3>
                <p className="text-sm text-gray-500 dark:text-gray-400 max-w-md">
                  오른쪽 하단에 있는 플로팅 아이콘(🤖)을 클릭하면 채팅창이 열립니다.
                  설정 파일에서 정의한 인사 메시지, FAQ, 객관식 선택지가 모두 동적으로 렌더링됩니다.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── 설치 가이드 ──────────────────────────────────────────── */}
      {activeTab === "install" && (
        <div className="space-y-6">
          {/* 설치 코드 */}
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              1. SDK 스크립트 로드
            </h2>
            <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
              웹페이지의 <code className="px-1.5 py-0.5 bg-gray-100 dark:bg-gray-700 rounded text-xs">&lt;body&gt;</code> 태그 닫기 전에 아래 코드를 추가하세요.
            </p>
            <div className="relative">
              <pre className="bg-gray-50 dark:bg-gray-900 rounded-lg p-4 text-sm overflow-x-auto text-gray-800 dark:text-gray-200 border border-gray-200 dark:border-gray-700">
                <code>{installCode}</code>
              </pre>
              <button
                onClick={() => handleCopy(installCode, "install")}
                className="absolute top-2 right-2 px-2 py-1 text-xs bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
              >
                {copied === "install" ? "✅ 복사됨" : "📋 복사"}
              </button>
            </div>
          </div>

          {/* 초기화 옵션 */}
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              2. 초기화 옵션 (선택)
            </h2>
            <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
              <code className="px-1.5 py-0.5 bg-gray-100 dark:bg-gray-700 rounded text-xs">data-api-base</code> 속성으로 자동 초기화되지만, 추가 옵션을 지정하려면 수동 초기화 코드를 사용하세요.
            </p>
            <div className="relative">
              <pre className="bg-gray-50 dark:bg-gray-900 rounded-lg p-4 text-sm overflow-x-auto text-gray-800 dark:text-gray-200 border border-gray-200 dark:border-gray-700">
                <code>{initCode}</code>
              </pre>
              <button
                onClick={() => handleCopy(initCode, "init")}
                className="absolute top-2 right-2 px-2 py-1 text-xs bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
              >
                {copied === "init" ? "✅ 복사됨" : "📋 복사"}
              </button>
            </div>

            {/* 옵션 테이블 */}
            <div className="mt-6 overflow-x-auto">
              <table className="w-full text-sm border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
                <thead>
                  <tr className="bg-gray-50 dark:bg-gray-900">
                    <th className="text-left px-4 py-2 font-medium text-gray-700 dark:text-gray-300">옵션</th>
                    <th className="text-left px-4 py-2 font-medium text-gray-700 dark:text-gray-300">기본값</th>
                    <th className="text-left px-4 py-2 font-medium text-gray-700 dark:text-gray-300">설명</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                  <tr>
                    <td className="px-4 py-2 font-mono text-xs text-blue-600 dark:text-blue-400">apiBase</td>
                    <td className="px-4 py-2 text-gray-600 dark:text-gray-400">""</td>
                    <td className="px-4 py-2 text-gray-600 dark:text-gray-400">백엔드 API 베이스 URL</td>
                  </tr>
                  <tr>
                    <td className="px-4 py-2 font-mono text-xs text-blue-600 dark:text-blue-400">primaryColor</td>
                    <td className="px-4 py-2 text-gray-600 dark:text-gray-400">"#2563eb"</td>
                    <td className="px-4 py-2 text-gray-600 dark:text-gray-400">메인 컬러 (브랜딩 설정에서 자동 적용)</td>
                  </tr>
                  <tr>
                    <td className="px-4 py-2 font-mono text-xs text-blue-600 dark:text-blue-400">position</td>
                    <td className="px-4 py-2 text-gray-600 dark:text-gray-400">"right"</td>
                    <td className="px-4 py-2 text-gray-600 dark:text-gray-400">플로팅 아이콘 위치 ("right" | "left")</td>
                  </tr>
                  <tr>
                    <td className="px-4 py-2 font-mono text-xs text-blue-600 dark:text-blue-400">offsetBottom</td>
                    <td className="px-4 py-2 text-gray-600 dark:text-gray-400">24</td>
                    <td className="px-4 py-2 text-gray-600 dark:text-gray-400">하단 여백 (px)</td>
                  </tr>
                  <tr>
                    <td className="px-4 py-2 font-mono text-xs text-blue-600 dark:text-blue-400">offsetSide</td>
                    <td className="px-4 py-2 text-gray-600 dark:text-gray-400">24</td>
                    <td className="px-4 py-2 text-gray-600 dark:text-gray-400">측면 여백 (px)</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* API 엔드포인트 */}
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              3. API 엔드포인트
            </h2>
            <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
              SDK는 다음 백엔드 API를 사용합니다. CORS가 허용되어야 합니다.
            </p>
            <div className="space-y-3">
              <div className="flex items-start gap-3 p-3 rounded-lg bg-gray-50 dark:bg-gray-900">
                <span className="px-2 py-0.5 text-xs font-bold bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400 rounded">GET</span>
                <div>
                  <code className="text-sm text-gray-800 dark:text-gray-200">/api/service-chat/config</code>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">챗봇 설정 (브랜딩, 인사, FAQ, 객관식, 프롬프트) 로드</p>
                </div>
              </div>
              <div className="flex items-start gap-3 p-3 rounded-lg bg-gray-50 dark:bg-gray-900">
                <span className="px-2 py-0.5 text-xs font-bold bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400 rounded">POST</span>
                <div>
                  <code className="text-sm text-gray-800 dark:text-gray-200">/api/chat/stream</code>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">SSE 스트리밍 채팅 (service_mode: true)</p>
                </div>
              </div>
              <div className="flex items-start gap-3 p-3 rounded-lg bg-gray-50 dark:bg-gray-900">
                <span className="px-2 py-0.5 text-xs font-bold bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400 rounded">POST</span>
                <div>
                  <code className="text-sm text-gray-800 dark:text-gray-200">/api/chat</code>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">일반 채팅 (SSE 폴백)</p>
                </div>
              </div>
            </div>
          </div>

          {/* 설정 파일 안내 */}
          <div className="bg-blue-50 dark:bg-blue-900/20 rounded-xl border border-blue-200 dark:border-blue-800 p-6">
            <h3 className="text-sm font-semibold text-blue-800 dark:text-blue-300 mb-2">
              💡 챗봇 커스터마이징
            </h3>
            <p className="text-sm text-blue-700 dark:text-blue-400">
              인사 메시지, FAQ, 객관식 선택지, RAG 시스템 프롬프트 등은 <code className="px-1 py-0.5 bg-blue-100 dark:bg-blue-900/40 rounded text-xs">backend/data/service_chat_config.json</code> 파일에서 수정할 수 있습니다.
              수정 후 <code className="px-1 py-0.5 bg-blue-100 dark:bg-blue-900/40 rounded text-xs">POST /api/service-chat/config/reload</code> API로 리로드하세요.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}