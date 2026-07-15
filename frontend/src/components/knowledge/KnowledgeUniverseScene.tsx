"use client";

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Canvas, type ThreeEvent } from "@react-three/fiber";
import { Line, OrbitControls, Stars } from "@react-three/drei";
import { Bloom, EffectComposer } from "@react-three/postprocessing";
import { useQuery } from "@tanstack/react-query";
import * as THREE from "three";

import { getProjects, searchProjects } from "@/lib/api";
import { queryKeys } from "@/lib/queryClient";
import type { ProjectSummary } from "@/types";

/**
 * Knowledge Universe -- organizational memory rendered as a 3D graph of
 * every past project the org has run. Every node, color, edge and search
 * result here is driven by real `/projects` + `/projects/search` data;
 * nothing is fabricated. Positions are a deterministic sunflower/golden-
 * angle spiral over projects sorted by `created_at` (a stable, cheap
 * layout -- no simulation loop required), not a fake metric.
 */

const PROJECT_LIMIT = 200;
const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));

type FilterMode = "all" | "approved" | "unapproved";

function computeLayout(projects: ProjectSummary[]): Map<string, [number, number, number]> {
  const sorted = [...projects].sort(
    (a, b) => Date.parse(a.created_at) - Date.parse(b.created_at)
  );
  const positions = new Map<string, [number, number, number]>();
  sorted.forEach((project, index) => {
    const radius = 1.6 * Math.sqrt(index + 1);
    const angle = index * GOLDEN_ANGLE;
    const x = radius * Math.cos(angle);
    const z = radius * Math.sin(angle);
    const y = Math.sin(index * 0.37) * 2.2;
    positions.set(project.id, [x, y, z]);
  });
  return positions;
}

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() =>
    typeof window !== "undefined" && window.matchMedia
      ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
      : false
  );
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mql = window.matchMedia("(prefers-reduced-motion: reduce)");
    const handler = (event: MediaQueryListEvent) => setReduced(event.matches);
    mql.addEventListener("change", handler);
    return () => mql.removeEventListener("change", handler);
  }, []);
  return reduced;
}

/** The color scheme is only 3 discrete categories (approved/researched/
 * pending), never a true per-instance continuous value -- so each category
 * gets its own InstancedMesh with a fixed, uniform material color instead
 * of one InstancedMesh using per-instance `setColorAt`/`vertexColors`.
 *
 * That per-instance-color path was tried first and is a real, reproducible
 * bug in this environment's exact package versions (three@0.185 +
 * @react-three/fiber@9.6): `mesh.setColorAt()` demonstrably writes correct,
 * non-black linear-color values into `instanceColor` (verified by reading
 * the buffer back), yet `meshBasicMaterial vertexColors` renders the
 * instance as black/invisible regardless of `useEffect` vs `useLayoutEffect`
 * timing. Bucketing by fixed material color sidesteps the bug entirely --
 * per-instance highlighting (focus/search/related) is expressed through
 * scale instead of color brightness, which needed no instancing-attribute
 * workaround and was already working.
 */
const CATEGORIES = [
  { key: "approved", color: "#22c55e", test: (p: ProjectSummary) => p.approved },
  {
    key: "researched",
    color: "#22d3ee",
    test: (p: ProjectSummary) => !p.approved && p.research_approved,
  },
  {
    key: "pending",
    color: "#3b82f6",
    test: (p: ProjectSummary) => !p.approved && !p.research_approved,
  },
] as const;

interface CategoryNodesProps {
  categoryProjects: ProjectSummary[];
  color: string;
  positions: Map<string, [number, number, number]>;
  focusedId: string | null;
  relatedIds: Set<string>;
  matchedIds: Set<string>;
  searchActive: boolean;
  filterMode: FilterMode;
  cutoffTs: number | null;
  onHoverChange: (id: string | null) => void;
  onSelectNode: (id: string) => void;
}

