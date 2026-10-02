import { Pool } from "pg";
import fs from "node:fs";
import path from "node:path";

// Real Postgres via DATABASE_URL. v1 ran on PGlite (embedded WASM Postgres)
// to avoid standing up a database before there were real users - this
// swaps to a real connection now that the dashboard is being deployed
// somewhere reachable, where PGlite's single-process limitation (no
// concurrent writers) would actually matter. See NOTES.md.

declare global {
  var __agentguardDb: Promise<Pool> | undefined;
}

async function createDb(): Promise<Pool> {
  const connectionString = process.env.DATABASE_URL;
  if (!connectionString) {
    throw new Error("DATABASE_URL environment variable is required");
  }

  const pool = new Pool({ connectionString });
  const schema = fs.readFileSync(path.join(process.cwd(), "lib", "schema.sql"), "utf-8");
  await pool.query(schema);
  return pool;
}

export function getDb(): Promise<Pool> {
  if (!global.__agentguardDb) {
    global.__agentguardDb = createDb();
  }
  return global.__agentguardDb;
}
