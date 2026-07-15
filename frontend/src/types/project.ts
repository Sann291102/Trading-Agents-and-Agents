import type { BusinessRequirementsDocument } from "./product";
import type { ResearchReport } from "./research";

/** Mirrors ProjectResponse in aio/api/main.py. */
export interface ProjectResponse {
  id: string;
  goal: string;
  research_report: ResearchReport | null;
  research_review: string;
  research_approved: boolean;
  business_requirements: BusinessRequirementsDocument | null;
  tech_plan: string;
  review: string;
  approved: boolean;
  preview_url: string | null;
  preview_error: string | null;
}

/** Mirrors the lightweight entries GET /projects returns (for the
 * Knowledge Universe's project-node list). */
export interface ProjectSummary {
  id: string;
  goal: string;
  approved: boolean;
  research_approved: boolean;
  created_at: string;
}

/** Mirrors GET /execution-logs entries. */
export interface ExecutionLogEntry {
  id: string;
  project_id: string | null;
  agent_role: string;
  started_at: string;
  ended_at: string;
  duration_seconds: number;
  confidence: number | null;
  reasoning_summary: string;
  handoff_target: string | null;
  error: string | null;
}
