# ADR-000: Architecture Decision Record Template

> Use this template when recording a new architecture or scope decision.
> Copy this file to `docs/adr/NNN-title.md`, fill in the sections,
> and add an entry to [`docs/adr/index.md`](index.md).

---

## Title

ADR-NNN: Short descriptive title

## Status

Proposed | Accepted | Deprecated | Superseded by ADR-XXX

## Date

YYYY-MM-DD

## Context

What is the issue that motivates this decision? What is the technical,
business, or organizational context? Describe the forces at play, including
political, economic, or technical constraints.

## Decision

What is the change being proposed or decided? State it clearly and concisely
in one or two sentences.

## Consequences

### Positive

- What becomes easier or better?
- What new capabilities does this enable?

### Negative

- What becomes harder?
- What risks does this introduce?
- What technical debt does this create?

### Neutral

- What trade-offs are being accepted?
- What alternatives were considered and rejected?

## Alternatives Considered

| Alternative | Why rejected |
|-------------|--------------|
| Option A | Reason for rejection |
| Option B | Reason for rejection |

## Links

- Related ADRs: ADR-XXX, ADR-YYY
- Related Jira issues: BOS-NNN
- External references: [link]

---

## How to Use This Template

1. Copy this file to `docs/adr/NNN-title.md` (next sequential number).
2. Fill in all sections. Leave "Alternatives Considered" empty only if
   there genuinely was only one option.
3. Set status to `Proposed` initially.
4. Submit a PR. The reviewer sets status to `Accepted` on merge.
5. Add an entry to `docs/adr/index.md`.
6. If a later ADR supersedes this one, update status to
   `Superseded by ADR-XXX` and link back.

### When Is an ADR Required?

An ADR is required **before implementation** when any of these change:

- Technology stack (language, framework, ORM, hosting)
- Architecture pattern (monolith vs. microservices, worker model)
- Data model (schema changes, entity boundaries)
- Scope boundaries (what's in or out of the current phase)
- Security boundaries (authentication, authorization, data access)
- Billing rules (pricing, quotas, feature gates)
- API contracts (public endpoints, webhook formats)
- Agent team structure (new profiles, role changes)

Minor bug fixes, documentation updates, and test additions do **not** require
an ADR.
