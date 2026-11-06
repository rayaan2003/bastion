import { randomUUID } from "node:crypto";
import { getDb } from "./db";

export type ApprovalStatus = "pending" | "approved" | "denied";

// Where a decision was made. Not a person: the dashboard has one shared login.
export type DecidedBy = "ui" | "api";

export interface ApprovalRequest {
  id: string;
  tool_name: string;
  args: Record<string, unknown>;
  reason: string;
  status: ApprovalStatus;
  call_id: string | null;
  session_id: string | null;
  decided_by: DecidedBy | null;
  created_at: string;
  responded_at: string | null;
}

export interface NewApprovalRequest {
  tool_name: string;
  args: Record<string, unknown>;
  reason: string;
  call_id: string | null;
  session_id: string | null;
}

export async function createApproval(req: NewApprovalRequest): Promise<ApprovalRequest> {
  const db = await getDb();
  const id = randomUUID();
  const result = await db.query<ApprovalRequest>(
    `INSERT INTO approval_requests (id, tool_name, args, reason, status, call_id, session_id)
     VALUES ($1, $2, $3, $4, 'pending', $5, $6)
     RETURNING *`,
    [id, req.tool_name, JSON.stringify(req.args), req.reason, req.call_id, req.session_id]
  );
  return result.rows[0];
}

export async function getApproval(id: string): Promise<ApprovalRequest | null> {
  const db = await getDb();
  const result = await db.query<ApprovalRequest>(
    `SELECT * FROM approval_requests WHERE id = $1`,
    [id]
  );
  return result.rows[0] ?? null;
}

export async function listApprovals(status?: ApprovalStatus): Promise<ApprovalRequest[]> {
  const db = await getDb();
  if (status) {
    const result = await db.query<ApprovalRequest>(
      `SELECT * FROM approval_requests WHERE status = $1 ORDER BY created_at DESC`,
      [status]
    );
    return result.rows;
  }
  const result = await db.query<ApprovalRequest>(
    `SELECT * FROM approval_requests ORDER BY created_at DESC`
  );
  return result.rows;
}

export async function decideApproval(
  id: string,
  decision: "approved" | "denied",
  decidedBy: DecidedBy
): Promise<ApprovalRequest | null> {
  const db = await getDb();
  const result = await db.query<ApprovalRequest>(
    `UPDATE approval_requests
     SET status = $2, decided_by = $3, responded_at = now()
     WHERE id = $1 AND status = 'pending'
     RETURNING *`,
    [id, decision, decidedBy]
  );
  return result.rows[0] ?? null;
}
