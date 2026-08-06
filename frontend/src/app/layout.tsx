import type { Metadata, Viewport } from "next";
import "./globals.css";
import { ThemeProvider } from "@/components/providers/ThemeProvider";
import { AppShell } from "@/components/layout/AppShell";

export const metadata: Metadata = {
  title: {
    default: "AInvest — Local AI Trading Research Terminal",
    template: "%s · AInvest",
  },
  description:
    "A fully local AI trading research platform: TradingAgents multi-agent analysis, RAEM episodic memory, and live market data — no cloud, no login.",
};

export const viewport: Viewport = {
  themeColor: "#0a0d12",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="antialiased" suppressHydrationWarning>
        <ThemeProvider>
          <AppShell>{children}</AppShell>
        </ThemeProvider>
      </body>
    </html>
  );
}
