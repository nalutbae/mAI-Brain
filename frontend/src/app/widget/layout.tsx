import type { Metadata } from "next";
import "../globals.css";

export const metadata: Metadata = {
  title: "mAI-Brain Chat Widget",
  description: "임베디드 채팅 위젯",
};

/**
 * 위젯 전용 최소 레이아웃.
 * RootLayout의 NavBar는 유지되지만 CSS로 숨김 처리합니다.
 */
export default function WidgetLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      {/* RootLayout의 NavBar를 숨기고 위젯을 전체 화면으로 확장 */}
      <style>{`
        /* NavBar 영역 숨기기 */
        body > nav, body > header {
          display: none !important;
        }
        /* 위젯을 전체 높이로 */
        body > main {
          height: 100vh !important;
          max-height: 100vh !important;
          overflow: hidden !important;
        }
        body {
          margin: 0 !important;
          padding: 0 !important;
          overflow: hidden !important;
        }
      `}</style>
      {children}
    </>
  );
}
