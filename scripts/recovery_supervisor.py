#!/usr/bin/env python3
"""BrandOS autonomous recovery supervisor — main data-collection script.

Cron-friendly script that reads the kanban SQLite DB, classifies tasks into
actionable states, and outputs a structured JSON recovery plan.

Usage:
    python scripts/recovery_supervisor.py
    python scripts/recovery_supervisor.py --db /path/to/kanban.db
    python scripts/recovery_supervisor.py --now 1700000000
"""

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Allow importing as module or running directly
if __name__ == "__main__" and __package__ is None:
    _here = Path(__file__).resolve().parent
    if str(_here) not in sys.path:
        sys.path.insert(0, str(_here))

from recovery_classify import (
    TaskState,
    classify_all,
    classify_task,
    count_implementation_wip,
    detect_circular_links,
    detect_stranded_tasks,
)
from recovery_audit import AuditLogger, redact_dict
from recovery_actions import execute_plan, ActionResult, ActionOutcome
from recovery_notify import notify_escalation, notify_daily_digest

# Default kanban DB path (Windows ~/AppData)
KANBAN_DB = os.path.expanduser("~/AppData/Local/hermes/kanban/boards/brandos/kanban.db")

# WIP limit for implementation profiles
WIP_LIMIT = 2

# Jira key pattern (e.g., BOS-151)
_JIRA_KEY_RE = re.compile(r"(BOS-\d+)", re.IGNORECASE)

audit = AuditLogger("recovery_supervisor")


def get_tasks(db_path: str) -> List[dict]:
    """Read all non-archived tasks from the kanban database.

    Args:
        db_path: Path to the kanban SQLite database file.

    Returns:
        List of task dicts with all columns from the tasks table.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            "SELECT * FROM tasks WHERE status != 'archived'"
        )
        rows = cur.fetchall()
        return [dict(row) for row in rows]
    except sqlite3.OperationalError:
        audit.warn("db_read_error", path=db_path, table="tasks")
        return []
    finally:
        conn.close()


def get_task_links(db_path: str) -> List[Tuple[str, str]]:
    """Read parent→child dependency links from the kanban database.

    Args:
        db_path: Path to the kanban SQLite database file.

    Returns:
        List of (parent_id, child_id) tuples.
    """
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            "SELECT parent_id, child_id FROM task_links"
        )
        return [(row[0], row[1]) for row in cur.fetchall()]
    except sqlite3.OperationalError:
        audit.warn("db_read_error", path=db_path, table="task_links")
        return []
    finally:
        conn.close()


def get_task_runs(db_path: str, task_id: str) -> List[dict]:
    """Get run history for a specific task.

    Args:
        db_path: Path to the kanban SQLite database file.
        task_id: ID of the task to get runs for.

    Returns:
        List of run record dicts, ordered by creation time.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            "SELECT * FROM task_runs WHERE task_id = ? ORDER BY created_at",
            (task_id,),
        )
        return [dict(row) for row in cur.fetchall()]
    except sqlite3.OperationalError:
        audit.warn("db_read_error", path=db_path, table="task_runs", task_id=task_id)
        return []
    finally:
        conn.close()


def extract_jira_key(title: str) -> Optional[str]:
    """Extract a Jira-style key (e.g., BOS-151) from a task title.

    Args:
        title: Task title string.

    Returns:
        The first BOS-NNN match found, or None if no key present.
    """
    if not title:
        return None
    m = _JIRA_KEY_RE.search(title)
    return m.group(1).upper() if m else None


