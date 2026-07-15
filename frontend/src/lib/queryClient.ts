import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
  },
});

/** Centralized so every caller invalidates/reads the same key shape. */
export const queryKeys = {
  agents: ["agents"] as const,
  projects: (limit: number) => ["projects", limit] as const,
  project: (id: string) => ["project", id] as const,
  projectFiles: (id: string) => ["project-files", id] as const,
  executionLogs: (limit: number) => ["execution-logs", limit] as const,
  projectSearch: (query: string) => ["project-search", query] as const,
  memoryEntries: (limit: number) => ["memory-entries", limit] as const,
};
