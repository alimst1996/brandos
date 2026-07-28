# BrandOS Execution Brief

> **Version:** 1.0 · **Last updated:** 2026-07-27 · **Status:** Active
> **Authority:** This document describes the current phase scope and deliverables.
> When it conflicts with the Product Vision, this brief wins.
> See [Document Map](document-map.md) for the full precedence order.

---

## Current Phase

**v0.1 — Foundation** (phase-foundation)

The foundation phase establishes the infrastructure for autonomous delivery,
the brand intelligence data model, and the agent team structure.
No customer-facing features ship in this phase.

## Phase Goals

1. **Autonomous delivery pipeline** — agents can receive, implement, review,
   and merge work without human intervention for low-risk changes.
2. **Brand intelligence foundation** — Brand Voice and Persona are modeled as
   separate, versioned data structures.
3. **Source-of-truth governance** — all product decisions captured as ADRs;
   document map enables any agent to navigate the knowledge base.
4. **Recovery and resilience** — the pipeline self-heals from agent crashes,
   timed-out tasks, and flaky reviews.

## Deliverables

### Infrastructure (EPIC-002 — Autonomous Delivery)

| Deliverable | Status | Notes |
|-------------|--------|-------|
| Jira-to-Hermes bridge | ✅ Done | `scripts/jira_hermes_bridge.py` — 87 tests |
| Definition of Ready | ✅ Done | `docs/definition-of-ready.md` — automated checker |
| Autopilot dispatcher | ✅ Done | `scripts/autopilot-dispatcher.py` — cron every 15min |
| Reconcile loop | ✅ Done | `scripts/reconcile.py` — full lifecycle management |
| Recovery supervisor | ✅ Done | `scripts/recovery_supervisor.py` — 112 tests |
| Autopilot runbook | ✅ Done | `docs/autopilot-runbook.md` |
| Daily report | ✅ Done | `scripts/autopilot-daily-report.py` — Telegram digest |

### Governance (ORCH-006 — Source of Truth)

| Deliverable | Status | Notes |
|-------------|--------|-------|
| Product Vision (versioned) | ✅ Done | `docs/vision.md` |
| Execution Brief (versioned) | ✅ Done | `docs/execution-brief.md` — this document |
| Document Map | ✅ Done | `docs/document-map.md` |
| ADR template + index | ✅ Done | `docs/adr/` |
| 5 backfilled ADRs | ✅ Done | See [ADR Index](adr/index.md) |

### Brand Intelligence (EPIC-001 — Brand Data Model)

| Deliverable | Status | Notes |
|-------------|--------|-------|
| Brand Voice schema | 🔲 Planned | Prisma schema for brand voice attributes |
| Persona schema | 🔲 Planned | Audience persona as separate entity |
| workspaceId convention | 🔲 Planned | Tenant isolation via workspace ID |

## Agent Team

| Profile | Role | Scope |
|---------|------|-------|
| `brandosorchestrator` | Project Manager | Task routing, coordination, escalation |
| `brandosbackend` | Backend Engineer | NestJS APIs, Prisma schema, worker |
| `brandosfrontend` | Frontend Engineer | Next.js pages, dashboard, UI |
| `brandosintelligence` | AI/ML Engineer | Content generation, brand voice alignment |
| `brandosquality` | Quality Reviewer | Code review, test verification, security |
| `brandospreview` | Preview Engineer | Staging deployment, visual verification |
| `brandossocial` | Social Media Agent | Content posting, engagement monitoring |

## Constraints

| Constraint | Value | Source |
|------------|-------|--------|
| WIP limit | 2 concurrent tasks | Autopilot config |
| Rework cycles | 2 max before escalation | Recovery supervisor |
| Auto-merge | Low-risk only | Risk-aware merge policy |
| Human approval | Required for high-risk / pre-1.0 | Definition of Ready |

## Out of Scope (this phase)

- Customer-facing UI (deferred to v0.2)
- Social media connectors (deferred; see [ADR-005](adr/005-deferral-of-social-connectors.md))
- Billing and subscription management
- Production deployment infrastructure

## References

- [Product Vision](vision.md) — long-term direction
- [Document Map](document-map.md) — where to find what
- [ADR Index](adr/index.md) — all architecture decision records
