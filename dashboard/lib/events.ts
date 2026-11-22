import { getDb } from "./db";

export interface AuditEvent {
  id: string;
  timestamp: number;
  session_id: string;
  tool_name: string;
  args: Record<string, unknown>;
  action: string;
  reason: string;
  call_id: string | null;
  approver: string | null;
  chain_id: string | null;
  seq: number | null;
  prev_hash: string | null;
  hash: string | null;
  created_at: string;
}

export interface NewAuditEvent {
  id: string;
  timestamp: number;
  session_id: string;
  tool_name: string;
  args: Record<string, unknown>;
  action: string;
  reason: string;
  call_id: string | null;
  approver: string | null;
  chain: ChainLink | null;
}

export interface ChainLink {
  chain_id: string;
  seq: number;
  prev_hash: string;
  hash: string;
}

// Returns false if another event already holds this event's place in its
// chain. Re-sending the same event (same id) is not a conflict.
export async function insertEvent(event: NewAuditEvent): Promise<boolean> {
  const db = await getDb();
  try {
    await db.query(
      `INSERT INTO audit_events
         (id, "timestamp", session_id, tool_name, args, action, reason, call_id, approver,
          chain_id, seq, prev_hash, hash)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
       ON CONFLICT (id) DO NOTHING`,
      [
        event.id,
        event.timestamp,
        event.session_id,
        event.tool_name,
        JSON.stringify(event.args),
        event.action,
        event.reason,
        event.call_id,
        event.approver,
        event.chain?.chain_id ?? null,
        event.chain?.seq ?? null,
        event.chain?.prev_hash ?? null,
        event.chain?.hash ?? null,
      ]
    );
  } catch (error) {
    const { code, constraint } = error as { code?: string; constraint?: string };
    if (code === "23505" && constraint === "idx_audit_events_chain_seq") return false;
    throw error;
  }
  return true;
}

export interface EventFilters {
  toolName?: string;
  action?: string;
  sessionId?: string;
  callId?: string;
  chainId?: string;
  limit?: number;
}

export async function listEvents(filters: EventFilters = {}): Promise<AuditEvent[]> {
  const db = await getDb();
  const conditions: string[] = [];
  const params: unknown[] = [];

  if (filters.toolName) {
    params.push(filters.toolName);
    conditions.push(`tool_name = $${params.length}`);
  }
  if (filters.action) {
    params.push(filters.action);
    conditions.push(`action = $${params.length}`);
  }
  if (filters.sessionId) {
    params.push(filters.sessionId);
    conditions.push(`session_id = $${params.length}`);
  }
  if (filters.callId) {
    params.push(filters.callId);
    conditions.push(`call_id = $${params.length}`);
  }
  if (filters.chainId) {
    params.push(filters.chainId);
    conditions.push(`chain_id = $${params.length}`);
  }

  const where = conditions.length > 0 ? `WHERE ${conditions.join(" AND ")}` : "";
  const limit = filters.limit ?? 100;
  params.push(limit);

  const result = await db.query<AuditEvent>(
    `SELECT * FROM audit_events ${where} ORDER BY "timestamp" DESC LIMIT $${params.length}`,
    params
  );
  return result.rows;
}
