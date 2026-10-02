import { NextRequest, NextResponse } from "next/server";
import { requireApiKey } from "@/lib/credentials";
import { createApproval, listApprovals, ApprovalStatus } from "@/lib/approvals";

export async function POST(request: NextRequest) {
  const unauthorized = requireApiKey(request);
  if (unauthorized) return unauthorized;

  const body = await request.json();

  const { tool_name, args, reason } = body;
  if (!tool_name) {
    return NextResponse.json({ error: "tool_name is required" }, { status: 400 });
  }

  const approval = await createApproval({
    tool_name,
    args: args ?? {},
    reason: reason ?? "",
  });

  return NextResponse.json(approval, { status: 201 });
}

export async function GET(request: NextRequest) {
  const unauthorized = requireApiKey(request);
  if (unauthorized) return unauthorized;

  const { searchParams } = new URL(request.url);
  const status = searchParams.get("status") as ApprovalStatus | null;
  const approvals = await listApprovals(status ?? undefined);
  return NextResponse.json({ approvals });
}
