import { SignJWT, jwtVerify } from "jose";

// Edge-runtime-safe (no node:crypto) - this file is imported by
// middleware.ts, which runs on the Edge runtime by default. Password and
// API key checks (which do use node:crypto) live in lib/credentials.ts
// instead, imported only by Node-runtime route handlers.

export const SESSION_COOKIE_NAME = "agentguard_session";
const SESSION_TTL_SECONDS = 60 * 60 * 24 * 7; // 7 days

function getSecret(): Uint8Array {
  const secret = process.env.DASHBOARD_SESSION_SECRET;
  if (!secret) {
    throw new Error("DASHBOARD_SESSION_SECRET environment variable is required");
  }
  return new TextEncoder().encode(secret);
}

export async function createSessionToken(): Promise<string> {
  return new SignJWT({ sub: "admin" })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime(`${SESSION_TTL_SECONDS}s`)
    .sign(getSecret());
}

export async function verifySessionToken(token: string): Promise<boolean> {
  try {
    await jwtVerify(token, getSecret());
    return true;
  } catch {
    return false;
  }
}
