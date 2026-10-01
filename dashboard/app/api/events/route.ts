import { NextRequest, NextResponse } from "next/server";
import { insertEvent, listEvents } from "@/lib/events";

export async function POST(request: NextRequest) {
  const body = await request.json();

  const { id, timestamp, session_id, tool_name, args, action, reason } = body;
  if (!id || !session_id || !tool_name || !action) {
    return NextResponse.json(
      { error: "id, session_id, tool_name, and action are required" },
      { status: 400 }
    );
  }

  await insertEvent({
    id,
    timestamp: timestamp ?? Date.now() / 1000,
    session_id,
    tool_name,
    args: args ?? {},
    action,
    reason: reason ?? "",
  });

  return NextResponse.json({ ok: true }, { status: 201 });
}

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const events = await listEvents({
    toolName: searchParams.get("tool_name") ?? undefined,
    action: searchParams.get("action") ?? undefined,
    sessionId: searchParams.get("session_id") ?? undefined,
    limit: searchParams.get("limit") ? Number(searchParams.get("limit")) : undefined,
  });
  return NextResponse.json({ events });
}
