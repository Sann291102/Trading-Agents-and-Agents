"use client";

import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

/**
 * Purely-atmospheric galaxy backdrop that sits *behind* the live org graph
 * and neural core (it renders no interactive data -- NeuralCore/OrgGraph
 * remain the real, backend-wired scene). Two layers:
 *
 *  1. A colorful spiral galaxy disc -- thousands of points laid out along
 *     logarithmic spiral arms, colored on an inner-warm to outer-cool
 *     gradient, rotating slowly around Y so the whole HQ feels like it sits
 *     inside a living galaxy.
 *  2. A smaller set of brighter "constellation" nodes that drift on their
 *     own velocities; every frame we recompute pairwise proximity and light
 *     up a connecting line between any two that have drifted near each other
 *     (brighter the closer they are). That's the "nodes connect when they
 *     reach the same space again" behaviour -- emergent from real distance
 *     math, not a scripted timeline.
 *
 * All motion mutates geometry/refs directly inside useFrame (the standard
 * R3F pattern), so React never re-renders per frame.
 */

/** Seeded, pure PRNG (mulberry32). Used instead of Math.random so the
 * galaxy/node layout is generated deterministically during render -- the
 * React purity lint rule forbids impure calls like Math.random there, and a
 * fixed seed also means the scene looks identical on every mount. */
function makeRng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const GALAXY_COUNT = 6000;
const GALAXY_RADIUS = 60;
const GALAXY_ARMS = 5;
const GALAXY_SPIN = 1.1;
const GALAXY_RANDOMNESS = 0.55;

const INNER_COLOR = new THREE.Color("#ff5d8f"); // warm pink-magenta core
const MID_COLOR = new THREE.Color("#8b5cf6"); // violet
const OUTER_COLOR = new THREE.Color("#22d3ee"); // cyan rim

function GalaxyDisc() {
  const pointsRef = useRef<THREE.Points>(null);

  const { positions, colors } = useMemo(() => {
    const rng = makeRng(1337);
    const positions = new Float32Array(GALAXY_COUNT * 3);
    const colors = new Float32Array(GALAXY_COUNT * 3);
    const color = new THREE.Color();

    for (let i = 0; i < GALAXY_COUNT; i++) {
      const i3 = i * 3;
      // Bias toward the center so the core is dense (sqrt gives more points
      // near r=0 -- a real galaxy is brightest at the middle).
      const radius = Math.sqrt(rng()) * GALAXY_RADIUS;
      const armAngle = ((i % GALAXY_ARMS) / GALAXY_ARMS) * Math.PI * 2;
      const spinAngle = radius * (GALAXY_SPIN / GALAXY_RADIUS) * Math.PI * 2;

      // Randomness grows with radius so arms are tight in the core and
      // fluffy at the rim; cubed keeps most points on the arm, few strays.
      const spread = () =>
        Math.pow(rng(), 3) *
        (rng() < 0.5 ? 1 : -1) *
        GALAXY_RANDOMNESS *
        (radius / GALAXY_RADIUS) *
        6;

      const angle = armAngle + spinAngle;
      positions[i3] = Math.cos(angle) * radius + spread();
      positions[i3 + 1] = spread() * 0.6; // thin disc -- little vertical spread
      positions[i3 + 2] = Math.sin(angle) * radius + spread();

      // Inner->mid->outer color gradient by normalized radius.
      const t = radius / GALAXY_RADIUS;
      if (t < 0.5) {
        color.copy(INNER_COLOR).lerp(MID_COLOR, t / 0.5);
      } else {
        color.copy(MID_COLOR).lerp(OUTER_COLOR, (t - 0.5) / 0.5);
      }
      colors[i3] = color.r;
      colors[i3 + 1] = color.g;
      colors[i3 + 2] = color.b;
    }
    return { positions, colors };
  }, []);

  useFrame((_, delta) => {
    if (pointsRef.current) {
      pointsRef.current.rotation.y += delta * 0.035;
    }
  });

  return (
    <points ref={pointsRef} rotation={[Math.PI * 0.12, 0, 0]} position={[0, -4, -6]}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
        <bufferAttribute attach="attributes-color" args={[colors, 3]} />
      </bufferGeometry>
      <pointsMaterial
        size={0.28}
        sizeAttenuation
        vertexColors
        transparent
        opacity={0.85}
        depthWrite={false}
        blending={THREE.AdditiveBlending}
      />
    </points>
  );
}

const NODE_COUNT = 26;
const FIELD = 13; // half-extent of the drifting node cloud
const LINK_DISTANCE = 4.6; // proximity threshold for a connection to light up
const MAX_LINKS = (NODE_COUNT * (NODE_COUNT - 1)) / 2;

