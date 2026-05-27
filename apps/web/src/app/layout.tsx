import type { Metadata } from "next";
import Link from "next/link";
import UserSwitcher from "@/components/UserSwitcher";
import "./globals.css";

export const metadata: Metadata = {
  title: "多 Agent 科研论文助手",
  description: "上传科研 PDF、解析论文、构建论文记忆、进行 RAG 问答、抽取研究 Idea、推荐引用",
};

const NAV_LINKS = [
  { label: "首页", href: "/" },
  { label: "论文库", href: "/papers" },
  { label: "跨论文问答", href: "/papers/ask" },
  { label: "Idea", href: "/ideas" },
  { label: "Agent", href: "/agent" },
  { label: "MCP", href: "/mcp" },
  { label: "任务", href: "/jobs" },
  { label: "用量/质量", href: "/usage" },
];

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body className="bg-gray-50 text-gray-900 min-h-screen flex flex-col">
        <nav className="bg-white border-b border-gray-200 sticky top-0 z-30">
          <div className="max-w-5xl mx-auto px-4 sm:px-6">
            <div className="flex items-center justify-between h-12">
              <Link href="/" className="text-sm font-bold text-gray-900 shrink-0">
                科研论文助手
              </Link>
              <div className="flex items-center gap-1 overflow-x-auto">
                {NAV_LINKS.map((link) => (
                  <Link
                    key={link.href}
                    href={link.href}
                    className="px-3 py-1.5 text-xs font-medium text-gray-600 hover:text-blue-600 hover:bg-blue-50 rounded-md transition-colors whitespace-nowrap"
                  >
                    {link.label}
                  </Link>
                ))}
              </div>
              <UserSwitcher />
            </div>
          </div>
        </nav>
        <main data-testid="app-main" className="flex-1">{children}</main>
      </body>
    </html>
  );
}
