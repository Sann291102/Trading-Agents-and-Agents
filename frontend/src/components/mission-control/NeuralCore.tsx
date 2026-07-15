"use client";

import { useMemo, useRef, type ComponentRef } from "react";
import { useFrame } from "@react-three/fiber";
import { Float, Line, MeshDistortMaterial, Sparkles } from "@react-three/drei";
import * as THREE from "three";

import { useOrgStore } from "@/store/orgStore";

/**
 * The Executive AI, rendered as a holographic neural sphere -- explicitly
 * not a face/avatar per the design brief. Its motion and color are driven
 * by real aggregate organization state: `activity` (share of agents
 * currently executing) and `needsReview` are read reactively from the
 * Zustand store, so this only re-renders when that actually changes (on
 * agent_started/agent_finished events), not every frame. `useFrame` then
 * smoothly interpolates the visible material properties each frame toward
 * whatever the current `activity`/`needsReview` closure values are --
 * imperative per-frame mutation for smoothness, reactive updates only for
 * *what* to animate toward. There is no timer-driven or fabricated
 * animation: with nothing happening, the core settles to a slow idle
 * breathing pace.
 */

const IDLE_COLOR = new THREE.Color("#22d3ee");
const ACTIVE_COLOR = new THREE.Color("#f97316");
const REVIEW_COLOR = new THREE.Color("#ef4444");
const targetColor = new THREE.Color();

/** Fixed icosahedron-vertex directions, reused every render via useMemo --
 * purely decorative "synapse" spokes (the Z.E.R.O-style particle-web look
 * from the reference designs), not a stand-in for any real per-agent data.
 * Static geometry, so there is nothing here to keep in sync with the org
 * roster. */
function useSynapseDirections(count: number): THREE.Vector3[] {
  return useMemo(() => {
    const phi = (1 + Math.sqrt(5)) / 2;
    const raw: [number, number, number][] = [
      [-1, phi, 0], [1, phi, 0], [-1, -phi, 0], [1, -phi, 0],
      [0, -1, phi], [0, 1, phi], [0, -1, -phi], [0, 1, -phi],
      [phi, 0, -1], [phi, 0, 1], [-phi, 0, -1], [-phi, 0, 1],
    ];
    return raw.slice(0, count).map(([x, y, z]) => new THREE.Vector3(x, y, z).normalize());
  }, [count]);
}

export function NeuralCore() {
  const activity = useOrgStore((state) => {
    const agents = Object.values(state.agents);
    if (agents.length === 0) return 0;
    return agents.filter((a) => a.status === "executing").length / agents.length;
  });
  const needsReview = useOrgStore((state) =>
    Object.values(state.agents).some((a) => a.status === "needs_review")
  );

  const meshRef = useRef<THREE.Mesh>(null);
  const materialRef = useRef<ComponentRef<typeof MeshDistortMaterial>>(null);
  const lightRef = useRef<THREE.PointLight>(null);
  const synapseDirections = useSynapseDirections(10);
  const synapseOpacity = 0.12 + activity * 0.4;

  useFrame((_, delta) => {
    const mesh = meshRef.current;
    if (mesh) {
      mesh.rotation.y += delta * 0.12;
      mesh.rotation.x += delta * 0.03;
    }

    const material = materialRef.current;
    if (material) {
      material.distort = THREE.MathUtils.lerp(material.distort, 0.25 + activity * 0.55, 0.04);

      targetColor.copy(IDLE_COLOR).lerp(ACTIVE_COLOR, activity * 0.7);
      if (needsReview) targetColor.lerp(REVIEW_COLOR, 0.55);
      material.color.lerp(targetColor, 0.03);
      material.emissive.copy(material.color);
      material.emissiveIntensity = THREE.MathUtils.lerp(
        material.emissiveIntensity,
        0.4 + activity * 0.9,
        0.04
      );
    }

    if (lightRef.current) {
      lightRef.current.intensity = THREE.MathUtils.lerp(
        lightRef.current.intensity,
        1.4 + activity * 2.2,
        0.04
      );
    }
  });

  return (
    <Float speed={1.4} rotationIntensity={0.2} floatIntensity={0.6}>
      <group>
        <mesh ref={meshRef}>
          <icosahedronGeometry args={[1.6, 6]} />
          <MeshDistortMaterial
            ref={materialRef}
            color={IDLE_COLOR}
            emissive={IDLE_COLOR}
            emissiveIntensity={0.5}
            roughness={0.15}
            metalness={0.6}
            distort={0.3}
            speed={2}
            radius={1}
            transparent
            opacity={0.92}
          />
        </mesh>

        <pointLight ref={lightRef} color={IDLE_COLOR} intensity={1.6} distance={12} decay={2} />

        {synapseDirections.map((direction, index) => (
          <Line
            key={index}
            points={[
              [direction.x * 1.7, direction.y * 1.7, direction.z * 1.7],
              [direction.x * 2.9, direction.y * 2.9, direction.z * 2.9],
            ]}
            color={index % 3 === 0 ? "#a855f7" : "#22d3ee"}
            lineWidth={1}
            transparent
            opacity={synapseOpacity}
          />
        ))}

        <Sparkles count={220} scale={6.2} size={2} speed={0.3} color={IDLE_COLOR} noise={1.4} />
      </group>
    </Float>
  );
}
