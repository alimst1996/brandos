# Architecture Decision Records — Index

> All architecture and scope decisions for BrandOS are recorded here.
> Each ADR follows the template in [000-adr-template.md](000-adr-template.md).
> New decisions must be recorded as ADRs before implementation begins.

---

## Active ADRs

| # | Title | Status | Date | Summary |
|---|-------|--------|------|---------|
| [001](001-monorepo-and-stack-choice.md) | Monorepo and Stack Choice | Accepted | 2026-07-24 | NestJS + Next.js + Prisma + Turborepo monorepo |
| [002](002-one-general-worker.md) | One General Worker | Accepted | 2026-07-24 | Single worker module; no specialized worker processes until throughput demands |
| [003](003-workspace-id-convention.md) | Workspace ID Convention | Accepted | 2026-07-24 | Tenant isolation via `workspaceId` field on all entities |
| [004](004-brand-voice-vs-persona.md) | Brand Voice vs. Persona Separation | Accepted | 2026-07-24 | Brand Voice (who the brand is) and Persona (who the audience is) are separate entities |
| [005](005-deferral-of-social-connectors.md) | Deferral of Social Connectors | Accepted | 2026-07-24 | Social media connectors deferred to post-MVP |

## Decision Categories

### Architecture & Stack
- ADR-001: Monorepo and stack choice
- ADR-002: One general worker

### Data Model
- ADR-003: Workspace ID convention
- ADR-004: Brand Voice vs. Persona separation

### Scope
- ADR-005: Deferral of social connectors

---

## Superseded / Deprecated ADRs

(None yet.)

---

## How to Add a New ADR

1. Copy `000-adr-template.md` to `NNN-title.md` (next sequential number).
2. Fill in all sections.
3. Set status to `Proposed`.
4. Add a row to the table above.
5. Submit a PR. Reviewer sets status to `Accepted` on merge.
6. If it supersedes an existing ADR, update both the old and new records.
