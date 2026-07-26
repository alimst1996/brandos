# BrandOS Autonomous Recovery Supervisor

**BOS-151** — Automated task health monitoring, classification, recovery, and escalation for the BrandOS kanban board.

## Overview

The recovery supervisor is a cron-friendly monitoring system that reads the kanban SQLite database, classifies every task into an actionable health state, detects structural anomalies (circular dependencies, stranded tasks), produces a structured JSON recovery plan with recommended actions, and **autonomously executes** those actions when run with `--execute`.

It is designed to run periodically (e.g., every 5–15 minutes via cron) and either report findings (plan-only mode) or take autonomous recovery actions (execute mode).

## Architecture

```
┌─────────────────────────────────────────────────┐
│              recovery_supervisor.py              │
│  (cron entry point → reads DB → outputs JSON)   │
│  --dry-run: plan only  --execute: take actions   │
│  --notify: send Telegram alerts                  │
├─────────────────────────────────────────────────┤
│  recovery_classify.py                           │
│  (pure classification logic, no I/O)            │
│  - classify_task()     - detect_circular_links()│
│  - classify_all()      - detect_stranded_tasks()│
│  - count_implementation_wip()                   │
├─────────────────────────────────────────────────┤
│  recovery_actions.py                            │
│  (autonomous action executor)                   │
│  - execute_plan()                               │
│  - restart/merge/rework/escalate/promote        │
│  - idempotency guards                           │
├─────────────────────────────────────────────────┤
│  recovery_notify.py                             │
│  (Telegram escalation & daily digest)           │
│  - notify_escalation()  - notify_daily_digest() │
├─────────────────────────────────────────────────┤
│  recovery_audit.py                              │
│  (structured JSON logging + secret redaction)   │
│  - RedactingFilter    - AuditLogger             │
│  - redact_dict()                                │
└─────────────────────────────────────────────────┘
```

## CLI Usage

```bash
# Plan-only mode (default — reads DB, outputs JSON, no mutations)
python scripts/recovery_supervisor.py --pretty

# Dry-run mode (logs what actions would be taken, but doesn't modify DB)
python scripts/recovery_supervisor.py --dry-run --pretty

# Execute mode (actually takes recovery actions — restarts, promotions, merges)
python scripts/recovery_supervisor.py --execute --pretty

# Execute + Telegram notifications
python scripts/recovery_supervisor.py --execute --notify --pretty

# Override DB path and timestamp
python scripts/recovery_supervisor.py --db /path/to/kanban.db --now 1700000000
```

### Default DB Path

The supervisor reads from:
```
~/AppData/Local/hermes/kanban/boards/brandos/kanban.db
```

## Classification Rules

Each task is classified into exactly one state:

| State | Condition |
|-------|-----------|
| `timed_out` | Running + started_at + max_runtime_seconds < now AND (no heartbeat OR heartbeat >30min old) |
| `stalled` | Running + no heartbeat for >60min (but not yet timed out) |
| `needs_review` | Blocked + block_kind = "review-required" |
| `needs_rework` | Blocked + block_kind = "rework-needed" + block_recurrences < 2 |
| `needs_rework_escalate` | Blocked + block_kind = "rework-needed" + block_recurrences >= 2 |
| `merge_ready` | Blocked + block_kind = "merge-ready" |
| `blocked_human` | Blocked + block_kind = "needs_input" (or unknown block kind) |
| `blocked_dependency` | Blocked + block_kind = "dependency" |
| `stranded` | Status = "todo" + all parent tasks are "done" (should be "ready") |
| `ready_dispatch` | Status = "ready" + not yet assigned/claimed |
| `running_healthy` | Running + recent heartbeat (<60min) |
| `done` | Status = "done" |
| `other` | Everything else |

### Heartbeat Thresholds

- **30 minutes** — If a running task exceeds its max_runtime AND has no heartbeat for 30min, it is **timed out**.
- **60 minutes** — If a running task has no heartbeat for 60min (regardless of max_runtime), it is **stalled**.

### Database Schema Compatibility

The supervisor reads the actual kanban SQLite schema (`last_heartbeat_at` column, `status='archived'` filtering). Tests use a matching schema for accuracy.

## Recovery Actions

When run with `--execute`, the supervisor performs these autonomous actions:

| Action | Trigger | Behavior |
|--------|---------|----------|
| `restart_task` | Timed-out task | Creates continuation task (`{id}_continue`), blocks original as `timed-out`, preserves assignee and branch context |
| `check_heartbeat` | Stalled task | Monitors short stalls; escalates after 7 days |
| `escalate_rework` | Rework needed + recurrences >= 2 | Marks as `escalated-rework`, routes to human |
| `route_rework` | Review-required or rework-needed (cycles < 2) | Increments block_recurrences, routes to rework |
| `promote_stranded` | Todo task with all parents done | Promotes to `ready` |
| `merge_pr` | Merge-ready task | Marks as `done` (GitHub merge API integration ready) |
| `resolve_circular_deps` | Circular dependencies detected | Always escalates to human (requires manual intervention) |
| `wip_limit_reached` | WIP count >= limit | Suppresses new dispatches |

### Idempotency

Every action is idempotent:
- **Restart**: Continuation ID is deterministic (`{task_id}_continue`). If it already exists, skip.
- **Promote**: If task is already `ready`, skip.
- **Escalate**: If already `escalated-rework`, skip.
- **Re-execute**: Running `execute_plan` twice on the same plan produces no duplicate side effects.

### Rework Cycle Limits

Maximum rework cycles: **2** (configurable via `MAX_REWORK_CYCLES`).
1. First rework → `rework-needed` (cycle 1/2)
2. Second rework → `rework-needed` (cycle 2/2)
3. Third attempt → `escalated-rework` (routed to human)

