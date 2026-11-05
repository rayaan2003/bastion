# Roadmap

What's next, in priority order. Shipped work moves to
[CHANGELOG.md](../CHANGELOG.md); the reasoning behind existing design is in
[architecture.md](architecture.md).

## Next

1. **Claude Agent SDK: enforce via a `PreToolUse` hook.** `can_use_tool` is
   never consulted for tools pre-allowed by `allowed_tools`/settings or under
   `permission_mode="bypassPermissions"`, so bastion silently doesn't see
   those calls. The SDK's own guidance is a `PreToolUse` hook to gate every
   call.
2. **Trustworthy audit log**
   - record who approved or denied (Slack user, dashboard reviewer)
   - link each approval to its session and audit event
   - redact PII/secrets in logged args by default
   - record whether an allowed tool call then succeeded or failed
3. **Tamper-evident audit** — hash-chained events so gaps or edits are
   detectable.
4. **Multi-user dashboard** — projects, per-project API keys, roles; SSO
   after that.
5. **Async approvals** — an async `ApprovalHandler` so the OpenAI Agents and
   Claude Agent SDK integrations don't block the event loop while waiting.
6. **Policy hot-reload** from the dashboard without restarting the agent.
7. **Beyond Python** — a TypeScript SDK, or an MCP proxy that enforces
   policy for any MCP client.

## Not planned

- Prompt-injection detection — well covered elsewhere and not what bastion
  is for.
- ML-based PII detection — revisit only if the regex false-negative rate is
  a real problem for users.

## Done

- Shadow mode (log-only rollout), per rule or whole policy.
