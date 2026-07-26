# Definition of Ready — BrandOS

## Purpose

An enforceable gate that prevents humans or agents from dispatching work before it is executable and reviewable.

## Checklist

An issue is **ready for dispatch** only when **all** applicable conditions are true:

| # | Condition | Validation |
|---|-----------|------------|
| 1 | Objective, scope and explicit out-of-scope are unambiguous | `description` field is non-empty and contains structured sections |
| 2 | Acceptance criteria are testable | `description` contains an "Acceptance Criteria" section |
| 3 | Required tests and evidence are specified | `description` references tests/evidence or labels indicate `points` |
| 4 | Real Jira dependency links exist and all blockers are resolved | No open `is blocked by` links to unresolved issues |
| 5 | Role, reviewer, risk, phase, points, and version labels are present | `role-*`, `review-*`, `risk-*`, `phase-*`, `points-*`, `ver-*` labels exist |
| 6 | Security/privacy implications are recorded | Labels or description mention security (or `risk-high` triggers review) |
| 7 | Human approval requirement is explicit | `human-approval-required` label is present when version < 1.0 or risk = high |
| 8 | Repository/module context and interface contracts are identified | Description names the repository or component |
| 9 | No `do-not-dispatch-yet`, `status-blocked`, or `deferred-scope` label remains | None of these block labels are present |
| 10 | Issue fits the active MVP scope | `ver-*` label is present |

## Labels Reference

### Positive gate (must be present)
- `ready-for-dispatch` — set only after all checklist items pass

### Block labels (presence prevents dispatch)
- `do-not-dispatch-yet` — work is not yet ready for any reason
- `status-blocked` — explicit external blocker
- `deferred-scope` — intentionally excluded from current scope

### Required labels
| Category | Pattern | Example |
|----------|---------|---------|
| Role | `role-*` | `role-pm`, `role-dev` |
| Reviewer | `review-by-*` or `review-agent-*` | `review-by-agent-quality` |
| Risk | `risk-*` | `risk-high`, `risk-low` |
| Phase | `phase-*` | `phase-foundation` |
| Points | `points-*` | `points-3` |
| Version | `ver-*` | `ver-0.1-foundation` |

## Enforcement

1. **Label gate**: Dispatch queries must include `ready-for-dispatch` in filters.
2. **Automated check**: `scripts/check_readiness.py` validates issue JSON against this checklist.
3. **Self-healing**: Removing any prerequisite label (via API or UI) automatically invalidates readiness.
4. **Reviewer gate**: High-risk or human-approval issues require a non-author reviewer.

## Updating the Checklist

Changes to this document require a pull request with reviewer approval.
The checker script must be updated in lockstep with any checklist change.