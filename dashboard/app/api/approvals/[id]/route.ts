import { NextRequest, NextResponse } from "next/server";
import { requireApiKey } from "@/lib/credentials";
import { getApproval } from "@/lib/approvals";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const unauthorized = requireApiKey(request);
  if (unauthorized) return unauthorized;

  const { id } = await params;
  const approval = await getApproval(id);
  if (!approval) {
    return NextResponse.json({ error: "not found" }, { status: 404 });
  }
  return NextResponse.json(approval);
}
