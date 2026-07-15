"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useFrame, type ThreeEvent } from "@react-three/fiber";
import { Html, Line } from "@react-three/drei";
import * as THREE from "three";

import { DEPARTMENT_HUB_ROLE, PIPELINE_ORDER } from "@/lib/orgTopology";
import { useOrgStore } from "@/store/orgStore";
import type { AgentStatusValue, OrgEvent } from "@/types";

import { useOrgGraphLayout, type GraphNode } from "./useOrgGraphLayout";

/**
 * Live, real-time force-directed organization graph. Node color is the
 * agent's real status (see STATUS_COLOR); node size reflects real recent
 * workload (its count of `agent_started` events still in the store's
 * capped event buffer, not a fabricated metric). Every `task_delegated`
 * event spawns a small particle that travels from the emitting
 * department's hub node to the *next* department's hub (per
 * PIPELINE_ORDER -- see useOrgGraphLayout's docstring on why that
 * inference is principled, not fabricated) over ~1.1s, then disappears --
 * "tasks travel across edges as animated particles" driven by real
 * handoff events, never a timer loop running independent of them.
 */

const STATUS_COLOR: Record<AgentStatusValue, string> = {
  idle: "#3b82f6",
  executing: "#f97316",
  completed: "#22c55e",
  needs_review: "#ef4444",
};
const WAITING_COLOR = "#a855f7";

interface Pulse {
  id: string;
  from: [number, number, number];
  to: [number, number, number];
  startedAt: number;
  duration: number;
}

function nextDepartmentAfter(department: string | null): string | null {
  if (!department) return null;
  const index = PIPELINE_ORDER.indexOf(department);
  if (index === -1 || index === PIPELINE_ORDER.length - 1) return null;
  return PIPELINE_ORDER[index + 1];
}

function AgentNode({
  node,
  waiting,
  workload,
  onSelect,
}: {
  node: GraphNode;
  waiting: boolean;
  workload: number;
  onSelect: (department: string) => void;
}) {
  const meshRef = useRef<THREE.Mesh>(null);
  const [hovered, setHovered] = useState(false);

  const baseRadius = node.isHub ? 0.32 : 0.22;
  const radius = baseRadius + Math.min(0.22, workload * 0.045);
  const color = waiting ? WAITING_COLOR : STATUS_COLOR[node.agent.status];

  useFrame((state) => {
    const mesh = meshRef.current;
    if (!mesh) return;
    const pulse = node.agent.status === "executing" ? 1 + Math.sin(state.clock.elapsedTime * 5) * 0.08 : 1;
    const hoverBoost = hovered ? 1.15 : 1;
    mesh.scale.setScalar(pulse * hoverBoost);
  });

  return (
    <group position={[node.x, node.y, node.z]}>
      <mesh
        ref={meshRef}
        onPointerOver={(event: ThreeEvent<PointerEvent>) => {
          event.stopPropagation();
          setHovered(true);
          document.body.style.cursor = "pointer";
        }}
        onPointerOut={(event: ThreeEvent<PointerEvent>) => {
          event.stopPropagation();
          setHovered(false);
          document.body.style.cursor = "auto";
        }}
        onClick={(event: ThreeEvent<MouseEvent>) => {
          event.stopPropagation();
          onSelect(node.agent.department);
        }}
      >
        <sphereGeometry args={[radius, 24, 24]} />
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={node.agent.status === "executing" ? 1.1 : 0.45}
          roughness={0.3}
          metalness={0.4}
        />
      </mesh>

      {(hovered || node.isHub) && (
        <Html distanceFactor={9} center position={[0, radius + 0.35, 0]} occlude>
          <div
            className="hud-label pointer-events-none whitespace-nowrap rounded border border-accent-cyan/30 bg-void/85 px-2 py-1 text-[9px] text-text-primary shadow"
            style={{ boxShadow: "var(--glow-cyan)" }}
          >
            <span className="font-semibold">{node.agent.role}</span>
            {hovered && (
              <span className="ml-1.5 normal-case tracking-normal text-text-muted">
                {node.agent.status}
                {node.agent.last_confidence != null && ` · ${node.agent.last_confidence.toFixed(2)}`}
              </span>
            )}
          </div>
        </Html>
      )}
    </group>
  );
}

/** Owns its own per-frame position update via a mesh ref (the standard
 * R3F pattern -- mutate the object directly in useFrame, never React
 * state/props, so this doesn't force any component to re-render every
 * frame just to animate one traveling dot). */
