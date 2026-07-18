"use client";

import { Canvas } from "@react-three/fiber";
import { Stars } from "@react-three/drei";
import { Bloom, EffectComposer } from "@react-three/postprocessing";

import { CinematicCamera } from "./CinematicCamera";
import { GalaxyField } from "./GalaxyField";
import { NeuralCore } from "./NeuralCore";
import { OrgGraph } from "./OrgGraph";

/**
 * The Mission Control 3D scene: the Executive AI's neural core at the
 * center, the live organization graph radiating from it, and a cinematic
 * camera that follows real work as it moves between departments. Loaded
 * client-only via next/dynamic (see app/page.tsx) -- Three.js touches
 * `window` at import time and breaks under Next's server rendering.
 */
export default function MissionControlScene() {
  return (
    <Canvas
      dpr={[1, 2]}
      camera={{ position: [0, 3.2, 11], fov: 50, near: 0.1, far: 200 }}
      gl={{ antialias: true }}
    >
      <color attach="background" args={["#05060a"]} />
      <ambientLight intensity={0.3} />
      <hemisphereLight intensity={0.25} color="#4c6fff" groundColor="#05060a" />

      <Stars radius={160} depth={60} count={2200} factor={2} saturation={0} fade speed={0.3} />

      {/* Atmospheric galaxy + drifting constellation nodes, behind the live
       * org graph -- see GalaxyField. Renders no interactive data. */}
      <GalaxyField />

      <NeuralCore />
      <OrgGraph />
      <CinematicCamera />

      <EffectComposer>
        <Bloom intensity={1.15} luminanceThreshold={0.18} luminanceSmoothing={0.5} mipmapBlur />
      </EffectComposer>
    </Canvas>
  );
}
