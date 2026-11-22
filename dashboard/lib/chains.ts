import { getDb } from "./db";

// Checks that stored events link up: no seq missing from a chain, and each
// event's prev_hash is the stored hash of the event before it. It doesn't
// recompute hashes from event contents - JSONB and JS numbers don't keep
// the SDK's exact JSON (1.0 comes back as 1) - so a changed event shows up
// when `bastion verify-audit` compares the SDK's log with this copy.

export interface ChainProblem {
  chain_id: string;
  seq: number;
  problem: string;
}

export interface ChainIntegrity {
  chains: number;
  events: number;
  problems: ChainProblem[];
  // More problems exist than are listed.
  truncated: boolean;
}

const MAX_PROBLEMS = 50;

export async function checkChains(): Promise<ChainIntegrity> {
  const db = await getDb();
  // COUNT is a BIGINT, which pg returns as a string.
  const totals = await db.query<{ chains: string; events: string }>(
    `SELECT COUNT(DISTINCT chain_id) AS chains, COUNT(*) AS events
     FROM audit_events WHERE chain_id IS NOT NULL`
  );
  const broken = await db.query<{ chain_id: string; seq: number; expected_seq: number }>(
    `SELECT chain_id, seq, expected_seq FROM (
       SELECT chain_id, seq, prev_hash,
              COALESCE((LAG(seq) OVER w) + 1, 0) AS expected_seq,
              COALESCE(LAG(hash) OVER w, '') AS expected_prev_hash
       FROM audit_events
       WHERE chain_id IS NOT NULL
       WINDOW w AS (PARTITION BY chain_id ORDER BY seq)
     ) linked
     WHERE seq <> expected_seq OR prev_hash <> expected_prev_hash
     ORDER BY chain_id, seq
     LIMIT $1`,
    [MAX_PROBLEMS + 1]
  );

  const problems = broken.rows.slice(0, MAX_PROBLEMS).map((row) => ({
    chain_id: row.chain_id,
    seq: row.seq,
    problem: describe(row.seq, row.expected_seq),
  }));
  return {
    chains: Number(totals.rows[0].chains),
    events: Number(totals.rows[0].events),
    problems,
    truncated: broken.rows.length > MAX_PROBLEMS,
  };
}

// Same wording as the SDK's `bastion verify-audit`. seq is never below
// expected: the unique (chain_id, seq) index rules out repeats.
function describe(seq: number, expected: number): string {
  if (seq === expected + 1) return `event ${expected} is missing before seq ${seq}`;
  if (seq > expected) return `events ${expected}-${seq - 1} are missing before seq ${seq}`;
  if (seq === 0) return "seq 0 has a prev_hash, but it should start its chain";
  return `seq ${seq} doesn't link to seq ${seq - 1}: one of them was replaced`;
}
