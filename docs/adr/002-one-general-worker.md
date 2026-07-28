# ADR-002: One General Worker

## Status

Accepted

## Date

2026-07-24

## Context

BrandOS needs background processing for tasks like content generation pipelines,
scheduled brand voice analysis, and webhook handling. The common approach is to
create specialized worker processes for each concern (a content worker, a
notification worker, a sync worker, etc.).

However, the team is small, the workload is low, and adding worker processes
early introduces operational complexity — separate process management, separate
health checks, separate scaling policies — that is not justified at this stage.

## Decision

Use a **single general worker module** inside the NestJS backend application.

- The worker is a NestJS module (`WorkerModule`) registered in the main app.
- It processes jobs from an in-process queue (BullMQ or simple in-memory queue).
- Jobs are typed and routed by a job registry — no separate process per job type.
- When a job type outgrows the shared worker (measured by queue depth and
  processing latency), it gets its own dedicated worker process as a follow-up
  ADR.

## Consequences

### Positive

- One process to deploy, monitor, and restart.
- No inter-process communication overhead for job dispatch.
- Simple health checks: if the main app is up, the worker is up.
- Agents can implement new job types without touching infrastructure.

### Negative

- A long-running job can block short jobs (mitigated by job prioritization
  and concurrency limits).
- If the main app crashes, the worker also goes down.
- Scaling the API and the worker independently is not possible without
  extracting the worker later.

### Neutral

- This is a conscious simplicity-over-scale trade-off. The extraction path
  is clear: move `WorkerModule` to its own NestJS app in a separate container.
- BullMQ (if adopted) supports both in-process and external Redis-backed modes,
  so the migration path is straightforward.

## Alternatives Considered

| Alternative | Why rejected |
|-------------|--------------|
| Separate worker processes from day one | Operational overhead not justified at current scale |
| External queue service (AWS SQS, RabbitMQ) | Adds infrastructure dependency; not needed at MVP scale |
| Cron-only (no persistent queue) | Not reliable for long-running or retryable tasks |
| Python worker (Celery) | Breaks TypeScript consistency ([ADR-001](001-monorepo-and-stack-choice.md)) |

## Links

- Related ADRs: [ADR-001](001-monorepo-and-stack-choice.md) (stack choice)
- Related Jira issues: FOUND-003 (worker module)
