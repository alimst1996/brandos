# ADR-003: Workspace ID Convention

## Status

Accepted

## Date

2026-07-24

## Context

BrandOS is designed as a multi-tenant platform where each brand owner operates
within their own workspace. Data isolation between workspaces is a hard
requirement — one brand owner must never see another's data, API keys, or
brand voice definitions.

The question is how to implement tenant isolation at the data model level:
- Shared database with row-level isolation?
- Separate database per tenant?
- Schema-per-tenant?

For the MVP, a shared database with row-level isolation is the simplest and
most cost-effective approach.

## Decision

Every entity in the data model includes a **`workspaceId`** field that acts as
the tenant partition key.

### Convention rules:

1. **Every table** that contains tenant data has a `workspaceId` column
   (foreign key to `Workspace`).
2. **Every Prisma query** includes a `where.workspaceId` filter. The ORM
   middleware or service layer enforces this — no ad-hoc queries without
   workspace scope.
3. **Every API endpoint** extracts `workspaceId` from the authenticated session
   (JWT claim or API key scope). It is never passed as a user-supplied parameter
   for read/write operations.
4. **Every agent task** receives `workspaceId` in its context package. Agents
   do not determine workspace scope themselves.
5. **Shared/reference tables** (e.g., job types, feature flags) may omit
   `workspaceId` if they are truly global.

### Database-level enforcement:

- A Prisma middleware (`$use`) injects `workspaceId` into all queries
  automatically.
- A unique composite index on `(workspaceId, <natural_key>)` prevents
  cross-tenant data leaks at the database level.

## Consequences

### Positive

- Clean tenant isolation with minimal infrastructure.
- Works with a single database; no need for schema-per-tenant complexity.
- Agents cannot accidentally access cross-tenant data (the middleware blocks it).
- Easy to extract a tenant to a dedicated database later if needed.

### Negative

- Every query carries the workspace filter; a missing filter is a data leak.
- The Prisma middleware adds a small overhead to every query.
- Large tenants share resources with small tenants (noisy-neighbor risk).

### Neutral

- This convention is documented here so that every new entity and query
  follows it without the engineer having to ask.
- If the platform outgrows shared-DB isolation, the `workspaceId` column
  becomes the shard key.

## Alternatives Considered

| Alternative | Why rejected |
|-------------|--------------|
| Schema-per-tenant | Complex migrations; Prisma doesn't natively support multi-schema well |
| Separate database per tenant | Expensive at MVP scale; connection pool explosion |
| Application-only filtering (no middleware) | Error-prone; any missed query leaks data |

## Links

- Related Jira issues: FOUND-005 (workspace model)
