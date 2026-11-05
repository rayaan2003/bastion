# Roadmap

What's next, in priority order. Shipped work moves to
[CHANGELOG.md](../CHANGELOG.md); the reasoning behind existing design is in
[architecture.md](architecture.md).

## Next

1. **Trustworthy audit log**
   - record who approved or denied (Slack user, dashboard reviewer)
   - link each approval to its session and audit event
   - redact PII/secrets in logged args by default
   - record whether an allowed tool call then succeeded or failed
2. **Tamper-evident audit** — hash-chained events so gaps or edits are
   detectable.
3. **Multi-user dashboard** — projects, per-project API keys, roles; SSO
   after that.
4. **Async approvals** — an async `ApprovalHandler`, or worker-thread
   dispatch as the Claude Agent SDK hook does, so the OpenAI Agents
   integration doesn't block the event loop while waiting.
5. **Policy hot-reload** from the dashboard without restarting the agent.
6. **Beyond Python** — a TypeScript SDK, or an MCP proxy that enforces
   policy for any MCP client.

## Not planned

- Prompt-injection detection — well covered elsewhere and not what bastion
  is for.
- ML-based PII detection — revisit only if the regex false-negative rate is
  a real problem for users.

## Done

- Shadow mode (log-only rollout), per rule or whole policy.
- Claude Agent SDK enforcement via a `PreToolUse` hook, so pre-allowed tools
  and `bypassPermissions` no longer skip policy.
