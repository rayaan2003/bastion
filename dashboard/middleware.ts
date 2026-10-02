import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE_NAME, verifySessionToken } from "@/lib/session";

export async function middleware(request: NextRequest) {
  const token = request.cookies.get(SESSION_COOKIE_NAME)?.value;
  const valid = token ? await verifySessionToken(token) : false;

  if (!valid) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("next", request.nextUrl.pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

// /api/* is deliberately not matched here - those routes are for the
// Python SDK (machine-to-machine) and are protected separately by
// requireApiKey() in lib/credentials.ts, not by the browser session cookie.
export const config = {
  matcher: ["/", "/audit/:path*", "/approvals/:path*"],
};
