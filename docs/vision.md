# BrandOS Product Vision

> **Version:** 1.0 · **Last updated:** 2026-07-27 · **Status:** Approved background
> **Authority:** This document describes the long-term product direction.
> When it conflicts with Jira active scope, **Jira wins**.
> See [Document Map](document-map.md) for the full precedence order.

---

## 1. What Is BrandOS

BrandOS is an AI-powered brand intelligence and social engagement platform.
It helps brand owners maintain a consistent voice, generate on-brand content,
and monitor audience engagement — all orchestrated by an autonomous agent team
running on Hermes.

## 2. Target User

Solo brand owners and small creative teams who want AI-assisted brand management
without hiring a full marketing department. The initial persona is a luxury
minimalist brand owner who needs consistent content across channels with
minimal manual intervention.

## 3. Problem Statement

- Maintaining a consistent brand voice across platforms is time-consuming.
- Content creation pipelines are fragmented (generate → review → post → monitor).
- Social media monitoring requires constant attention.
- Existing tools are either too manual or too generic for niche luxury brands.

## 4. Solution Overview

BrandOS provides a unified platform with four pillars:

### 4.1 Brand Intelligence
- Define and evolve a Brand Voice (tone, vocabulary, visual language).
- Separate Brand Voice (who the brand sounds like) from Persona (who the
  audience is) to avoid conflation.
- Store brand guidelines as structured, versioned data — not prose.

### 4.2 Content Generation
- AI-generated images and video on-brand content.
- Template-driven content pipelines (product showcase, engagement hooks,
  seasonal campaigns).
- Human-in-the-loop review for high-risk or public-facing content.

### 4.3 Social Engagement
- Monitor mentions, comments, and engagement metrics.
- Automated response drafting with brand-voice alignment.
- Social connectors for major platforms (Instagram, X/Twitter, Telegram).
  > **Note:** Social connectors are deferred to post-MVP. See
  > [ADR-005](docs/adr/005-deferral-of-social-connectors.md).

### 4.4 Autonomous Delivery
- Multi-agent orchestration via Hermes kanban board.
- Agents for: backend, frontend, intelligence, quality, preview, social,
  and an orchestrator coordinator.
- Autonomous recovery, rework cycles, and escalation to human when needed.
- Continuous delivery pipeline with risk-aware auto-merge.

## 5. Architecture Principles

| # | Principle | Rationale |
|---|-----------|-----------|
| 1 | Monorepo | Single source of truth for backend + frontend + worker; shared types |
| 2 | One general worker | Simplicity; specialized workers added only when throughput demands |
| 3 | Workspace isolation | Every task runs in its own git worktree branch |
| 4 | Convention over configuration | workspaceId convention reduces boilerplate |
| 5 | ADR-driven changes | Every scope or architecture change lands as an ADR before implementation |
| 6 | Risk-aware automation | Low-risk work auto-merges; high-risk requires human review |

## 6. Technology Stack

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Backend | NestJS (TypeScript) | Structured, testable, agent-friendly API |
| Frontend | Next.js (TypeScript) | SSR + static generation; shared TS types with backend |
| Worker | NestJS worker module (shared process) | One general worker; scale later |
| Database | Prisma ORM | Type-safe schema; migration management |
| Validation | Zod | Runtime validation shared across layers |
| Monorepo tool | Turborepo | Task caching, dependency graph |
| Orchestration | Hermes Agent + kanban | Autonomous multi-agent delivery |
| AI models | OpenRouter (GPT-4o, Gemini, etc.) | Model flexibility; cost control |

## 7. Success Criteria (MVP — v0.1 Foundation)

1. Brand owner can define a Brand Voice and see it applied in generated content.
2. An agent team can receive a Jira task, implement it, review it, and merge it
   autonomously with human oversight for high-risk changes.
3. The autonomous delivery pipeline runs continuously with ≤2 active tasks,
   automatic recovery from failures, and structured escalation to human.
4. All product decisions are captured as ADRs and linked from a navigable
   document map.

## 8. What This Is Not

- **Not a general marketing platform.** BrandOS is for niche/luxury brands,
  not mass-market campaign management.
- **Not a social media dashboard.** Social connectors are deferred; the MVP
  focuses on brand intelligence and autonomous delivery infrastructure.
- **Not a no-code tool.** The agent team works in code; the product owner
  interacts via Jira and kanban, not drag-and-drop editors.

## 9. References

- [Execution Brief](execution-brief.md) — current phase scope and deliverables
- [Document Map](document-map.md) — where to find what, and who wins conflicts
- [ADR Index](adr/index.md) — all architecture decision records
