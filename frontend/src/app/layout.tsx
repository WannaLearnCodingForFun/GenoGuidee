import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import Sidebar from "@/components/Sidebar";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "GenoGuide — Genomic Variant Intelligence",
  description:
    "AI-powered genomic variant interpretation & precision decision support. ESM-2 + XGBoost + deterministic ACMG engine + blockchain-style provenance.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-screen bg-bg text-fg">
        <div className="flex min-h-screen">
          <Sidebar />
          <main className="min-w-0 flex-1 pl-60">{children}</main>
        </div>
      </body>
    </html>
  );
}
