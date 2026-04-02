import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const publicPaths = ["/prijava", "/registracija"];

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Skip static files and API routes
  if (
    pathname.startsWith("/_next") ||
    pathname.startsWith("/api") ||
    pathname.includes(".")
  ) {
    return NextResponse.next();
  }

  const isPublicRoute = publicPaths.some(
    (path) => pathname === path || pathname.startsWith(path + "/")
  );

  // Check for access_token cookie or rely on client-side localStorage check
  // Since tokens are in localStorage (client-side), we use a lightweight
  // session marker cookie set by the auth flow
  const hasSession = request.cookies.get("has_session")?.value === "1";

  if (!isPublicRoute && !hasSession) {
    const loginUrl = new URL("/prijava", request.url);
    return NextResponse.redirect(loginUrl);
  }

  if (isPublicRoute && hasSession) {
    const dashboardUrl = new URL("/", request.url);
    return NextResponse.redirect(dashboardUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.png$).*)"],
};
