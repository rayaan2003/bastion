import { NextRequest, NextResponse } from "next/server";
import { requireApiKey } from "@/lib/credentials";
import { getCurrentPolicy } from "@/lib/policy";

// GET only - this is what the Python SDK's load_policy_from_dashboard()
// fetches. Editing happens through the /policy page (session-protected
// Server Action), not through this API, so there's no POST here.
export async function GET(request: NextRequest) {
  const unauthorized = requireApiKey(request);
  if (unauthorized) return unauthorized;

  const current = await getCurrentPolicy();
  return NextResponse.json({ yaml_text: current?.yaml_text ?? null });
}
