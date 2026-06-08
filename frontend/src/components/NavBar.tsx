"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export default function NavBar() {
  const pathname = usePathname();

  const links = [
    { href: "/", label: "💬 채팅", active: pathname === "/" },
    { href: "/admin", label: "📚 문서 관리", active: pathname === "/admin" },
  ];

  return (
    <nav className="border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-6 py-0 flex items-center gap-6 shrink-0">
      <Link
        href="/"
        className="text-lg font-bold text-gray-900 dark:text-white py-3 mr-4"
      >
        mAI-Brain
      </Link>
      {links.map((link) => (
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
      ))}
    </nav>
  );
}
