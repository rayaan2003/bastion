import { randomUUID } from "node:crypto";
import { getDb } from "./db";

// Append-only version history, not a single mutable row - "current" is
// just the most recent one. This gives a free audit trail of policy
// changes over time, consistent with the rest of the product.

export interface PolicyVersion {
  id: string;
  yaml_text: string;
  created_at: string;
}

export async function getCurrentPolicy(): Promise<PolicyVersion | null> {
  const db = await getDb();
  const result = await db.query<PolicyVersion>(
    `SELECT * FROM policy_versions ORDER BY created_at DESC LIMIT 1`
  );
  return result.rows[0] ?? null;
}

export async function savePolicyVersion(yamlText: string): Promise<PolicyVersion> {
  const db = await getDb();
  const id = randomUUID();
  const result = await db.query<PolicyVersion>(
    `INSERT INTO policy_versions (id, yaml_text) VALUES ($1, $2) RETURNING *`,
    [id, yamlText]
  );
  return result.rows[0];
}

export async function listPolicyVersions(limit = 20): Promise<PolicyVersion[]> {
  const db = await getDb();
  const result = await db.query<PolicyVersion>(
    `SELECT * FROM policy_versions ORDER BY created_at DESC LIMIT $1`,
    [limit]
  );
  return result.rows;
}
