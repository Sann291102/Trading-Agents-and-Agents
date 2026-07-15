"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { ProjectDetailPanel } from "@/components/knowledge/ProjectDetailPanel";

const KnowledgeUniverseScene = dynamic(
  () => import("@/components/knowledge/KnowledgeUniverseScene"),
  {
    ssr: false,
    loading: () => (
      <div className="flex flex-1 items-center justify-center text-sm text-text-muted">
        Loading knowledge universe…
      </div>
    ),
  }
);

function KnowledgePageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const selectedProjectId = searchParams.get("project");

  return (
    <main className="relative flex-1">
      <div className="absolute inset-0">
        <KnowledgeUniverseScene
          onSelectProject={(id) => router.push(`/knowledge?project=${encodeURIComponent(id)}`)}
        />
      </div>

      <div className="pointer-events-none absolute left-4 top-4 md:left-6 md:top-6">
        <Link
          href="/"
          className="pointer-events-auto inline-block glass-panel px-3 py-1.5 text-xs text-text-muted hover:text-text-primary"
        >
          ← Mission Control
        </Link>
      </div>

      <ProjectDetailPanel
        projectId={selectedProjectId}
        onClose={() => router.push("/knowledge")}
      />
    </main>
  );
}

/**
 * Knowledge Universe -- organizational memory as a 3D graph of every past
 * project. The selected project id lives in the URL (`?project=<id>`) so
 * a direct link to a specific memory node (e.g. from the command palette's
 * search results) works without extra state plumbing. `useSearchParams()`
 * requires a Suspense boundary in the App Router, hence the split.
 */
export default function KnowledgePage() {
  return (
    <Suspense
      fallback={
        <div className="flex flex-1 items-center justify-center text-sm text-text-muted">
          Loading…
        </div>
      }
    >
      <KnowledgePageContent />
    </Suspense>
  );
}