## WIP Accounting

**Work-In-Progress (WIP)** tracks how many implementation tasks are actively consuming agent slots.

### Rules:
- Only `running` or `blocked` tasks count
- Only implementation profiles consume WIP:
  - `brandosbackend`
  - `brandosfrontend`
  - `brandosintelligence`
  - `brandospreview`
- Exempt profiles (do NOT consume WIP):
  - `brandosquality` — review/quality tasks
  - `brandosorchestrator` — orchestration tasks
  - `brandossocial` — social media tasks
- **WIP limit**: 2 (configurable via `WIP_LIMIT`)

When WIP is at limit, the supervisor recommends no new dispatches.

## Escalation Policy

### Automatic Escalation Triggers
- Rework limit exceeded (2+ cycles) → `escalated-rework`
- Stalled for >7 days → escalated to human
- Circular dependencies → always escalated (requires manual link breaking)

### Telegram Notifications

The `--notify` flag sends structured alerts to Telegram:
- **Escalation alert**: Sent when there are escalated or failed actions
- **Daily digest**: Sent every run with board health summary

Set the notification channel via `RECOVERY_NOTIFY_CHANNEL` environment variable.

### Escalation to Product Owner

Agents route through `brandosorchestrator` for coordination. Human alerts include:
- The exact decision required
- Why agents cannot safely decide it
- What recovery paths were already attempted

Escalation triggers for human-only decisions:
- Secrets/permissions needed
- Paid services required
- Public/production actions
- Irreversible data changes
- Legal/compliance decisions
- Repeated failure after all bounded recovery paths

## Cron Setup

```cron
# Plan-only every 10 minutes (safe, no mutations)
*/10 * * * * cd /path/to/brandos && python scripts/recovery_supervisor.py --pretty >> /var/log/recovery.log 2>&1

# Execute mode every 15 minutes with notifications
*/15 * * * * cd /path/to/brandos && python scripts/recovery_supervisor.py --execute --notify --pretty >> /var/log/recovery.log 2>&1
```

Or use Hermes cron for integration with the kanban system.

## Audit Format

All audit entries are structured JSON (NDJSON — one JSON object per line):

```json
{
  "timestamp": "2024-01-15T10:30:00+00:00",
  "level": "ACTION",
  "event": "action:create_continuation",
  "logger": "recovery_actions",
  "action_type": "create_continuation",
  "task_id": "t_abc_continue",
  "details": "Created continuation for timed-out task t_abc",
  "original_task": "t_abc"
}
```

### Log Levels

- `INFO` — Normal operational events (scan start, plan built)
- `WARN` — Non-fatal issues (DB table missing, read errors)
- `ERROR` — Fatal issues (DB not found, action execution failures)
- `ACTION` — Recovery actions taken on tasks

### Secret Redaction

The audit system automatically redacts:
- **Keys**: `token`, `api_key`, `password`, `secret`, `authorization`, `auth`, `credential`, `cookie`, `session`
- **Values**: Bearer tokens, Basic auth, API key patterns (`sk_*`, `ghp_*`, `xoxb-*`), environment variable references to secrets (`$MY_TOKEN`)

## Testing

```bash
# Run all tests
python -m unittest tests.test_recovery tests.test_recovery_actions -v

# Run specific test modules
python -m unittest tests.test_recovery -v        # Classification + plan tests
python -m unittest tests.test_recovery_actions -v # Action execution + notification tests
```

### Test Coverage

**test_recovery.py** (67 tests):
- All 13 classification states
- Circular dependency detection (2-node, 3-node, self-loop)
- Stranded task detection (full and partial parent completion)
- WIP counting (implementation profiles, exemptions, max WIP)
- Recovery plan structure and content
- Audit logging and secret redaction
- Restart idempotency and state transitions

**test_recovery_actions.py** (45 tests):
- Continuation task creation (idempotent, preserves Jira key, assigns correctly)
- Restart handling (dry-run, already-timed-out, not-found, no-id)
- Stalled task handling (short stall → monitor, long stall → escalate)
- Rework escalation (cycle 1 → rework, cycle 2 → rework, cycle 3+ → escalate)
- Stranded promotion (promote, already-ready skip, dry-run)
- Merge-ready handling (mark done, dry-run)
- Circular dependency handling (always escalates)
- Dependency unblocking (parent done → unblock, parent running → stay blocked)
- Full plan execution (empty, mixed scenarios, healthy board)
- Restart idempotency (no duplicate continuations across runs)
- Full lifecycle (timed-out → continuation → ready → done)
- Notification formatting (escalation message, daily digest, caps)
- End-to-end recovery scenarios

## Import Usage

All modules work as importable libraries:

```python
from scripts.recovery_classify import classify_task, TaskState, detect_circular_links
from scripts.recovery_audit import AuditLogger, redact_dict
from scripts.recovery_supervisor import build_recovery_plan
from scripts.recovery_actions import execute_plan, ActionResult, ActionOutcome
from scripts.recovery_notify import notify_escalation, notify_daily_digest

# Classify a single task
state = classify_task({"id": "1", "status": "running", ...}, now=int(time.time()))

# Build full recovery plan
plan = build_recovery_plan("/path/to/kanban.db")
print(json.dumps(plan, indent=2))

# Execute the plan (autonomous recovery)
results = execute_plan("/path/to/kanban.db", plan, dry_run=False)
for r in results:
    print(f"{r.action}: {r.outcome.value} — {r.details}")

# Send Telegram notifications
notify_daily_digest(plan)
notify_escalation([{"action": "escalate_rework", "task_id": "t1", "outcome": "escalated", "details": "..."}])
```
