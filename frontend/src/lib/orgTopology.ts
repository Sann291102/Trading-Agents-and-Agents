/**
 * The one piece of pipeline-shape knowledge intentionally duplicated on
 * the frontend. `GET /agents` reports each agent's role/department/status,
 * but the *order* departments execute in is Python control flow inside
 * `orchestration/graph.py`, not data any endpoint exposes. The backend's
 * AgentStatusTracker deliberately does not invent a "waiting" status for
 * exactly this reason (see aio/agents/registry.py's docstring) -- the
 * frontend, which already needs to render the live workflow diagram, is
 * where that derivation belongs.
 *
 * If the backend graph's shape changes (new department inserted, edges
 * reordered), update PIPELINE_ORDER/DEPARTMENTS to match -- everything
 * else (which agents belong to which department, current status per
 * agent) still comes from real `/agents` + SSE data, never hardcoded here.
 */

export interface DepartmentInfo {
  id: string;
  label: string;
}

/** Matches the `department` field every agent reports, in the order the
 * orchestration graph reaches them: Executive -> Research (parallel
 * fan-out/fan-in across 4 specialists) -> Product -> Engineering ->
 * Executive (final review). */
export const DEPARTMENTS: DepartmentInfo[] = [
  { id: "Executive", label: "Executive" },
  { id: "Research", label: "Research & Planning" },
  { id: "Product", label: "Product" },
  { id: "Engineering", label: "Engineering" },
];

export const PIPELINE_ORDER: readonly string[] = [
  "Executive",
  "Research",
  "Product",
  "Engineering",
];

/**
 * Which agent is each department's graph "hub" -- the one every other
 * agent in that department connects to, and which connects onward to the
 * next department's hub in PIPELINE_ORDER. Used by OrgGraph to build edges
 * generically: a new agent added to an *existing* department (e.g. a
 * second QA agent later) needs zero topology changes here, since it just
 * joins its department's existing hub as another spoke. Only a genuinely
 * new department needs a one-line addition -- the same documented
 * exception PIPELINE_ORDER already accepts.
 */
export const DEPARTMENT_HUB_ROLE: Record<string, string> = {
  Executive: "Executive AI (CEO)",
  Research: "Research Coordinator",
  Product: "Product Manager",
  Engineering: "Backend Lead",
};

/** Given the department the live workflow most recently touched, which
 * departments have the pipeline not reached *yet* this run (rendered as
 * "waiting" / purple) -- a department already visited counts as reached
 * even if the pipeline has since moved on (e.g. Research is not "waiting"
 * again once Engineering is active). */
export function departmentsWaitingAfter(activeDepartment: string | null): Set<string> {
  if (!activeDepartment) return new Set();
  const index = PIPELINE_ORDER.indexOf(activeDepartment);
  if (index === -1) return new Set();
  return new Set(PIPELINE_ORDER.slice(index + 1));
}

/**
 * Mission Timeline stages per the product spec. Several (Design, Testing,
 * Deployment, Monitoring) have no implementing department yet -- shown
 * dimmed/"not yet implemented" rather than faked, consistent with every
 * other honest-about-scope choice in this project. `eventTypes` lists
 * which real OrgEvent types mark a stage reached.
 */
export interface MissionStage {
  id: string;
  label: string;
  implemented: boolean;
  eventTypes: string[];
}

export const MISSION_STAGES: MissionStage[] = [
  { id: "objective_received", label: "Objective Received", implemented: true, eventTypes: ["task_delegated"] },
  { id: "research", label: "Research", implemented: true, eventTypes: ["research_complete"] },
  { id: "planning", label: "Planning", implemented: true, eventTypes: ["approval_granted"] },
  { id: "design", label: "Design", implemented: false, eventTypes: [] },
  { id: "development", label: "Development", implemented: true, eventTypes: ["review_requested"] },
  { id: "testing", label: "Testing", implemented: false, eventTypes: [] },
  { id: "deployment", label: "Deployment", implemented: false, eventTypes: ["deployment_started"] },
  { id: "monitoring", label: "Monitoring", implemented: false, eventTypes: [] },
  { id: "memory_update", label: "Memory Update", implemented: true, eventTypes: ["memory_updated", "knowledge_added"] },
];
