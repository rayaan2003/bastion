CREATE TABLE IF NOT EXISTS audit_events (
  id TEXT PRIMARY KEY,
  "timestamp" DOUBLE PRECISION NOT NULL,
  session_id TEXT NOT NULL,
  tool_name TEXT NOT NULL,
  args JSONB NOT NULL,
  action TEXT NOT NULL,
  reason TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_events_session ON audit_events (session_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_tool ON audit_events (tool_name);
CREATE INDEX IF NOT EXISTS idx_audit_events_action ON audit_events (action);
CREATE INDEX IF NOT EXISTS idx_audit_events_timestamp ON audit_events ("timestamp" DESC);

-- Added after the table shipped; ALTER keeps existing deployments migrating
-- on startup like the rest of this file.
ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS call_id TEXT;
CREATE INDEX IF NOT EXISTS idx_audit_events_call ON audit_events (call_id);
ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS approver TEXT;

CREATE TABLE IF NOT EXISTS approval_requests (
  id TEXT PRIMARY KEY,
  tool_name TEXT NOT NULL,
  args JSONB NOT NULL,
  reason TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  responded_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_approval_requests_status ON approval_requests (status);

-- call_id/session_id link a request to its audit events. decided_by is where
-- the decision was made ('ui' or 'api') - not a person, since the dashboard
-- has a single shared login.
ALTER TABLE approval_requests ADD COLUMN IF NOT EXISTS call_id TEXT;
ALTER TABLE approval_requests ADD COLUMN IF NOT EXISTS session_id TEXT;
ALTER TABLE approval_requests ADD COLUMN IF NOT EXISTS decided_by TEXT;

CREATE TABLE IF NOT EXISTS policy_versions (
  id TEXT PRIMARY KEY,
  yaml_text TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_policy_versions_created_at ON policy_versions (created_at DESC);
