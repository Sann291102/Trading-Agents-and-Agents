/**
 * The session token lives in two places: the Zustand store (read by
 * `fetchJSON` to attach `Authorization: Bearer <token>` to every API call)
 * and this cookie (read by `middleware.ts`, which runs on the Edge runtime
 * and has no access to client-side JS state). Both are written/cleared
 * together via `useOrgStore.getState().setToken(...)` -- this module only
 * owns the cookie read/write mechanics, not when they happen.
 */

export const AUTH_COOKIE_NAME = "aio_token";

const THIRTY_DAYS_SECONDS = 30 * 24 * 60 * 60;

export function readAuthCookie(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(
    new RegExp(`(?:^|; )${AUTH_COOKIE_NAME}=([^;]*)`)
  );
  return match ? decodeURIComponent(match[1]) : null;
}

export function writeAuthCookie(token: string): void {
  if (typeof document === "undefined") return;
  // 30 days, matching the backend's SESSION_TTL (aio/auth/service.py).
  document.cookie = `${AUTH_COOKIE_NAME}=${encodeURIComponent(token)}; path=/; max-age=${THIRTY_DAYS_SECONDS}; SameSite=Lax`;
}

export function clearAuthCookie(): void {
  if (typeof document === "undefined") return;
  document.cookie = `${AUTH_COOKIE_NAME}=; path=/; max-age=0`;
}