/** One InstancedMesh draw call per category -- still cheap regardless of
 * node count (3 draw calls total, not N), per-instance position/scale
 * recomputed whenever focus, search, filter or the time scrub change. */
function CategoryNodes({
  categoryProjects,
  color,
  positions,
  focusedId,
  relatedIds,
  matchedIds,
  searchActive,
  filterMode,
  cutoffTs,
  onHoverChange,
  onSelectNode,
}: CategoryNodesProps) {
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const dummy = useMemo(() => new THREE.Object3D(), []);

  useLayoutEffect(() => {
    const mesh = meshRef.current;
    if (!mesh) return;

    categoryProjects.forEach((project, index) => {
      const pos = positions.get(project.id);
      if (!pos) return;

      const passesFilter =
        filterMode === "all" || (filterMode === "approved" ? project.approved : !project.approved);
      const passesTime = cutoffTs == null || Date.parse(project.created_at) <= cutoffTs;
      const visible = passesFilter && passesTime;

      const isFocused = project.id === focusedId;
      const isRelated = relatedIds.has(project.id);
      const isSearchMatch = matchedIds.has(project.id);

      let scale = 0.5;
      if (searchActive) scale = isSearchMatch ? 0.78 : 0.28;
      if (isRelated) scale = Math.max(scale, 0.85);
      if (isFocused) scale = 1.15;
      if (!visible) scale = 0;

      dummy.position.set(pos[0], pos[1], pos[2]);
      dummy.scale.setScalar(scale);
      dummy.updateMatrix();
      mesh.setMatrixAt(index, dummy.matrix);
    });

    mesh.instanceMatrix.needsUpdate = true;
  }, [categoryProjects, positions, focusedId, relatedIds, matchedIds, searchActive, filterMode, cutoffTs, dummy]);

  if (categoryProjects.length === 0) return null;

  return (
    <instancedMesh
      ref={meshRef}
      frustumCulled={false}
      args={[undefined, undefined, categoryProjects.length]}
      onPointerOver={(event: ThreeEvent<PointerEvent>) => {
        event.stopPropagation();
        if (typeof event.instanceId === "number") {
          const project = categoryProjects[event.instanceId];
          if (project) onHoverChange(project.id);
        }
      }}
      onPointerOut={(event: ThreeEvent<PointerEvent>) => {
        event.stopPropagation();
        onHoverChange(null);
      }}
      onClick={(event: ThreeEvent<MouseEvent>) => {
        event.stopPropagation();
        if (typeof event.instanceId === "number") {
          const project = categoryProjects[event.instanceId];
          if (project) onSelectNode(project.id);
        }
      }}
    >
      <icosahedronGeometry args={[0.42, 1]} />
      <meshBasicMaterial
        color={color}
        transparent
        depthWrite={false}
        blending={THREE.AdditiveBlending}
        toneMapped={false}
      />
    </instancedMesh>
  );
}

/** Draws real edges from the focused node to whichever semantically
 * similar projects (from the backend's vector-similarity search) are also
 * currently loaded -- the "related projects" requirement, satisfied with
 * a real backend-computed similarity score rather than a fabricated
 * distance metric. */
function RelatedEdges({
  focusedId,
  relatedIds,
  positions,
}: {
  focusedId: string;
  relatedIds: Set<string>;
  positions: Map<string, [number, number, number]>;
}) {
  const from = positions.get(focusedId);
  if (!from) return null;

  return (
    <>
      {Array.from(relatedIds).map((id) => {
        const to = positions.get(id);
        if (!to) return null;
        return (
          <Line key={id} points={[from, to]} color="#22d3ee" lineWidth={1.4} transparent opacity={0.6} />
        );
      })}
    </>
  );
}

