import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Clipper 2.0 — Pro AI Short-Form Video Studio",
  description: "Turn any video or live stream into professionally edited vertical Reels, Shorts, and TikToks.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="bg-[#070B14] text-slate-100 antialiased selection:bg-cyan-500/30">
        {children}
      </body>
    </html>
  );
}
