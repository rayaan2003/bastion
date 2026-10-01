import { NextRequest, NextResponse } from "next/server";
import { decideApproval } from "@/lib/approvals";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const body = await request.json();
  const { decision } = body;

  if (decision !== "approved" && decision !== "denied") {
    return NextResponse.json(
      { error: "decision must be 'approved' or 'denied'" },
      { status: 400 }
    );
  }

  const updated = await decideApproval(id, decision);
  if (!updated) {
    return NextResponse.json(
      { error: "approval not found, or already decided" },
      { status: 404 }
    );
  }

  return NextResponse.json(updated);
}
