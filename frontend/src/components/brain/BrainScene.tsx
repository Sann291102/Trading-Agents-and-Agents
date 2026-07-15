"use client";

import { useMemo, useRef, useState, type ComponentRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Float, Html, Line, MeshDistortMaterial, OrbitControls, Sparkles, Stars } from "@react-three/drei";
import { Bloom, EffectComposer } from "@react-three/postprocessing";
import { useQuery } from "@tanstack/react-query";
import * as THREE from "three";

import { getMemoryEntries } from "@/lib/api";
import { queryKeys } from "@/lib/queryClient";
import type { MemoryEntry, MemoryType } from "@/types";

/**
 * The Brain -- organizational memory rendered as a neural-particle core with
 * one labeled "region" per real MemoryType (see aio/models/memory.py),
 * sized by its actual entry count from GET /memory-entries. This is the
 * honest answer to "should work 24/7 from the database": the durable part
 * (memory) already lives in the DB and is always queryable on demand -- there
 * is no local GPU running continuous background inference, so nothing here
 * claims otherwise. Loaded client-only via next/dynamic (see app/brain's
 * page.tsx) -- Three.js touches `window` at import time and breaks under
 * Next's server rendering, the same reason MissionControlScene/
 * KnowledgeUniverseScene are dynamic-imported.
 */

const REGIONS: { type: MemoryType; label: string; color: string }[] = [
  { type: "research_finding", label: "Research", color: "#22d3ee" },
  { type: "architectural_decision", label: "Architecture", color: "#3b82f6" },
  { type: "lesson_learned", label: "Lessons", color: "#f97316" },
  { type: "reusable_component", label: "Components", color: "#22c55e" },
  { type: "risk", label: "Risks", color: "#ef4444" },
];

const EMPTY_ENTRIES: MemoryEntry[] = [];

function countByType(entries: MemoryEntry[]): Map<MemoryType, number> {
  const counts = new Map<MemoryType, number>();
  for (const entry of entries) {
    counts.set(entry.type, (counts.get(entry.type) ?? 0) + 1);
  }
  return counts;
}

function BrainCore({ totalEntries }: { totalEntries: number }) {
  const meshRef = useRef<THREE.Mesh>(null);
  const materialRef = useRef<ComponentRef<typeof MeshDistortMaterial>>(null);
  const activity = Math.min(1, totalEntries / 40);

  useFrame((_, delta) => {
    const mesh = meshRef.current;
    if (mesh) {
      mesh.rotation.y += delta * 0.08;
      mesh.rotation.x += delta * 0.02;
    }
    const material = materialRef.current;
    if (material) {
      material.emissiveIntensity = THREE.MathUtils.lerp(
        material.emissiveIntensity,
        0.5 + activity * 0.6,
        0.04
      );
    }
  });

  return (
    <Float speed={1.1} rotationIntensity={0.15} floatIntensity={0.5}>
      <mesh ref={meshRef}>
        <icosahedronGeometry args={[1.3, 6]} />
        <MeshDistortMaterial
          ref={materialRef}
          color="#a855f7"
          emissive="#a855f7"
          emissiveIntensity={0.5}
          roughness={0.2}
          metalness={0.5}
          distort={0.35}
          speed={1.6}
          radius={1}
          transparent
          opacity={0.9}
        />
      </mesh>
      <pointLight color="#a855f7" intensity={2} distance={14} decay={2} />
      <Sparkles count={260} scale={7.5} size={2} speed={0.25} color="#22d3ee" noise={1.5} />
    </Float>
  );
}

function RegionNode({
  index,
  total,
  label,
  color,
  count,
}: {
  index: number;
  total: number;
  label: string;
  color: string;
  count: number;
}) {
  const angle = (index / total) * Math.PI * 2;
  const radius = 4.4;
  const position: [number, number, number] = [
    Math.cos(angle) * radius,
    Math.sin(index * 1.7) * 0.9,
    Math.sin(angle) * radius,
  ];
  const nodeRadius = 0.26 + Math.min(0.4, Math.sqrt(count) * 0.11);
  const [hovered, setHovered] = useState(false);

  return (
    <group position={position}>
      <mesh
        onPointerOver={(event) => {
          event.stopPropagation();
          setHovered(true);
          document.body.style.cursor = "pointer";
        }}
        onPointerOut={(event) => {
          event.stopPropagation();
          setHovered(false);
          document.body.style.cursor = "auto";
        }}
        scale={hovered ? 1.15 : 1}
      >
        <sphereGeometry args={[nodeRadius, 24, 24]} />
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={0.7}
          roughness={0.3}
          metalness={0.4}
        />
      </mesh>
      <Line
        points={[
          [0, 0, 0],
          [-position[0] * 0.72, -position[1] * 0.72, -position[2] * 0.72],
        ]}
        color={color}
        lineWidth={1}
        transparent
        opacity={0.3}
      />
      <Html distanceFactor={11} center position={[0, nodeRadius + 0.4, 0]} occlude>
        <div
          className="hud-label pointer-events-none whitespace-nowrap rounded border border-accent-cyan/30 bg-void/85 px-2 py-1 text-[9px] text-text-primary shadow"
          style={{ borderColor: `${color}66` }}
        >
          <span className="font-semibold">{label}</span>
          <span className="ml-1.5 normal-case tracking-normal text-text-muted">{count}</span>
        </div>
      </Html>
    </group>
  );
}

/**
 * Self-contained, like MissionControlScene/KnowledgeUniverseScene: fetches
 * its own data (memory entries) rather than requiring the page to thread
 * props through the dynamic-import boundary.
 */
export default function BrainScene() {
  const entriesQuery = useQuery({
    queryKey: queryKeys.memoryEntries(200),
    queryFn: () => getMemoryEntries(200),
  });
  const entries = useMemo(() => entriesQuery.data ?? EMPTY_ENTRIES, [entriesQuery.data]);
  const counts = useMemo(() => countByType(entries), [entries]);

  return (
    <Canvas dpr={[1, 2]} camera={{ position: [0, 2.4, 10], fov: 50, near: 0.1, far: 200 }}>
      <color attach="background" args={["#05060a"]} />
      <ambientLight intensity={0.3} />
      <hemisphereLight intensity={0.25} color="#a855f7" groundColor="#05060a" />
      <Stars radius={160} depth={60} count={1800} factor={2} saturation={0} fade speed={0.25} />

      <BrainCore totalEntries={entries.length} />
      {REGIONS.map((region, index) => (
        <RegionNode
          key={region.type}
          index={index}
          total={REGIONS.length}
          label={region.label}
          color={region.color}
          count={counts.get(region.type) ?? 0}
        />
      ))}

      <OrbitControls enableDamping dampingFactor={0.08} minDistance={4} maxDistance={26} />
      <EffectComposer>
        <Bloom intensity={1.1} luminanceThreshold={0.18} luminanceSmoothing={0.5} mipmapBlur />
      </EffectComposer>
    </Canvas>
  );
}
