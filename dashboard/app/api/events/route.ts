import { NextRequest, NextResponse } from "next/server";
import { requireApiKey } from "@/lib/credentials";
import { type ChainLink, insertEvent, listEvents } from "@/lib/events";

// The seq column is a Postgres INTEGER.
const MAX_SEQ = 2 ** 31 - 1;

// SDKs older than the hash chain send none of these fields.
function parseChainLink(body: Record<string, unknown>): ChainLink | null | "invalid" {
  const { chain_id, seq, prev_hash, hash } = body;
  if ([chain_id, seq, prev_hash, hash].every((field) => field === undefined)) return null;
  if (
    typeof chain_id !== "string" ||
    !chain_id ||
    typeof seq !== "number" ||
    !Number.isInteger(seq) ||
    seq < 0 ||
    seq > MAX_SEQ ||
    typeof prev_hash !== "string" ||
    typeof hash !== "string" ||
    !hash
  ) {
    return "invalid";
  }
  return { chain_id, seq, prev_hash, hash };
}

export async function POST(request: NextRequest) {
  const unauthorized = requireApiKey(request);
  if (unauthorized) return unauthorized;

  const body = await request.json();

  const { id, timestamp, session_id, tool_name, args, action, reason, call_id, approver } =
    body;
  if (!id || !session_id || !tool_name || !action) {
    return NextResponse.json(
      { error: "id, session_id, tool_name, and action are required" },
      { status: 400 }
    );
  }
  const chain = parseChainLink(body);
  if (chain === "invalid") {
    return NextResponse.json(
      {
        error:
          "chain_id, seq, prev_hash and hash go together: non-empty chain_id and hash, " +
          "seq a non-negative integer, prev_hash a string",
      },
      { status: 400 }
    );
  }

  const inserted = await insertEvent({
    id,
    timestamp: timestamp ?? Date.now() / 1000,
    session_id,
    tool_name,
    args: args ?? {},
    action,
    reason: reason ?? "",
    call_id: call_id || null,
    approver: approver || null,
    chain,
  });
  if (!inserted) {
    return NextResponse.json(
      { error: `chain ${chain?.chain_id} already has a different event at seq ${chain?.seq}` },
      { status: 409 }
    );
  }

  return NextResponse.json({ ok: true }, { status: 201 });
}

export async function GET(request: NextRequest) {
  const unauthorized = requireApiKey(request);
  if (unauthorized) return unauthorized;

  const { searchParams } = new URL(request.url);
  const events = await listEvents({
    toolName: searchParams.get("tool_name") ?? undefined,
    action: searchParams.get("action") ?? undefined,
    sessionId: searchParams.get("session_id") ?? undefined,
    callId: searchParams.get("call_id") ?? undefined,
    chainId: searchParams.get("chain_id") ?? undefined,
    limit: searchParams.get("limit") ? Number(searchParams.get("limit")) : undefined,
  });
  return NextResponse.json({ events });
}
