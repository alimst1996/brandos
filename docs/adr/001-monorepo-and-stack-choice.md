# ADR-001: Monorepo and Stack Choice

## Status

Accepted

## Date

2026-07-24

## Context

BrandOS needs a backend API, a frontend dashboard, and a background worker.
The team is small (solo brand owner + AI agent team), so the overhead of
multiple repositories — separate CI pipelines, dependency management, and
cross-repo type sharing — would slow delivery significantly.

The technology choices must support:
- TypeScript across the stack (agent-friendly, type-safe)
- Server-side rendering for the dashboard (SEO, initial load)
- Structured API layer with dependency injection (testability)
- Type-safe database access (schema-driven development)
- Task caching for fast builds in a monorepo

## Decision

Use a **Turborepo monorepo** with:

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Backend API | NestJS (TypeScript) | Structured DI, decorators, agent-friendly codegen |
| Frontend | Next.js (TypeScript) | SSR + static, shared TS types with backend |
| ORM | Prisma | Type-safe schema, migration tooling, TS client generation |
| Validation | Zod | Runtime validation shared across layers without codegen |
| Build | Turborepo | Task caching, dependency-aware builds |
| Package manager | pnpm | Fast, disk-efficient, native workspace support |

## Consequences

### Positive

- Single `git clone` gives the full codebase. Agents work in one workspace.
- Prisma generates TypeScript types used by both backend and frontend.
- Zod schemas validate API input/output at runtime without separate OpenAPI
  codegen steps.
- Turborepo caches unchanged packages; incremental builds are fast.
- One CI pipeline, one deployment artifact per layer.

### Negative

- Monorepo grows over time; Turborepo cache invalidation can be coarse.
- All agents share the same repo; merge conflicts possible on schema files.
- pnpm hoisting quirks occasionally require `pnpm-lock.yaml` surgery.

### Neutral

- The worker shares the backend process (see [ADR-002](002-one-general-worker.md)).
- If the monorepo becomes too large, layers can be extracted to packages
  without changing the repo structure (Turborepo supports this natively).

## Alternatives Considered

| Alternative | Why rejected |
|-------------|--------------|
| Separate repos (backend + frontend + worker) | Too much overhead for a small team; cross-repo type sharing is painful |
| Nx monorepo | Heavier tooling; Turborepo is simpler for this scale |
| Plain pnpm workspaces (no Turborepo) | No task caching; builds would be slow as the codebase grows |
| Python backend (FastAPI) | TypeScript everywhere enables shared types; Python would require separate validation layer |

## Links

- Related ADRs: [ADR-002](002-one-general-worker.md) (worker model)
- Related Jira issues: FOUND-001 (monorepo setup)
