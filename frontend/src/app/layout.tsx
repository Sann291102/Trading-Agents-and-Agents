import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { CommandPalette } from "@/components/CommandPalette";
import { NotificationStack } from "@/components/NotificationStack";
import { OrgProvider } from "@/components/OrgProvider";
import { StatusBar } from "@/components/StatusBar";
import { ExecutiveNarration } from "@/components/mission-control/ExecutiveNarration";

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
  title: "JARVIS -- Mission Control",
  description: "JARVIS: the central intelligence of your autonomous AI organization",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <OrgProvider>
          <div className="flex min-h-0 flex-1 flex-col">{children}</div>
          <StatusBar />
          <CommandPalette />
          <NotificationStack />
          <ExecutiveNarration />
        </OrgProvider>
      </body>
    </html>
  );
}
