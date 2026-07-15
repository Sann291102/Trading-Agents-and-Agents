"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { login } from "@/lib/api";
import { useOrgStore } from "@/store/orgStore";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const next = searchParams.get("next") || "/";

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (pending || !username.trim() || !password) return;

    setPending(true);
    setError(null);
    try {
      const result = await login(username.trim(), password);
      useOrgStore.getState().setToken(result.token);
      router.push(next);
    } catch {
      setError("Invalid username or password.");
      setPending(false);
    }
  }

  return (
    <div className="hud-panel w-full max-w-sm space-y-4 p-6">
      <div>
        <p className="hud-label text-[11px] text-accent-cyan">Mission Control</p>
        <h1 className="mt-1 text-lg font-medium text-text-primary">Sign in</h1>
      </div>

      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="space-y-1">
          <label htmlFor="username" className="text-xs text-text-muted">
            Username
          </label>
          <input
            id="username"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="username"
            className="w-full rounded border border-border bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted outline-none focus-visible:border-accent-cyan/50"
          />
        </div>
        <div className="space-y-1">
          <label htmlFor="password" className="text-xs text-text-muted">
            Password
          </label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
            className="w-full rounded border border-border bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted outline-none focus-visible:border-accent-cyan/50"
          />
        </div>

        {error && <p className="text-xs text-status-needs_review">{error}</p>}

        <button
          type="submit"
          disabled={pending || !username.trim() || !password}
          className="w-full rounded bg-accent-blue px-3 py-2 text-sm font-medium text-text-primary transition-opacity disabled:opacity-50"
        >
          {pending ? "Signing in…" : "Sign in"}
        </button>
      </form>

      <p className="text-center text-xs text-text-muted">
        No account?{" "}
        <Link href="/signup" className="text-accent-cyan hover:underline">
          Sign up
        </Link>
      </p>
    </div>
  );
}

export default function LoginPage() {
  return (
    <main className="flex flex-1 items-center justify-center p-4">
      <Suspense fallback={null}>
        <LoginForm />
      </Suspense>
    </main>
  );
}
