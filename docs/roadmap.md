# Roadmap

What's next, in priority order. Shipped work moves to
[CHANGELOG.md](../CHANGELOG.md); the reasoning behind existing design is in
[architecture.md](architecture.md).

## Next

1. **Approval controls** — optional redaction of args shown in
   Slack/dashboard approval requests.
2. **Tamper-evident audit** — hash-chained events so gaps or edits are
   detectable.
3. **Multi-user dashboard** — projects, per-project API keys, roles, and
   named reviewers on approvals; SSO after that.
4. **Policy hot-reload** from the dashboard without restarting the agent
   (or the MCP proxy).
5. **MCP proxy over HTTP** — Streamable HTTP transport for remote MCP
   servers, alongside stdio; and one approval per multi-round
   (`input_required`) tool call instead of one per round.
6. **TypeScript SDK.**

## Not planned

- Prompt-injection detection — well covered elsewhere and not what bastion
  is for.
- ML-based PII detection — revisit only if the regex false-negative rate is
  a real problem for users.

## Done

- Shadow mode (log-only rollout), per rule or whole policy.
- PII/secrets redacted in audit-logged args by default.
- `call_id` links each call's decision and outcome (`completed`/`failed`).
- Approvals record who decided (`approver`) and link to their call.
- Claude Agent SDK enforcement via a `PreToolUse` hook, so pre-allowed tools
  and `bypassPermissions` no longer skip policy.
- Approval waits run off the event loop in every async integration.
- Slack approver allow-list.
- MCP proxy (stdio): policy for any MCP client without code changes.
