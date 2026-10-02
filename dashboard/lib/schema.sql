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

CREATE TABLE IF NOT EXISTS policy_versions (
  id TEXT PRIMARY KEY,
  yaml_text TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_policy_versions_created_at ON policy_versions (created_at DESC);
