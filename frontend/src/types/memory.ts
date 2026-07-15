/**
 * Mirrors aio.models.memory.MemoryEntry exactly -- the durable
 * organizational-memory records the pipeline writes via MemoryService
 * (see src/aio/memory/recording.py). Sourced only from GET /memory-entries;
 * nothing here is synthesized on the client.
 */
export type MemoryType =
  | "research_finding"
  | "architectural_decision"
  | "lesson_learned"
  | "reusable_component"
  | "risk";

export interface MemoryMetadata {
  tags: string[];
  source_agent: string | null;
  references: string[];
  extra: Record<string, unknown>;
}

export interface MemoryEntry {
  id: string;
  project_id: string | null;
  title: string;
  type: MemoryType;
  summary: string;
  department: string;
  owner: string;
  confidence: number;
  created_at: string;
  metadata: MemoryMetadata;
}
