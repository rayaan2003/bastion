import { createHash, timingSafeEqual } from "node:crypto";
import { NextResponse } from "next/server";

// node:crypto is not available on the Edge runtime, so this file must only
// be imported by Node-runtime code (API routes, the login route) - never
// by middleware.ts. See lib/session.ts for the edge-safe session logic.

function timingSafeStringEqual(a: string, b: string): boolean {
  // Hash both to fixed-length digests first so timingSafeEqual never sees
  // mismatched buffer lengths (which it rejects before any comparison).
  const hashA = createHash("sha256").update(a).digest();
  const hashB = createHash("sha256").update(b).digest();
  return timingSafeEqual(hashA, hashB);
}

export function checkPassword(candidate: string): boolean {
  const expected = process.env.DASHBOARD_PASSWORD;
  if (!expected) {
    throw new Error("DASHBOARD_PASSWORD environment variable is required");
  }
  return timingSafeStringEqual(candidate, expected);
}

function checkApiKey(request: Request): boolean {
  const expected = process.env.DASHBOARD_API_KEY;
  if (!expected) {
    throw new Error("DASHBOARD_API_KEY environment variable is required");
  }
  const header = request.headers.get("authorization") ?? "";
  const match = /^Bearer (.+)$/.exec(header);
  if (!match) return false;
  return timingSafeStringEqual(match[1], expected);
}

/** Call at the top of every /api/* route handler. Returns a 401 response
 * to return immediately if unauthorized, or null if the request may proceed. */
export function requireApiKey(request: Request): NextResponse | null {
  if (!checkApiKey(request)) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  return null;
}