def build_recovery_plan(db_path: str, now: Optional[int] = None) -> Dict[str, Any]:
    """Build a complete recovery plan by classifying all tasks.

    Main entry point for the supervisor. Reads the DB, classifies tasks,
    detects anomalies, and produces a structured recovery plan.

    Args:
        db_path: Path to the kanban SQLite database file.
        now: Current Unix timestamp. Defaults to int(time.time()).

    Returns:
        Dict containing the full recovery plan with classified tasks,
        WIP counts, detected anomalies, and recommended actions.
    """
    if now is None:
        now = int(time.time())

    audit.info("recovery_scan_start", db_path=db_path, now=now)

    tasks = get_tasks(db_path)
    links = get_task_links(db_path)

    # Classify all tasks
    classified = classify_all(tasks, now)

    # Detect anomalies
    circular = detect_circular_links(links)
    stranded_ids = detect_stranded_tasks(tasks, links)
    wip_count = count_implementation_wip(tasks)

    # Mark stranded tasks in the classified output
    stranded_tasks = []
    for task in tasks:
        if task["id"] in stranded_ids:
            stranded_tasks.append({
                "id": task["id"],
                "title": task.get("title", ""),
                "jira_key": extract_jira_key(task.get("title", "")),
                "assignee": task.get("assignee", ""),
            })

    # Enrich task summaries for each category
    def summarize_tasks(task_list: list) -> list:
        """Create summary dicts for a list of tasks."""
        return [
            {
                "id": t["id"],
                "title": t.get("title", ""),
                "jira_key": extract_jira_key(t.get("title", "")),
                "status": t.get("status", ""),
                "assignee": t.get("assignee", ""),
                "block_kind": t.get("block_kind", ""),
            }
            for t in task_list
        ]

    # Build recommended actions
    actions = []

    for t in classified.get(TaskState.TIMED_OUT.value, []):
        actions.append({
            "action": "restart_task",
            "task_id": t["id"],
            "reason": f"Timed out (started_at={t.get('started_at')}, max_runtime={t.get('max_runtime_seconds')}s)",
            "priority": "high",
        })

    for t in classified.get(TaskState.STALLED.value, []):
        actions.append({
            "action": "check_heartbeat",
            "task_id": t["id"],
            "reason": "No heartbeat for >60min",
            "priority": "medium",
        })

    for t in classified.get(TaskState.NEEDS_REWORK_ESCALATE.value, []):
        actions.append({
            "action": "escalate_rework",
            "task_id": t["id"],
            "reason": f"Rework requested {t.get('block_recurrences', 0)} times, escalating",
            "priority": "high",
        })

    for task_id in stranded_ids:
        actions.append({
            "action": "promote_stranded",
            "task_id": task_id,
            "reason": "All parents done but task still in todo",
            "priority": "medium",
        })

    if circular:
        actions.append({
            "action": "resolve_circular_deps",
            "task_id": None,
            "reason": f"Found {len(circular)} circular dependency cycle(s)",
            "priority": "high",
        })

    if wip_count >= WIP_LIMIT:
        actions.append({
            "action": "wip_limit_reached",
            "task_id": None,
            "reason": f"WIP count ({wip_count}) >= limit ({WIP_LIMIT})",
            "priority": "medium",
        })

    plan = {
        "timestamp": now,
        "wip": {
            "current": wip_count,
            "limit": WIP_LIMIT,
            "at_limit": wip_count >= WIP_LIMIT,
        },
        "timed_out_tasks": summarize_tasks(classified.get(TaskState.TIMED_OUT.value, [])),
        "stalled_tasks": summarize_tasks(classified.get(TaskState.STALLED.value, [])),
        "needs_review": summarize_tasks(classified.get(TaskState.NEEDS_REVIEW.value, [])),
        "needs_rework": summarize_tasks(classified.get(TaskState.NEEDS_REWORK.value, [])),
        "needs_rework_escalate": summarize_tasks(classified.get(TaskState.NEEDS_REWORK_ESCALATE.value, [])),
        "merge_ready": summarize_tasks(classified.get(TaskState.MERGE_READY.value, [])),
        "blocked_human": summarize_tasks(classified.get(TaskState.BLOCKED_HUMAN.value, [])),
        "blocked_dependency": summarize_tasks(classified.get(TaskState.BLOCKED_DEPENDENCY.value, [])),
        "stranded": stranded_tasks,
        "circular_links": circular,
        "ready_for_dispatch": summarize_tasks(classified.get(TaskState.READY_DISPATCH.value, [])),
        "healthy_running": summarize_tasks(classified.get(TaskState.RUNNING_HEALTHY.value, [])),
        "actions_recommended": actions,
    }

    audit.info(
        "recovery_plan_built",
        total_tasks=len(tasks),
        actions_count=len(actions),
        wip=wip_count,
        timed_out=len(classified.get(TaskState.TIMED_OUT.value, [])),
        stalled=len(classified.get(TaskState.STALLED.value, [])),
        stranded=len(stranded_ids),
        circular_cycles=len(circular),
    )

    return plan


def main() -> None:
    """CLI entry point. Parses args, builds recovery plan, prints JSON."""
    parser = argparse.ArgumentParser(
        description="BrandOS autonomous recovery supervisor"
    )
    parser.add_argument(
        "--db",
        default=KANBAN_DB,
        help=f"Path to kanban SQLite DB (default: {KANBAN_DB})",
    )
    parser.add_argument(
        "--now",
        type=int,
        default=None,
        help="Override current Unix timestamp (for testing)",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute recommended actions (default is plan-only/dry-run)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log actions without mutating the database (implies --execute)",
    )
    parser.add_argument(
        "--notify",
        action="store_true",
        help="Send Telegram notifications for escalations and daily digest",
    )
    args = parser.parse_args()

    if not os.path.exists(args.db):
        audit.error("db_not_found", path=args.db)
        print(json.dumps({"error": f"Database not found: {args.db}"}, indent=2))
        sys.exit(1)

    plan = build_recovery_plan(args.db, now=args.now)

    # Execute actions if requested
    action_results = []
    if args.execute or args.dry_run:
        action_results_raw = execute_plan(args.db, plan, dry_run=args.dry_run)
        action_results = [
            {
                "action": r.action,
                "task_id": r.task_id,
                "outcome": r.outcome.value,
                "details": r.details,
                "metadata": r.metadata,
            }
            for r in action_results_raw
        ]
        plan["action_results"] = action_results

    # Send notifications if requested
    if args.notify:
        notify_daily_digest(plan)
        if action_results:
            notify_escalation(action_results, board_summary=plan.get("wip"))

    indent = 2 if args.pretty else None
    print(json.dumps(plan, indent=indent, default=str))


if __name__ == "__main__":
    main()
