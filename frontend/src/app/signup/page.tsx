"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { signup } from "@/lib/api";
import { useOrgStore } from "@/store/orgStore";

const MIN_PASSWORD_LENGTH = 8;

export default function SignupPage() {
  const router = useRouter();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const passwordTooShort = password.length > 0 && password.length < MIN_PASSWORD_LENGTH;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (pending || !username.trim() || password.length < MIN_PASSWORD_LENGTH) return;

    setPending(true);
    setError(null);
    try {
      const result = await signup(username.trim(), password);
      useOrgStore.getState().setToken(result.token);
      router.push("/");
    } catch (err) {
      const message = err instanceof Error ? err.message : "";
      setError(
        message.includes("409") ? "That username is already taken." : "Could not sign up."
      );
      setPending(false);
    }
  }

  return (
    <main className="flex flex-1 items-center justify-center p-4">
      <div className="hud-panel w-full max-w-sm space-y-4 p-6">
        <div>
          <p className="hud-label text-[11px] text-accent-cyan">Mission Control</p>
          <h1 className="mt-1 text-lg font-medium text-text-primary">Create an account</h1>
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
              autoComplete="new-password"
              className="w-full rounded border border-border bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted outline-none focus-visible:border-accent-cyan/50"
            />
            {passwordTooShort && (
              <p className="text-[11px] text-text-muted">
                At least {MIN_PASSWORD_LENGTH} characters.
              </p>
            )}
          </div>

          {error && <p className="text-xs text-status-needs_review">{error}</p>}

          <button
            type="submit"
            disabled={pending || !username.trim() || password.length < MIN_PASSWORD_LENGTH}
            className="w-full rounded bg-accent-blue px-3 py-2 text-sm font-medium text-text-primary transition-opacity disabled:opacity-50"
          >
            {pending ? "Creating account…" : "Sign up"}
          </button>
        </form>

        <p className="text-center text-xs text-text-muted">
          Already have an account?{" "}
          <Link href="/login" className="text-accent-cyan hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </main>
  );
}