function TravelingPulse({ pulse }: { pulse: Pulse }) {
  const meshRef = useRef<THREE.Mesh>(null);

  useFrame(() => {
    const mesh = meshRef.current;
    if (!mesh) return;
    const t = Math.min(1, (performance.now() - pulse.startedAt) / pulse.duration);
    const eased = t * t * (3 - 2 * t); // smoothstep
    mesh.position.set(
      THREE.MathUtils.lerp(pulse.from[0], pulse.to[0], eased),
      THREE.MathUtils.lerp(pulse.from[1], pulse.to[1], eased),
      THREE.MathUtils.lerp(pulse.from[2], pulse.to[2], eased)
    );
  });

  return (
    <mesh ref={meshRef} position={pulse.from}>
      <sphereGeometry args={[0.11, 12, 12]} />
      <meshBasicMaterial color="#22d3ee" toneMapped={false} />
    </mesh>
  );
}

export function OrgGraph() {
  const router = useRouter();
  const { nodes, edges, nodesById } = useOrgGraphLayout();
  const activeDepartment = useOrgStore((state) => state.activeDepartment);
  const events = useOrgStore((state) => state.events);

  const waitingDepartments = useMemo(() => {
    if (!activeDepartment) return new Set<string>();
    const index = PIPELINE_ORDER.indexOf(activeDepartment);
    if (index === -1) return new Set<string>();
    return new Set(PIPELINE_ORDER.slice(index + 1));
  }, [activeDepartment]);

  const workloadByRole = useMemo(() => {
    const counts = new Map<string, number>();
    for (const event of events) {
      if (event.type === "agent_started" && event.agent_role) {
        counts.set(event.agent_role, (counts.get(event.agent_role) ?? 0) + 1);
      }
    }
    return counts;
  }, [events]);

  const [pulses, setPulses] = useState<Pulse[]>([]);

  return (
    <group>
      {edges.map((edge, index) => {
        const source = nodesById.get(edge.source);
        const target = nodesById.get(edge.target);
        if (!source || !target) return null;
        return (
          <Line
            key={`${edge.source}-${edge.target}-${index}`}
            points={[
              [source.x, source.y, source.z],
              [target.x, target.y, target.z],
            ]}
            color={edge.kind === "pipeline" ? "#22d3ee" : "#626c8f"}
            lineWidth={edge.kind === "pipeline" ? 1.6 : 1}
            transparent
            opacity={edge.kind === "pipeline" ? 0.5 : 0.25}
          />
        );
      })}

      {nodes
        .filter((node) => node.agent.role !== DEPARTMENT_HUB_ROLE.Executive)
        .map((node) => (
          <AgentNode
            key={node.id}
            node={node}
            waiting={waitingDepartments.has(node.agent.department)}
            workload={workloadByRole.get(node.id) ?? 0}
            onSelect={(department) => router.push(`/department/${department}`)}
          />
        ))}

      <PulseLayer pulses={pulses} setPulses={setPulses} events={events} nodesById={nodesById} />
    </group>
  );
}

/** Watches the event log for task_delegated handoffs and turns each into a
 * transient traveling pulse -- pure event-driven, no polling/timer loop
 * independent of real events. */
function PulseLayer({
  pulses,
  setPulses,
  events,
  nodesById,
}: {
  pulses: Pulse[];
  setPulses: React.Dispatch<React.SetStateAction<Pulse[]>>;
  events: OrgEvent[];
  nodesById: Map<string, GraphNode>;
}) {
  const lastHandledIdRef = useRef<string | null>(null);

  useEffect(() => {
    if (events.length === 0 || nodesById.size === 0) return;
    const lastEvent = events[events.length - 1];
    if (lastEvent.id === lastHandledIdRef.current) return;
    lastHandledIdRef.current = lastEvent.id;
    if (lastEvent.type !== "task_delegated" || !lastEvent.department) return;

    const nextDept = nextDepartmentAfter(lastEvent.department);
    if (!nextDept) return;

    const fromNode = [...nodesById.values()].find(
      (n) => n.agent.department === lastEvent.department && n.isHub
    );
    const toNode = [...nodesById.values()].find((n) => n.agent.department === nextDept && n.isHub);
    if (!fromNode || !toNode) return;

    const pulse: Pulse = {
      id: lastEvent.id,
      from: [fromNode.x, fromNode.y, fromNode.z],
      to: [toNode.x, toNode.y, toNode.z],
      startedAt: performance.now(),
      duration: 1100,
    };
    setPulses((current) => [...current, pulse]);
    setTimeout(() => {
      setPulses((current) => current.filter((p) => p.id !== pulse.id));
    }, pulse.duration + 50);
  }, [events, nodesById, setPulses]);

  return (
    <>
      {pulses.map((pulse) => (
        <TravelingPulse key={pulse.id} pulse={pulse} />
      ))}
    </>
  );
}
