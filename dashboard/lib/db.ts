import { PGlite } from "@electric-sql/pglite";
import fs from "node:fs";
import path from "node:path";

// Embedded Postgres (PGlite), file-persisted under ./data. This is a
// deliberate v1 choice to avoid requiring a hosted Postgres instance before
// there are real users — see NOTES.md in the repo root. Swap for a real
// Postgres connection (e.g. via `pg`) once concurrent multi-instance access
// matters; the SQL in schema.sql and the query() call sites don't change.

declare global {
  var __agentguardDb: Promise<PGlite> | undefined;
}

async function createDb(): Promise<PGlite> {
  const dataDir = path.join(process.cwd(), "data", "pgdata");
  fs.mkdirSync(dataDir, { recursive: true });
  const db = new PGlite(dataDir);
  const schema = fs.readFileSync(path.join(process.cwd(), "lib", "schema.sql"), "utf-8");
  await db.exec(schema);
  return db;
}

export function getDb(): Promise<PGlite> {
  if (!global.__agentguardDb) {
    global.__agentguardDb = createDb();
  }
  return global.__agentguardDb;
}
