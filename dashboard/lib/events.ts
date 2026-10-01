import { getDb } from "./db";

export interface AuditEvent {
  id: string;
  timestamp: number;
  session_id: string;
  tool_name: string;
  args: Record<string, unknown>;
  action: string;
  reason: string;
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
}

export async function insertEvent(event: NewAuditEvent): Promise<void> {
  const db = await getDb();
  await db.query(
    `INSERT INTO audit_events (id, "timestamp", session_id, tool_name, args, action, reason)
     VALUES ($1, $2, $3, $4, $5, $6, $7)
     ON CONFLICT (id) DO NOTHING`,
    [
      event.id,
      event.timestamp,
      event.session_id,
      event.tool_name,
      JSON.stringify(event.args),
      event.action,
      event.reason,
    ]
  );
}

export interface EventFilters {
  toolName?: string;
  action?: string;
  sessionId?: string;
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

  const where = conditions.length > 0 ? `WHERE ${conditions.join(" AND ")}` : "";
  const limit = filters.limit ?? 100;
  params.push(limit);

  const result = await db.query<AuditEvent>(
    `SELECT * FROM audit_events ${where} ORDER BY "timestamp" DESC LIMIT $${params.length}`,
    params
  );
  return result.rows;
}
