import { NextResponse, type NextRequest } from "next/server";

import { AUTH_COOKIE_NAME } from "@/lib/authCookie";

const PUBLIC_PATHS = new Set(["/login", "/signup"]);

/**
 * Coarse route gate: redirects to /login when the session cookie is
 * missing. This only checks *presence*, not validity -- there is no DB
 * access from the Edge runtime here, and re-validating on every navigation
 * would add real latency for no benefit, since the backend already
 * re-validates the token on every actual API call (aio/api/main.py's
 * get_current_user returns 401 for an invalid/expired token regardless of
 * what this middleware let through). The cookie is set/cleared alongside
 * the in-memory token by useOrgStore's setToken (see lib/authCookie.ts).
 */
export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (PUBLIC_PATHS.has(pathname)) {
    return NextResponse.next();
  }

  const token = request.cookies.get(AUTH_COOKIE_NAME)?.value;
  if (!token) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
