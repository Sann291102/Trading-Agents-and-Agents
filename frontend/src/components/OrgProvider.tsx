"use client";

import { QueryClientProvider, useQuery } from "@tanstack/react-query";
import { useEffect, type ReactNode } from "react";

import { getAgents } from "@/lib/api";
import { queryClient, queryKeys } from "@/lib/queryClient";
import { useOrgEventStream } from "@/lib/useOrgEventStream";
import { useOrgStore } from "@/store/orgStore";

/** Seeds the store with the current agent roster/status on load (so the
 * UI isn't blank before the first live event arrives), then hands off to
 * the live SSE stream for everything after. */
function OrgBootstrap() {
  useOrgEventStream();

  const { data } = useQuery({
    queryKey: queryKeys.agents,
    queryFn: getAgents,
  });

  useEffect(() => {
    if (data) useOrgStore.getState().setAgents(data);
  }, [data]);

  return null;
}

export function OrgProvider({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <OrgBootstrap />
      {children}
    </QueryClientProvider>
  );
}
