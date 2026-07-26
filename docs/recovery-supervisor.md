# BrandOS Autonomous Recovery Supervisor

**BOS-151** — Automated task health monitoring, classification, and recovery for the BrandOS kanban board.

## Overview

The recovery supervisor is a cron-friendly monitoring system that reads the kanban SQLite database, classifies every task into an actionable health state, detects structural anomalies (circular dependencies, stranded tasks), and produces a structured JSON recovery plan with recommended actions.

It is designed to run periodically (e.g., every 5–15 minutes via cron) and output its findings for consumption by downstream automation or human review.

## Architecture

```
┌─────────────────────────────────────────────────┐
│              recovery_supervisor.py              │
│  (cron entry point → reads DB → outputs JSON)   │
├─────────────────────────────────────────────────┤
│  recovery_classify.py                           │
│  (pure classification logic, no I/O)            │
│  - classify_task()     - detect_circular_links()│
│  - classify_all()      - detect_stranded_tasks()│
│  - count_implementation_wip()                   │
├─────────────────────────────────────────────────┤
│  recovery_audit.py                              │
│  (structured JSON logging + secret redaction)   │
│  - RedactingFilter    - AuditLogger             │
│  - redact_dict()                                │
└─────────────────────────────────────────────────┘
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

## Action Types

The recovery plan generates recommended actions:

| Action | Priority | Description |
|--------|----------|-------------|
| `restart_task` | High | Re-queue a timed-out task for execution |
| `check_heartbeat` | Medium | Investigate why a task has stopped heartbeating |
| `escalate_rework` | High | Escalate task after 2+ rework requests |
| `promote_stranded` | Medium | Move todo task to ready when all parents are done |
| `resolve_circular_deps` | High | Fix circular dependency links |
| `wip_limit_reached` | Medium | No new tasks should be dispatched |

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

Rework escalation follows a two-strike rule:
1. First rework request → classified as `needs_rework` (priority: normal)
2. Second+ rework request (block_recurrences >= 2) → classified as `needs_rework_escalate` (priority: high, flagged for human review)

## CLI Usage

```bash
# Run with default DB path
python scripts/recovery_supervisor.py

# Specify custom DB path
python scripts/recovery_supervisor.py --db /path/to/kanban.db

# Override timestamp (for testing)
python scripts/recovery_supervisor.py --now 1700000000

# Pretty-print JSON
python scripts/recovery_supervisor.py --pretty
```

### Default DB Path

The supervisor reads from:
```
~/AppData/Local/hermes/kanban/boards/brandos/kanban.db
```

Override with `--db` or set the environment as needed.

## Cron Setup

Add to crontab (every 10 minutes):

```cron
*/10 * * * * cd /path/to/brandos && python scripts/recovery_supervisor.py --pretty >> /var/log/recovery.log 2>&1
```

Or use Hermes cron for integration with the kanban system.

## Audit Format

All audit entries are structured JSON (NDJSON — one JSON object per line):

```json
{
  "timestamp": "2024-01-15T10:30:00+00:00",
  "level": "ACTION",
  "event": "action:restart_task",
  "logger": "recovery_supervisor",
  "action_type": "restart_task",
  "task_id": "abc123",
  "details": "Timed out after 2h with no heartbeat"
}
```

### Log Levels

- `INFO` — Normal operational events (scan start, plan built)
- `WARN` — Non-fatal issues (DB table missing, read errors)
- `ERROR` — Fatal issues (DB not found)
- `ACTION` — Recovery actions taken on tasks

### Secret Redaction

The audit system automatically redacts:
- **Keys**: `token`, `api_key`, `password`, `secret`, `authorization`, `auth`, `credential`, `cookie`, `session`
- **Values**: Bearer tokens, Basic auth, API key patterns (`sk_*`, `ghp_*`, `xoxb-*`), environment variable references to secrets (`$MY_TOKEN`)

## Testing

```bash
python -m unittest tests.test_recovery -v
```

Test coverage includes:
- All 13 classification states
- Circular dependency detection (2-node, 3-node, self-loop)
- Stranded task detection (full and partial parent completion)
- WIP counting (implementation profiles, exemptions, max WIP)
- Recovery plan structure and content
- Audit logging and secret redaction
- Restart idempotency and state transitions

## Import Usage

All modules work as importable libraries:

```python
from scripts.recovery_classify import classify_task, TaskState, detect_circular_links
from scripts.recovery_audit import AuditLogger, redact_dict
from scripts.recovery_supervisor import build_recovery_plan

# Classify a single task
state = classify_task({"id": "1", "status": "running", ...}, now=int(time.time()))

# Build full recovery plan
plan = build_recovery_plan("/path/to/kanban.db")
print(json.dumps(plan, indent=2))
```
