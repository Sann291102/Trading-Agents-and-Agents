"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import { DepartmentWorkspace } from "@/components/department/DepartmentWorkspace";

/**
 * A Client Component page using `useParams()` rather than the Server
 * Component `params` prop -- sidesteps Next 16's async-params convention
 * entirely, since everything this page needs (live agent status, project
 * detail) is client-side store/query data anyway.
 */
export default function DepartmentPage() {
  const params = useParams<{ departmentId: string }>();
  const departmentId = decodeURIComponent(params.departmentId);

  return (
    <main className="flex-1 overflow-y-auto p-4 md:p-8">
      <div className="mx-auto max-w-4xl space-y-4">
        <Link href="/" className="inline-block text-xs text-text-muted hover:text-text-primary">
          ← Mission Control
        </Link>
        <DepartmentWorkspace departmentId={departmentId} />
      </div>
    </main>
  );
}
