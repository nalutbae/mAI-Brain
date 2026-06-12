"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import ThemeToggle from "./ThemeToggle";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function NavBar() {
  const pathname = usePathname();

  const links: Array<
    { href: string; label: string; active: boolean } &
      { external?: boolean }
  > = [
    { href: "/", label: "💬 채팅", active: pathname === "/" },
    { href: "/workspaces", label: "📁 워크스페이스", active: pathname === "/workspaces" },
    { href: "/sessions", label: "📋 대화 목록", active: pathname === "/sessions" },
    { href: "/cross-reasoning", label: "🔀 교차추론", active: pathname === "/cross-reasoning" },
    { href: "/admin", label: "📚 문서 관리", active: pathname === "/admin" },
    { href: "/admin/chunking", label: "⚙️ 청킹", active: pathname === "/admin/chunking" },
    { href: "/admin/prompts", label: "📝 프롬프트", active: pathname === "/admin/prompts" },
    { href: "/admin/api-keys", label: "🔑 API 키", active: pathname === "/admin/api-keys" },
    { href: "/evaluation", label: "📊 평가", active: pathname === "/evaluation" },
    { href: "/feedback", label: "🔄 피드백", active: pathname === "/feedback" },
    { href: "/settings", label: "⚙️ 설정", active: pathname === "/settings" },
    { href: `${API_BASE_URL}/scalar`, label: "📖 API 문서", active: false, external: true },
  ];

  return (
    <nav className="border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-6 py-0 flex items-center gap-6 shrink-0">
      <Link
        href="/"
        className="text-lg font-bold text-gray-900 dark:text-white py-3 mr-4"
      >
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
      {/* spacer — 토글 버튼을 오른쪽으로 밀기 */}
      <div className="flex-1" />
      <ThemeToggle />
    </nav>
  );
}