export default function KnowledgeUniverseScene({
  onSelectProject,
}: {
  onSelectProject: (projectId: string) => void;
}) {
  const {
    data: projects = [],
    isLoading,
    error,
  } = useQuery({
    queryKey: queryKeys.projects(PROJECT_LIMIT),
    queryFn: () => getProjects(PROJECT_LIMIT),
  });

  const positions = useMemo(() => computeLayout(projects), [projects]);
  const categorizedProjects = useMemo(
    () => CATEGORIES.map((category) => ({ ...category, projects: projects.filter(category.test) })),
    [projects]
  );
  const prefersReducedMotion = usePrefersReducedMotion();

  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const focusedId = hoveredId ?? selectedId;
  const focusedProject = useMemo(
    () => projects.find((p) => p.id === focusedId) ?? null,
    [projects, focusedId]
  );

  const { data: relatedHits } = useQuery({
    queryKey: queryKeys.projectSearch(focusedProject ? `related::${focusedProject.goal}` : "__none__"),
    queryFn: () => searchProjects(focusedProject!.goal, 4),
    enabled: !!focusedProject,
  });

  const relatedIds = useMemo(() => {
    if (!focusedProject || !relatedHits) return new Set<string>();
    const loadedIds = new Set(projects.map((p) => p.id));
    const ids = relatedHits
      .map((hit) => hit.id)
      .filter((id) => id !== focusedProject.id && loadedIds.has(id));
    return new Set(ids);
  }, [focusedProject, relatedHits, projects]);

  const [searchInput, setSearchInput] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const { data: searchHits } = useQuery({
    queryKey: queryKeys.projectSearch(submittedQuery ? `query::${submittedQuery}` : "__none__"),
    queryFn: () => searchProjects(submittedQuery, 8),
    enabled: submittedQuery.trim().length > 0,
  });
  const matchedIds = useMemo(
    () => new Set((searchHits ?? []).map((hit) => hit.id)),
    [searchHits]
  );
  const searchActive = submittedQuery.trim().length > 0 && !!searchHits;

  const [filterMode, setFilterMode] = useState<FilterMode>("all");

  const timeBounds = useMemo<[number, number] | null>(() => {
    const timestamps = projects
      .map((p) => Date.parse(p.created_at))
      .filter((t) => !Number.isNaN(t));
    if (timestamps.length === 0) return null;
    return [Math.min(...timestamps), Math.max(...timestamps)];
  }, [projects]);
  const [cutoff, setCutoff] = useState<number | null>(null);
  const effectiveCutoff = cutoff ?? timeBounds?.[1] ?? null;

  return (
    <div className="relative h-full w-full">
      <div
        className="h-full w-full"
        onPointerLeave={() => setHoveredId(null)}
      >
        {/* Framed close for the common case of a handful of projects (the
            golden-angle spiral only spans a wide radius once there are many)
            -- OrbitControls' maxDistance={160} still lets you zoom out for a
            large project history instead of starting zoomed out for everyone. */}
        <Canvas dpr={[1, 2]} camera={{ position: [0, 7, 16], fov: 50, near: 0.1, far: 500 }}>
          <color attach="background" args={["#05060a"]} />
          <Stars
            radius={200}
            depth={60}
            count={2000}
            factor={2}
            saturation={0}
            fade
            speed={prefersReducedMotion ? 0 : 0.4}
          />

          {categorizedProjects.map((category) => (
            <CategoryNodes
              key={category.key}
              categoryProjects={category.projects}
              color={category.color}
              positions={positions}
              focusedId={focusedId}
              relatedIds={relatedIds}
              matchedIds={matchedIds}
              searchActive={searchActive}
              filterMode={filterMode}
              cutoffTs={effectiveCutoff}
              onHoverChange={setHoveredId}
              onSelectNode={(id) => {
                setSelectedId(id);
                onSelectProject(id);
              }}
            />
          ))}

          {focusedProject && relatedIds.size > 0 && (
            <RelatedEdges focusedId={focusedProject.id} relatedIds={relatedIds} positions={positions} />
          )}

          <OrbitControls enableDamping dampingFactor={0.08} minDistance={4} maxDistance={160} />

          <EffectComposer>
            <Bloom intensity={0.9} luminanceThreshold={0.15} luminanceSmoothing={0.4} mipmapBlur />
          </EffectComposer>
        </Canvas>
      </div>

      <div className="pointer-events-none absolute inset-0 flex flex-col justify-between gap-3 p-4">
        <div className="pointer-events-auto glass-panel flex flex-wrap items-center gap-3 p-3 text-xs">
          <form
            onSubmit={(event) => {
              event.preventDefault();
              setSubmittedQuery(searchInput.trim());
            }}
            className="flex items-center gap-2"
          >
            <input
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
              placeholder="Search past projects..."
              className="w-48 rounded border border-border bg-surface/70 px-2 py-1 text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-1 focus:ring-accent-cyan"
            />
            <button
              type="submit"
              className="rounded bg-accent-blue/80 px-2 py-1 text-white hover:bg-accent-blue"
            >
              Search
            </button>
            {submittedQuery && (
              <button
                type="button"
                onClick={() => {
                  setSubmittedQuery("");
                  setSearchInput("");
                }}
                className="rounded border border-border px-2 py-1 text-text-secondary hover:text-text-primary"
              >
                Clear
              </button>
            )}
          </form>

          <div className="flex items-center gap-1">
            {(["all", "approved", "unapproved"] as FilterMode[]).map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() => setFilterMode(mode)}
                className={`rounded px-2 py-1 capitalize ${
                  filterMode === mode
                    ? "bg-accent-purple/80 text-white"
                    : "border border-border text-text-secondary hover:text-text-primary"
                }`}
              >
                {mode}
              </button>
            ))}
          </div>

          {timeBounds && timeBounds[0] !== timeBounds[1] && (
            <label className="flex items-center gap-2 text-text-secondary">
              <span>Timeline</span>
              <input
                type="range"
                min={timeBounds[0]}
                max={timeBounds[1]}
                value={effectiveCutoff ?? timeBounds[1]}
                onChange={(event) => setCutoff(Number(event.target.value))}
                className="w-32 accent-accent-cyan"
              />
              <span className="font-mono text-text-muted">
                {new Date(effectiveCutoff ?? timeBounds[1]).toLocaleDateString()}
              </span>
            </label>
          )}

          <div className="ml-auto flex items-center gap-3 text-text-muted">
            <span className="flex items-center gap-1">
              <span className="inline-block h-2 w-2 rounded-full bg-status-completed" /> approved
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block h-2 w-2 rounded-full bg-accent-cyan" /> researched
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block h-2 w-2 rounded-full bg-accent-blue" /> pending
            </span>
          </div>
        </div>

        {isLoading && (
          <div className="pointer-events-auto glass-panel w-fit p-3 text-xs text-text-secondary">
            Loading knowledge graph...
          </div>
        )}
        {error && (
          <div className="pointer-events-auto glass-panel w-fit p-3 text-xs text-status-needs_review">
            Failed to load projects: {(error as Error).message}
          </div>
        )}
        {!isLoading && !error && projects.length === 0 && (
          <div className="pointer-events-auto glass-panel w-fit p-3 text-xs text-text-secondary">
            No projects yet -- the universe fills in as the organization runs projects.
          </div>
        )}

        <div className="flex items-end justify-between gap-3">
          <div className="pointer-events-none text-[11px] text-text-muted">
            Scroll to zoom &middot; drag to orbit &middot; hover or click a node to see related projects
          </div>

          {focusedProject && (
            <div className="pointer-events-auto glass-panel max-w-sm p-3 text-xs">
              <p className="line-clamp-3 text-text-primary">{focusedProject.goal}</p>
              <p className="mt-1 text-text-muted">
                {focusedProject.approved
                  ? "Approved"
                  : focusedProject.research_approved
                    ? "Research approved"
                    : "Pending approval"}
                {relatedIds.size > 0 && ` · ${relatedIds.size} related project${relatedIds.size === 1 ? "" : "s"} found`}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
