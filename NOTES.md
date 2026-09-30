# NOTES — Product Context & Decisions

Reference doc for *why* this product is shaped the way it is. For *what to
build next*, see [PLAN.md](PLAN.md). For repo conventions, see
[AGENTS.md](AGENTS.md).

## Product

**One-liner**: A policy enforcement layer for AI agents — intercepts tool/function
calls before they execute, enforces allow/block/approve rules, and logs everything
for audit/compliance.

**Wedge**: action-level enforcement on tool calls (not another prompt-injection
classifier — that's commoditized). Closer to "IAM + firewall for agents" than
"content moderation for agents."

**Target buyer (end state)**: enterprises deploying internal AI agents — security/
compliance teams need governance before regulators or incidents force the issue.

**GTM reality check**: solo founder + enterprise sales cycle is a hard combo
(3-9mo cycles, SOC2 needed, on-site POCs). Plan: start distribution via
AI-native/startup teams and open-source adoption, use resulting logos/case
studies to unlock enterprise motion later. Don't sell cold into enterprise
security teams as the first GTM motion.

## Competitive landscape (as of 2026-09)

- Lakera, Prompt Security, CalypsoAI, HiddenLayer — input/output guardrails,
  prompt injection + content safety focus
- Robust Intelligence (acquired by Cisco), Protect AI (acquired by Palo Alto)
- Witness AI, Aim Security — enterprise LLM usage observability/DLP
- Guardrails AI, NeMo Guardrails — open source, rule-based validation

None of these do **action-level enforcement on tool calls** well yet — mostly
log-and-hope. That's the differentiation to hold onto.

## Monetization

- Usage-based (per agent action / per 1k requests) + seat/dashboard fee
- Free/generous tier for indie devs (PLG) → expand to enterprise contracts
- Compliance reporting (EU AI Act, SOC2 evidence) = upsell, not initial wedge

## Architecture

```
Agent code (LangGraph)
     |
     v
SDK wraps the tool-execution step
     |
     +--> Policy engine (local, low-latency) -- allow/block/flag
     |         |
     |         v (if flagged)
     |    Approval queue -> Slack/dashboard -> human decides
     |
     v
Tool actually executes (or doesn't)
     |
     v
Async log shipped to backend -> Dashboard (Next.js + Postgres)
```

- SDK: Python package, wraps LangGraph's tool-call hook
- Policy engine: runs locally in-process for low latency, config is
  versioned per project (YAML/JSON)
- Backend: async log ingestion (non-blocking), Postgres storage, simple
  dashboard for logs + policy config + approval queue
- Approval channel: Slack (fastest to build, natural UX — Approve/Deny buttons)

## Decisions log

- 2026-09-30: Wedge = agent runtime guardrails (not DLP, not compliance-first,
  not red-teaming-as-a-service)
- 2026-09-30: ICP = enterprises going agentic (end state), but GTM starts
  smaller (AI-native teams, OSS adoption)
- 2026-09-30: Solo technical founder — MVP scoped to be buildable alone
- 2026-09-30: First framework integration = LangGraph, others added later
- 2026-09-30: Repo scaffolded at `C:\Cooking AI\AI safety and compliance`
- 2026-09-30: MVP scope locked (see PLAN.md for the current, evolving version)
- 2026-09-30: OSS license = Apache-2.0 (provisional, reconsider before public launch)
- 2026-09-30: Adopted production tooling from the start — ruff, mypy (strict),
  pytest, GitHub Actions CI — rather than retrofitting later. Reasoning: this
  is meant to be an OSS security tool; code quality and typed public APIs are
  part of the trust signal, not polish to add after traction.

## Open questions

- Naming for the product/repo — currently using placeholder name `agentguard`
  (package + repo), not validated for trademark/domain availability, easy to
  rename before any public launch
- Where policy config lives long-term (per-project YAML file vs. pulled from
  a hosted dashboard) — see PLAN.md
- PII/secrets detection: which library/API to lean on (e.g. Microsoft
  Presidio for local, or a hosted API) — not yet decided
