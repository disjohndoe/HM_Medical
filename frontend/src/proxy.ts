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

  // Validate httpOnly cookie presence — actual JWT validation happens on the backend
  // The access_token cookie is set by the backend as httpOnly, so JavaScript cannot forge it.
  // This provides server-side route protection without needing the JWT secret on the frontend.
  const hasAccessToken = request.cookies.has("access_token");
  const hasSession = request.cookies.get("has_session")?.value === "1";
  const isAuthenticated = hasAccessToken || hasSession;

  if (!isPublicRoute && !isAuthenticated) {
    const loginUrl = new URL("/prijava", request.url);
    return NextResponse.redirect(loginUrl);
  }

  if (isPublicRoute && isAuthenticated) {
    const dashboardUrl = new URL("/", request.url);
    return NextResponse.redirect(dashboardUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.png$).*)"],
};
