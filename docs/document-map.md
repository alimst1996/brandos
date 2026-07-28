# BrandOS Document Map

> **Purpose:** This is the single entry point for any agent or human navigating
> the BrandOS knowledge base. It names every source of truth, its authority level,
> and its path. An agent given only this file can locate the active scope,
> the stack decision, and the persona separation rule without reading the full
> vision document.

---

## Precedence Order

When two sources conflict, **the higher source wins**:

| Rank | Source | Why |
|------|--------|-----|
| 1 | **Git history** | Shows what was *actually built*, not what was planned |
| 2 | **Jira active scope** (labels, description, links) | The current sprint's ground truth |
| 3 | **Architecture Decision Records** (`docs/adr/`) | Captured decisions with context and consequences |
| 4 | **Execution Brief** (`docs/execution-brief.md`) | Current phase scope and deliverables |
| 5 | **Product Vision** (`docs/vision.md`) | Long-term approved direction (background) |
| 6 | **Other docs** (`docs/*.md`) | Operational guides, runbooks |

**Key rule:** The Product Vision is approved background. When it says one thing
and a Jira issue says another, the Jira issue is authoritative for what gets built
right now. The vision gets updated later to reflect the new direction, via an ADR.

**Convention:** Any scope or architecture change MUST land as an ADR before
implementation begins. See [ADR-000](adr/000-adr-template.md) for the template.

---

## Source-of-Truth Registry

### Product Direction

| Document | Path | Authority | Audience |
|----------|------|-----------|----------|
| Product Vision | [`docs/vision.md`](vision.md) | Long-term direction (lowest priority on conflicts) | Everyone |
| Execution Brief | [`docs/execution-brief.md`](execution-brief.md) | Current phase scope | Agents, PO |
| Document Map | [`docs/document-map.md`](document-map.md) | Navigation + precedence | Everyone (start here) |

### Decision Records

| Document | Path | Authority | Audience |
|----------|------|-----------|----------|
| ADR Template | [`docs/adr/000-adr-template.md`](adr/000-adr-template.md) | Format standard | Anyone writing an ADR |
| ADR Index | [`docs/adr/index.md`](adr/index.md) | Registry of all ADRs | Everyone |
| ADR-001 | [`docs/adr/001-monorepo-and-stack-choice.md`](adr/001-monorepo-and-stack-choice.md) | Stack decision | Engineers |
| ADR-002 | [`docs/adr/002-one-general-worker.md`](adr/002-one-general-worker.md) | Worker architecture | Engineers |
| ADR-003 | [`docs/adr/003-workspace-id-convention.md`](adr/003-workspace-id-convention.md) | Tenant isolation | Engineers |
| ADR-004 | [`docs/adr/004-brand-voice-vs-persona.md`](adr/004-brand-voice-vs-persona.md) | Data model separation | Intelligence, PM |
| ADR-005 | [`docs/adr/005-deferral-of-social-connectors.md`](adr/005-deferral-of-social-connectors.md) | Scope deferral | Everyone |

### Operations

| Document | Path | Authority | Audience |
|----------|------|-----------|----------|
| Definition of Ready | [`docs/definition-of-ready.md`](definition-of-ready.md) | Dispatch gate | Agents, orchestrator |
| Jira-Hermes Bridge | [`docs/jira-hermes-bridge.md`](jira-hermes-bridge.md) | Task dispatch system | Orchestrator |
| Autopilot Runbook | [`docs/autopilot-runbook.md`](autopilot-runbook.md) | Recovery procedures | Humans, orchestrator |
| Recovery Supervisor | [`docs/recovery-supervisor.md`](recovery-supervisor.md) | Autonomous recovery | Orchestrator |
| Reconcile Handoff | [`docs/reconcile-handoff.md`](reconcile-handoff.md) | Delivery lifecycle | Orchestrator |

### Code Entry Points

| Component | Path | Purpose |
|-----------|------|---------|
| Jira-Hermes Bridge | `scripts/jira_hermes_bridge.py` | Dispatch Jira issues to kanban |
| Autopilot Dispatcher | `scripts/autopilot-dispatcher.py` | Cron dispatcher (15min) |
| Reconcile Loop | `scripts/reconcile.py` | Full delivery lifecycle |
| Recovery Supervisor | `scripts/recovery_supervisor.py` | Task health monitoring |
| Readiness Checker | `scripts/check_readiness.py` | Definition of Ready validator |
| Daily Report | `scripts/autopilot-daily-report.py` | Telegram status digest |

---

## How to Find the Active Scope

An agent following these steps can locate the current work without reading the
full vision:

1. **Check Jira** — query for issues with `ready-for-dispatch` label in BOS
   project. This is the authoritative current scope.
2. **Check the kanban board** — `hermes kanban list` shows what's in-flight.
3. **Check this execution brief** — `docs/execution-brief.md` lists phase
   deliverables and their status.
4. **Check ADRs** — `docs/adr/index.md` for any decisions that constrain scope.

If Jira says something different from the vision, **Jira wins**. If Jira is
silent on a question, check the ADRs. If ADRs are silent, the vision provides
the default direction.

---

## Maintenance

- **Who updates this:** The orchestrator agent (`brandosorchestrator`) or the PO.
- **When:** Whenever a new ADR is created, a new operational doc is added, or
  the execution brief is updated for a new phase.
- **How:** Edit this file and submit a PR. Changes to the precedence order
  require an ADR.
