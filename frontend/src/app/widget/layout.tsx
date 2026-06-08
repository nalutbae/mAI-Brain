import type { Metadata } from "next";
import "../globals.css";

export const metadata: Metadata = {
  title: "mAI-Brain Chat Widget",
  description: "임베디드 채팅 위젯",
};

export default function WidgetLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
