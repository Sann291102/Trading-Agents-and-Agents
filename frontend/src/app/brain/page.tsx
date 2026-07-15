"use client";

import dynamic from "next/dynamic";
import Link from "next/link";

import { BrainChat } from "@/components/brain/BrainChat";

const BrainScene = dynamic(() => import("@/components/brain/BrainScene"), {
  ssr: false,
  loading: () => (
    <div className="flex flex-1 items-center justify-center text-sm text-text-muted">
      Loading the brain…
    </div>
  ),
});

/**
 * The Brain -- organizational memory as a neural-particle core with one
 * region per real memory type, plus a chat box for casual questions
 * answered from that same memory (POST /chat) rather than the full mission
 * pipeline. Mirrors the Knowledge Universe page's composition (thin route,
 * dynamic ssr:false import of the 3D scene, back-link overlay).
 */
export default function BrainPage() {
  return (
    <main className="relative flex-1">
      <div className="absolute inset-0">
        <BrainScene />
      </div>

      <div className="pointer-events-none absolute left-4 top-4 md:left-6 md:top-6">
        <Link
          href="/"
          className="pointer-events-auto inline-block glass-panel px-3 py-1.5 text-xs text-text-muted hover:text-text-primary"
        >
          ← Mission Control
        </Link>
      </div>

      <div className="pointer-events-none absolute left-1/2 top-4 -translate-x-1/2 md:top-6">
        <div className="hud-panel pointer-events-auto px-4 py-1.5 text-center">
          <p className="hud-label text-[11px] text-text-primary">The Brain</p>
          <p className="mt-0.5 text-[11px] text-text-muted">
            scroll to zoom · drag to orbit · ask a question below
          </p>
        </div>
      </div>

      <BrainChat />
    </main>
  );
}
