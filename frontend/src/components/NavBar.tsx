"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "../lib/auth";
import ThemeToggle from "./ThemeToggle";

// nginx 프록시 모드에서는 빈 문자열(상대 경로) 사용
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

// 관리자 전용 경로
const ADMIN_PATHS = ["/admin", "/admin/api-keys", "/admin/chunking", "/admin/prompts", "/admin/users", "/admin/workspaces", "/admin/settings", "/admin/sdk-demo"];

// 로그인 필요 경로 (모든 페이지)
// 로그인 없이 접근 가능: /login, /api/v1 (외부 API)

export default function NavBar() {
  const pathname = usePathname();
  const { user, loading, isAdmin, logout } = useAuth();

  // 로그인 페이지에서는 NavBar 숨김
  if (pathname === "/login") return null;

  // 로딩 중이면 빈 NavBar
  if (loading) {
    return (
      <nav className="border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-6 py-0 flex items-center gap-6 shrink-0">
        <Link href="/" className="text-lg font-bold text-gray-900 dark:text-white py-3 mr-4">
          mAI-Brain
        </Link>
        <div className="flex-1" />
        <ThemeToggle />
      </nav>
    );
  }

  // 로그인하지 않은 경우: 최소 메뉴만 표시
  if (!user) {
    return (
      <nav className="border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-6 py-0 flex items-center gap-6 shrink-0">
        <Link href="/" className="text-lg font-bold text-gray-900 dark:text-white py-3 mr-4">
          mAI-Brain
        </Link>
        <div className="flex-1" />
        <Link
          href="/login"
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium"
        >
          로그인
        </Link>
        <ThemeToggle />
      </nav>
    );
  }

  // 로그인한 사용자: role에 따라 메뉴 필터링
  const allLinks = [
    { href: "/", label: "💬 채팅", active: pathname === "/" && !pathname.startsWith("/service-chat"), adminOnly: false },
    { href: "/service-chat", label: "🤖 서비스 챗봇", active: pathname === "/service-chat", adminOnly: false },
    { href: "/admin/workspaces", label: "📁 워크스페이스", active: pathname === "/admin/workspaces", adminOnly: true },
    { href: "/cross-reasoning", label: "🔀 교차추론", active: pathname === "/cross-reasoning", adminOnly: false },
    { href: "/knowledge-graph", label: "🕸️ 지식그래프", active: pathname === "/knowledge-graph", adminOnly: false },
    { href: "/admin", label: "📚 문서 관리", active: pathname === "/admin", adminOnly: true },
    { href: "/admin/chunking", label: "⚙️ 청킹", active: pathname === "/admin/chunking", adminOnly: true },
    { href: "/admin/prompts", label: "📝 프롬프트", active: pathname === "/admin/prompts", adminOnly: true },
    { href: "/admin/api-keys", label: "🔑 API 키", active: pathname === "/admin/api-keys", adminOnly: true },
    { href: "/admin/users", label: "👥 사용자", active: pathname === "/admin/users", adminOnly: true },
    { href: "/evaluation", label: "📊 평가", active: pathname === "/evaluation", adminOnly: true },
    { href: "/feedback", label: "🔄 피드백", active: pathname === "/feedback", adminOnly: false },
    { href: "/admin/settings", label: "⚙️ 설정", active: pathname === "/admin/settings", adminOnly: true },
    { href: "/admin/sdk-demo", label: "🧩 SDK 데모", active: pathname === "/admin/sdk-demo", adminOnly: true },
    { href: `${API_BASE_URL}/scalar`, label: "📖 API 문서", active: false, adminOnly: true, external: true },
  ];

  const links = allLinks.filter((link) => !link.adminOnly || isAdmin);

  return (
    <nav className="border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-6 py-0 flex items-center gap-4 shrink-0">
      <Link href="/" className="text-lg font-bold text-gray-900 dark:text-white py-3 mr-2">
        mAI-Brain
      </Link>
      {links.map((link) =>
        link.external ? (
          <a
            key={link.href}
            href={link.href}
            target="_blank"
            rel="noopener noreferrer"
            className="py-3 border-b-2 text-sm font-medium transition-colors border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
          >
            {link.label}
          </a>
        ) : (
          <Link
            key={link.href}
            href={link.href}
            className={`py-3 border-b-2 text-sm font-medium transition-colors ${
              link.active
                ? "border-blue-600 text-blue-600 dark:border-blue-400 dark:text-blue-400"
                : "border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
            }`}
          >
            {link.label}
          </Link>
        ),
      )}
      <div className="flex-1" />
      {/* 사용자 정보 */}
      <div className="flex items-center gap-3">
        <span className="text-sm text-gray-600 dark:text-gray-400">
          {user.display_name || user.username}
          {isAdmin && <span className="ml-1 text-xs text-purple-600 dark:text-purple-400">관리자</span>}
        </span>
        <button
          onClick={logout}
          className="text-sm text-gray-500 hover:text-red-600 dark:text-gray-400 dark:hover:text-red-400 transition-colors"
        >
          로그아웃
        </button>
      </div>
      <ThemeToggle />
    </nav>
  );
}