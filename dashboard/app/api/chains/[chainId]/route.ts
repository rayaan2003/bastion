import { NextRequest, NextResponse } from "next/server";
import { listChainLinks } from "@/lib/chains";
import { requireApiKey } from "@/lib/credentials";

// A chain's stored hashes, for `bastion verify-audit --dashboard-url` to
// compare with the SDK's local log. Paged by seq: one long-running agent
// can write a long chain.
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ chainId: string }> }
) {
  const unauthorized = requireApiKey(request);
  if (unauthorized) return unauthorized;

  const { chainId } = await params;
  const afterSeq = Number(new URL(request.url).searchParams.get("after_seq") ?? -1);
  if (!Number.isInteger(afterSeq)) {
    return NextResponse.json({ error: "after_seq must be an integer" }, { status: 400 });
  }
  return NextResponse.json(await listChainLinks(chainId, afterSeq));
}
