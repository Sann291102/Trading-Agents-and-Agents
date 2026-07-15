"use client";

import { useMemo } from "react";
import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation } from "d3-force";

import { DEPARTMENT_HUB_ROLE, PIPELINE_ORDER } from "@/lib/orgTopology";
import { useOrgStore } from "@/store/orgStore";
import type { AgentInfo } from "@/types";

export interface GraphNode {
  id: string;
  agent: AgentInfo;
  x: number;
  y: number;
  z: number;
  isHub: boolean;
}

export interface GraphEdge {
  source: string;
  target: string;
  kind: "pipeline" | "department";
}

export interface OrgGraphLayout {
  nodes: GraphNode[];
  edges: GraphEdge[];
  nodesById: Map<string, GraphNode>;
  /** Centroid of each department's nodes -- what CinematicCamera flies to. */
  departmentCentroids: Map<string, [number, number, number]>;
}

interface SimNode {
  id: string;
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
  fx?: number | null;
  fy?: number | null;
  index?: number;
}

/**
 * Real-time force-directed layout over the actual agent roster (`GET
 * /agents` seeded + live SSE updates via useOrgStore) -- recomputed
 * whenever the roster changes (a new agent/department appearing needs no
 * frontend redesign, just a fresh simulation run over the new node set).
 * d3-force is 2D; results are placed on the X/Z plane with a small
 * per-department Y offset for visual depth, a standard trick for using a
 * 2D force layout inside a 3D scene.
 *
 * Edges are derived from DEPARTMENT_HUB_ROLE + PIPELINE_ORDER (see
 * lib/orgTopology.ts) rather than any per-agent hardcoded list, so a new
 * agent joining an *existing* department automatically gets a spoke to its
 * department's hub with no changes here.
 */
export function useOrgGraphLayout(): OrgGraphLayout {
  const agents = useOrgStore((state) => state.agents);

  return useMemo(() => {
    const roster = Object.values(agents);
    if (roster.length === 0) {
      return { nodes: [], edges: [], nodesById: new Map(), departmentCentroids: new Map() };
    }

    // Guards every edge below against a roster that's momentarily partial
    // (e.g. mid-reconnect after an API restart, or an SSE update landing
    // before a full /agents refresh): an edge naming a role not currently
    // in the roster would otherwise reach d3-force, whose forceLink throws
    // an uncaught "node not found" and crashes the whole scene.
    const rosterByRole = new Map(roster.map((a) => [a.role, a]));
    const hasRole = (role: string | undefined): role is string =>
      !!role && rosterByRole.has(role);

    const edges: GraphEdge[] = [];
    for (let i = 0; i < PIPELINE_ORDER.length - 1; i++) {
      const fromHub = DEPARTMENT_HUB_ROLE[PIPELINE_ORDER[i]];
      const toHub = DEPARTMENT_HUB_ROLE[PIPELINE_ORDER[i + 1]];
      if (hasRole(fromHub) && hasRole(toHub)) {
        edges.push({ source: fromHub, target: toHub, kind: "pipeline" });
      }
    }
    // Final review closes the loop back to Executive.
    const executiveHub = DEPARTMENT_HUB_ROLE.Executive;
    const engineeringHub = DEPARTMENT_HUB_ROLE.Engineering;
    if (
      hasRole(executiveHub) &&
      hasRole(engineeringHub) &&
      executiveHub !== engineeringHub
    ) {
      edges.push({ source: engineeringHub, target: executiveHub, kind: "pipeline" });
    }

    for (const agent of roster) {
      const hub = DEPARTMENT_HUB_ROLE[agent.department];
      if (hub && hub !== agent.role && rosterByRole.has(hub)) {
        edges.push({ source: agent.role, target: hub, kind: "department" });
      }
    }

    // The Executive AI hub is fixed at the true origin: it's rendered as
    // the NeuralCore, not a graph sphere (see OrgGraph), so every edge
    // that terminates on it must anchor exactly where the core sits.
    const executiveRole = DEPARTMENT_HUB_ROLE.Executive;
    const simNodes: SimNode[] = roster.map((a) => {
      const node: SimNode = { id: a.role };
      if (a.role === executiveRole) {
        node.fx = 0;
        node.fy = 0;
      }
      return node;
    });
    const simulation = forceSimulation<SimNode>(simNodes)
      .force(
        "link",
        forceLink<SimNode, GraphEdge & { source: string; target: string }>(edges)
          .id((n) => n.id)
          .distance((edge) => (edge.kind === "pipeline" ? 5.5 : 2.6))
          .strength(0.9)
      )
      .force("charge", forceManyBody().strength(-14))
      .force("center", forceCenter(0, 0))
      .force("collide", forceCollide(1.4))
      .stop();

    for (let i = 0; i < 300; i++) simulation.tick();

    const departmentYOffset: Record<string, number> = {
      Executive: 0,
      Research: 1.1,
      Product: -0.6,
      Engineering: -1.6,
    };

    const nodes: GraphNode[] = simNodes.map((simNode) => {
      const agent = rosterByRole.get(simNode.id)!;
      return {
        id: simNode.id,
        agent,
        x: simNode.x ?? 0,
        y: departmentYOffset[agent.department] ?? 0,
        z: simNode.y ?? 0,
        isHub: DEPARTMENT_HUB_ROLE[agent.department] === simNode.id,
      };
    });

    const nodesById = new Map(nodes.map((n) => [n.id, n]));

    const departmentCentroids = new Map<string, [number, number, number]>();
    const sums = new Map<string, [number, number, number, number]>();
    for (const node of nodes) {
      const entry = sums.get(node.agent.department) ?? [0, 0, 0, 0];
      entry[0] += node.x;
      entry[1] += node.y;
      entry[2] += node.z;
      entry[3] += 1;
      sums.set(node.agent.department, entry);
    }
    for (const [department, [sx, sy, sz, count]] of sums) {
      departmentCentroids.set(department, [sx / count, sy / count, sz / count]);
    }

    return { nodes, edges, nodesById, departmentCentroids };
  }, [agents]);
}