function ConstellationNodes() {
  const pointsRef = useRef<THREE.Points>(null);
  const linesRef = useRef<THREE.LineSegments>(null);

  // Everything is built imperatively once, in a memo, and returned as THREE
  // objects. Per-frame motion then mutates the *geometry attribute arrays*
  // reached through the mesh refs inside useFrame -- never a captured hook
  // value -- which is the pattern the React-19 immutability/refs lint rules
  // require (mutating a memo'd array or reading ref.current in JSX both trip
  // them). `basePositions`/`velocities`/`nodeColors` are read-only after
  // construction; the mutated buffers live inside the geometries.
  const { pointsGeometry, linesGeometry, basePositions, velocities, nodeColors } = useMemo(() => {
    const rng = makeRng(90210);
    const basePositions = new Float32Array(NODE_COUNT * 3);
    const velocities = new Float32Array(NODE_COUNT * 3);
    const nodeColors = new Float32Array(NODE_COUNT * 3);
    const palette = [
      new THREE.Color("#22d3ee"),
      new THREE.Color("#8b5cf6"),
      new THREE.Color("#ff5d8f"),
      new THREE.Color("#38bdf8"),
      new THREE.Color("#facc15"),
    ];
    for (let i = 0; i < NODE_COUNT; i++) {
      const i3 = i * 3;
      basePositions[i3] = (rng() - 0.5) * FIELD * 2;
      basePositions[i3 + 1] = (rng() - 0.5) * FIELD * 1.2;
      basePositions[i3 + 2] = (rng() - 0.5) * FIELD * 2;
      velocities[i3] = (rng() - 0.5) * 0.6;
      velocities[i3 + 1] = (rng() - 0.5) * 0.4;
      velocities[i3 + 2] = (rng() - 0.5) * 0.6;
      const c = palette[i % palette.length];
      nodeColors[i3] = c.r;
      nodeColors[i3 + 1] = c.g;
      nodeColors[i3 + 2] = c.b;
    }

    const pointsGeometry = new THREE.BufferGeometry();
    pointsGeometry.setAttribute("position", new THREE.BufferAttribute(basePositions.slice(), 3));
    pointsGeometry.setAttribute("color", new THREE.BufferAttribute(nodeColors, 3));

    // Line buffers sized for the worst case (every pair connected) so the
    // per-frame rebuild never reallocates -- we only move the draw range.
    const linesGeometry = new THREE.BufferGeometry();
    linesGeometry.setAttribute(
      "position",
      new THREE.BufferAttribute(new Float32Array(MAX_LINKS * 2 * 3), 3)
    );
    linesGeometry.setAttribute(
      "color",
      new THREE.BufferAttribute(new Float32Array(MAX_LINKS * 2 * 3), 3)
    );

    return { pointsGeometry, linesGeometry, basePositions, velocities, nodeColors };
  }, []);

  useFrame((state) => {
    const t = state.clock.elapsedTime;
    const pointsGeom = pointsRef.current?.geometry;
    const linesGeom = linesRef.current?.geometry;
    if (!pointsGeom || !linesGeom) return;

    const livePositions = (pointsGeom.attributes.position as THREE.BufferAttribute)
      .array as Float32Array;
    const linePositions = (linesGeom.attributes.position as THREE.BufferAttribute)
      .array as Float32Array;
    const lineColors = (linesGeom.attributes.color as THREE.BufferAttribute).array as Float32Array;

    // Drift each node on a gentle bounded sine orbit around its base point --
    // it always returns near where it started, so pairs repeatedly drift
    // together and apart ("reaching again to the same space").
    for (let i = 0; i < NODE_COUNT; i++) {
      const i3 = i * 3;
      livePositions[i3] = basePositions[i3] + Math.sin(t * velocities[i3] + i) * 2.2;
      livePositions[i3 + 1] = basePositions[i3 + 1] + Math.cos(t * velocities[i3 + 1] + i) * 1.5;
      livePositions[i3 + 2] =
        basePositions[i3 + 2] + Math.sin(t * velocities[i3 + 2] + i * 0.7) * 2.2;
    }
    (pointsGeom.attributes.position as THREE.BufferAttribute).needsUpdate = true;

    // Rebuild the connection lines: one segment per pair currently within
    // LINK_DISTANCE, brightness scaled by how close they are.
    let seg = 0;
    for (let a = 0; a < NODE_COUNT; a++) {
      const a3 = a * 3;
      for (let b = a + 1; b < NODE_COUNT; b++) {
        const b3 = b * 3;
        const dx = livePositions[a3] - livePositions[b3];
        const dy = livePositions[a3 + 1] - livePositions[b3 + 1];
        const dz = livePositions[a3 + 2] - livePositions[b3 + 2];
        const dist = Math.sqrt(dx * dx + dy * dy + dz * dz);
        if (dist > LINK_DISTANCE) continue;

        const strength = 1 - dist / LINK_DISTANCE; // 0 at threshold, 1 touching
        const o = seg * 6;
        linePositions[o] = livePositions[a3];
        linePositions[o + 1] = livePositions[a3 + 1];
        linePositions[o + 2] = livePositions[a3 + 2];
        linePositions[o + 3] = livePositions[b3];
        linePositions[o + 4] = livePositions[b3 + 1];
        linePositions[o + 5] = livePositions[b3 + 2];
        // Blend the two endpoints' colors, scaled by proximity so distant
        // links are faint and near-touching links glow.
        for (let k = 0; k < 2; k++) {
          const src = (k === 0 ? a : b) * 3;
          const co = o + k * 3;
          lineColors[co] = nodeColors[src] * strength;
          lineColors[co + 1] = nodeColors[src + 1] * strength;
          lineColors[co + 2] = nodeColors[src + 2] * strength;
        }
        seg++;
      }
    }
    linesGeom.setDrawRange(0, seg * 2);
    (linesGeom.attributes.position as THREE.BufferAttribute).needsUpdate = true;
    (linesGeom.attributes.color as THREE.BufferAttribute).needsUpdate = true;
  });

  return (
    <group position={[0, 0, -2]}>
      <points ref={pointsRef} geometry={pointsGeometry}>
        <pointsMaterial
          size={0.5}
          sizeAttenuation
          vertexColors
          transparent
          opacity={0.95}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </points>
      <lineSegments ref={linesRef} geometry={linesGeometry}>
        <lineBasicMaterial
          vertexColors
          transparent
          opacity={0.65}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </lineSegments>
    </group>
  );
}

export function GalaxyField() {
  return (
    <group>
      <GalaxyDisc />
      <ConstellationNodes />
    </group>
  );
}
