import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "agentguard dashboard",
  description: "Audit log and approval queue for agentguard-enforced AI agent tool calls.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-neutral-950 text-neutral-100">
        <nav className="border-b border-neutral-800 px-6 py-4 flex gap-6 text-sm items-center">
          <span className="font-semibold">agentguard</span>
          <a href="/audit" className="text-neutral-400 hover:text-neutral-100">
            Audit Log
          </a>
          <a href="/approvals" className="text-neutral-400 hover:text-neutral-100">
            Approvals
          </a>
          <form action="/api/auth/logout" method="post" className="ml-auto">
            <button type="submit" className="text-neutral-400 hover:text-neutral-100">
              Sign out
            </button>
          </form>
        </nav>
        <main className="flex-1 px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
