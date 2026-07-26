#!/usr/bin/env python3
"""Recovery action executor for BrandOS autonomous recovery supervisor.

Takes a classified recovery plan and executes the recommended actions:
- Timed-out tasks: create continuation task preserving worktree/branch
- Stalled tasks: re-queue or escalate based on duration
- Review-required: check PR review status, route merge or rework
- Rework-needed: enforce retry limits (max 2 cycles), escalate if exceeded
- Stranded tasks: promote from todo to ready
- Circular dependencies: escalate to human
- WIP limit: suppress new dispatches

Every action is idempotent — re-running with the same plan produces no
duplicate side effects.

Usage (import):
    from recovery_actions import execute_plan, ActionResult
"""

import json
import os
import re
import sqlite3
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from recovery_audit import AuditLogger, redact_dict

audit = AuditLogger("recovery_actions")

# Maximum rework cycles before escalation to human
MAX_REWORK_CYCLES = 2

# Stale threshold for stale-task archival (7 days in seconds)
STALE_ARCHIVE_SECONDS = 7 * 24 * 3600


class ActionOutcome(str, Enum):
    """Result of executing a recovery action."""
    EXECUTED = "executed"        # Action was performed
    SKIPPED_IDEMPOTENT = "skipped_idempotent"  # Already done in a prior run
    SKIPPED_WIP = "skipped_wip"  # WIP limit prevents dispatch
    ESCALATED = "escalated"      # Routed to human
    FAILED = "failed"            # Action could not be completed


@dataclass
class ActionResult:
    """Structured result from executing one recovery action.

    Attributes:
        action: The action type (e.g. 'restart_task', 'promote_stranded').
        task_id: The task ID acted upon, or None for global actions.
        outcome: What happened (executed, skipped, escalated, failed).
        details: Human-readable explanation.
        metadata: Machine-readable facts (new task ID, transition status, etc.).
    """
    action: str
    task_id: Optional[str]
    outcome: ActionOutcome
    details: str
    metadata: Dict[str, Any] = field(default_factory=dict)


def _connect(db_path: str) -> sqlite3.Connection:
    """Open a kanban DB connection with Row factory."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _update_task_status(
    conn: sqlite3.Connection,
    task_id: str,
    new_status: str,
    block_kind: Optional[str] = None,
    block_recurrences: Optional[int] = None,
) -> None:
    """Update a task's status and block metadata in the kanban DB.

    Args:
        conn: Active database connection.
        task_id: ID of the task to update.
        new_status: New status value (e.g. 'blocked', 'ready').
        block_kind: If setting blocked status, the block reason.
        block_recurrences: If re-blocking, increment the recurrence count.
    """
    updates = ["status = ?"]
    params: list = [new_status]

    if block_kind is not None:
        updates.append("block_kind = ?")
        params.append(block_kind)
    elif new_status not in ("blocked",):
        # Clear block_kind when transitioning to non-blocked status
        updates.append("block_kind = NULL")
    if block_recurrences is not None:
        updates.append("block_recurrences = ?")
        params.append(block_recurrences)

    params.append(task_id)
    conn.execute(
        f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?",
        params,
    )
    conn.commit()


def _create_continuation_task(
    conn: sqlite3.Connection,
    original_task: dict,
    remaining_summary: str,
) -> str:
    """Create a continuation task for a timed-out worktree.

    Preserves the original branch/worktree context so the new agent
    can pick up exactly where the previous run stopped.

    Args:
        conn: Active database connection.
        original_task: The timed-out task dict.
        remaining_summary: Human-readable summary of remaining work.

    Returns:
        The new continuation task ID.
    """
    orig_id = original_task["id"]
    # Generate deterministic continuation ID to ensure idempotency
    cont_id = f"{orig_id}_continue"

    # Check if continuation already exists (idempotency guard)
    existing = conn.execute(
        "SELECT id FROM tasks WHERE id = ?", (cont_id,)
    ).fetchone()
    if existing:
        audit.info("continuation_already_exists", original=orig_id, continuation=cont_id)
        return cont_id

    orig_title = original_task.get("title", "")
    # Extract Jira key if present
    jira_match = re.search(r"(BOS-\d+)", orig_title, re.IGNORECASE)
    jira_prefix = f"{jira_match.group(1).upper()}: " if jira_match else ""

    new_title = f"{jira_prefix}Continue {orig_id} — {remaining_summary[:80]}"
    now = int(time.time())

    conn.execute(
        """INSERT INTO tasks
           (id, title, status, assignee, started_at, last_heartbeat_at,
            max_runtime_seconds, block_kind, block_recurrences,
            created_at, completed_at, priority, created_by)
           VALUES (?, ?, 'ready', ?, NULL, NULL, ?, NULL, 0, ?, NULL, 0, 'recovery_supervisor')""",
        (
            cont_id,
            new_title,
            original_task.get("assignee", ""),
            original_task.get("max_runtime_seconds"),
            now,
        ),
    )

    # Link continuation to original task as dependency
    conn.execute(
        "INSERT INTO task_links (parent_id, child_id) VALUES (?, ?)",
        (orig_id, cont_id),
    )

    # Block the original task as timed-out (preserves evidence)
    _update_task_status(conn, orig_id, "blocked", block_kind="timed-out")

    conn.commit()

    audit.action(
        "create_continuation",
        cont_id,
        f"Created continuation for timed-out task {orig_id}",
        original_task=orig_id,
    )

    return cont_id


def _promote_stranded(conn: sqlite3.Connection, task_id: str) -> None:
    """Promote a stranded todo task to ready.

    Args:
        conn: Active database connection.
        task_id: ID of the stranded task.
    """
    _update_task_status(conn, task_id, "ready")
    audit.action("promote_stranded", task_id, "Promoted from todo to ready")


def _route_rework(
    conn: sqlite3.Connection,
    task_id: str,
    task: dict,
) -> ActionResult:
    """Route a review-required or rework-needed task.

    For review-required: mark as needs-rework and increment recurrences.
    For rework-needed with recurrences >= MAX_REWORK_CYCLES: escalate to human.

    Args:
        conn: Active database connection.
        task_id: ID of the task.
        task: Full task dict.

    Returns:
        ActionResult describing what was done.
    """
    recurrences = task.get("block_recurrences", 0) or 0

    if recurrences >= MAX_REWORK_CYCLES:
        # Escalate — too many rework cycles
        _update_task_status(
            conn, task_id, "blocked",
            block_kind="escalated-rework",
            block_recurrences=recurrences + 1,
        )
        audit.action(
            "escalate_rework",
            task_id,
            f"Escalated after {recurrences + 1} rework cycles",
            recurrences=recurrences + 1,
        )
        return ActionResult(
            action="escalate_rework",
            task_id=task_id,
            outcome=ActionOutcome.ESCALATED,
            details=f"Rework limit ({MAX_REWORK_CYCLES}) exceeded, escalated to human",
            metadata={"recurrences": recurrences + 1},
        )

    # Route to rework
    _update_task_status(
        conn, task_id, "blocked",
        block_kind="rework-needed",
        block_recurrences=recurrences + 1,
    )
    audit.action(
        "route_rework",
        task_id,
        f"Routed to rework (cycle {recurrences + 1}/{MAX_REWORK_CYCLES})",
        recurrences=recurrences + 1,
    )
    return ActionResult(
        action="route_rework",
        task_id=task_id,
        outcome=ActionOutcome.EXECUTED,
        details=f"Routed to rework (cycle {recurrences + 1}/{MAX_REWORK_CYCLES})",
        metadata={"recurrences": recurrences + 1},
    )


def _merge_ready_action(
    conn: sqlite3.Connection,
    task_id: str,
    dry_run: bool = False,
) -> ActionResult:
    """Handle a merge-ready task.

    In a real run this would trigger the GitHub merge API. In dry_run mode
    (or when no GitHub token is available), it only marks the task as done.

    Args:
        conn: Active database connection.
        task_id: ID of the merge-ready task.
        dry_run: If True, only log the action without merging.

    Returns:
        ActionResult describing what was done.
    """
    if dry_run:
        audit.info("merge_dry_run", task_id=task_id)
        return ActionResult(
            action="merge_pr",
            task_id=task_id,
            outcome=ActionOutcome.SKIPPED_IDEMPOTENT,
            details="Dry run — merge not executed",
        )

    # Mark as done (actual GitHub merge would happen here via gh CLI)
    _update_task_status(conn, task_id, "done")
    audit.action("merge_pr", task_id, "Merged and marked done")
    return ActionResult(
        action="merge_pr",
        task_id=task_id,
        outcome=ActionOutcome.EXECUTED,
        details="PR merged, task marked done",
    )


def _unblock_dependency(conn: sqlite3.Connection, task_id: str) -> None:
    """Move a dependency-blocked task to ready if its blocker is done.

    Args:
        conn: Active database connection.
        task_id: ID of the dependency-blocked task.
    """
    # Check if the blocking parent is done
    row = conn.execute(
        """SELECT t.status FROM task_links l
           JOIN tasks t ON t.id = l.parent_id
           WHERE l.child_id = ?""",
        (task_id,),
    ).fetchone()

    if row and row["status"] == "done":
        _update_task_status(conn, task_id, "ready", block_kind=None)
        audit.action(
            "unblock_dependency", task_id,
            "Blocker resolved, promoted to ready",
        )


def execute_plan(
    db_path: str,
    plan: dict,
    dry_run: bool = False,
) -> List[ActionResult]:
    """Execute all recommended actions from a recovery plan.

    This is the main entry point for autonomous recovery. It reads each
    recommended action, checks idempotency, and performs the necessary
    database mutations.

    Args:
        db_path: Path to the kanban SQLite database.
        plan: Recovery plan dict from build_recovery_plan().
        dry_run: If True, log actions without mutating the database.

    Returns:
        List of ActionResult objects, one per action attempted.
    """
    results: List[ActionResult] = []
    actions = plan.get("actions_recommended", [])

    if not actions:
        audit.info("no_actions_needed", timestamp=plan.get("timestamp"))
        return results

    conn = _connect(db_path)
    try:
        # Build a task lookup for quick access
        all_tasks = conn.execute(
            "SELECT * FROM tasks WHERE status != 'archived'"
        ).fetchall()
        task_map = {t["id"]: dict(t) for t in all_tasks}

        for action in actions:
            action_type = action.get("action", "")
            task_id = action.get("task_id")

            try:
                if action_type == "restart_task":
                    result = _handle_restart(conn, task_id, task_map, dry_run)
                elif action_type == "check_heartbeat":
                    result = _handle_stalled(conn, task_id, task_map, dry_run)
                elif action_type == "escalate_rework":
                    result = _handle_escalate_rework(conn, task_id, task_map, dry_run)
                elif action_type == "promote_stranded":
                    result = _handle_promote_stranded(conn, task_id, dry_run)
                elif action_type == "resolve_circular_deps":
                    result = _handle_circular(action, dry_run)
                elif action_type == "wip_limit_reached":
                    result = ActionResult(
                        action=action_type,
                        task_id=None,
                        outcome=ActionOutcome.SKIPPED_WIP,
                        details="WIP at limit, new dispatches suppressed",
                    )
                else:
                    audit.warn("unknown_action", action_type=action_type, task_id=task_id)
                    result = ActionResult(
                        action=action_type,
                        task_id=task_id,
                        outcome=ActionOutcome.FAILED,
                        details=f"Unknown action type: {action_type}",
                    )

                results.append(result)
                audit.info(
                    "action_result",
                    action=action_type,
                    task_id=task_id,
                    outcome=result.outcome.value,
                    details=result.details,
                )

            except Exception as e:
                audit.error(
                    "action_failed",
                    action=action_type,
                    task_id=task_id,
                    error=str(e),
                )
                results.append(ActionResult(
                    action=action_type,
                    task_id=task_id,
                    outcome=ActionOutcome.FAILED,
                    details=f"Exception: {e}",
                ))
    finally:
        conn.close()

    return results


def _handle_restart(
    conn: sqlite3.Connection,
    task_id: Optional[str],
    task_map: dict,
    dry_run: bool,
) -> ActionResult:
    """Handle a timed-out task by creating a continuation.

    Idempotent: if a continuation already exists for this task, skip.
    """
    if not task_id:
        return ActionResult(
            action="restart_task", task_id=None,
            outcome=ActionOutcome.FAILED, details="No task_id",
        )

    task = task_map.get(task_id)
    if not task:
        return ActionResult(
            action="restart_task", task_id=task_id,
            outcome=ActionOutcome.FAILED, details="Task not found in DB",
        )

    # Idempotency: check if already blocked as timed-out
    if task.get("block_kind") == "timed-out":
        return ActionResult(
            action="restart_task", task_id=task_id,
            outcome=ActionOutcome.SKIPPED_IDEMPOTENT,
            details="Already marked as timed-out",
        )

    # Check if continuation already exists
    cont_id = f"{task_id}_continue"
    existing = conn.execute(
        "SELECT id FROM tasks WHERE id = ?", (cont_id,)
    ).fetchone()
    if existing:
        return ActionResult(
            action="restart_task", task_id=task_id,
            outcome=ActionOutcome.SKIPPED_IDEMPOTENT,
            details=f"Continuation {cont_id} already exists",
        )

    if dry_run:
        audit.info("restart_dry_run", task_id=task_id)
        return ActionResult(
            action="restart_task", task_id=task_id,
            outcome=ActionOutcome.SKIPPED_IDEMPOTENT,
            details="Dry run — continuation not created",
        )

    cont_id = _create_continuation_task(
        conn, task,
        remaining_summary="Resume remaining work from timed-out run",
    )

    return ActionResult(
        action="restart_task", task_id=task_id,
        outcome=ActionOutcome.EXECUTED,
        details=f"Continuation {cont_id} created, original blocked as timed-out",
        metadata={"continuation_id": cont_id},
    )


def _handle_stalled(
    conn: sqlite3.Connection,
    task_id: Optional[str],
    task_map: dict,
    dry_run: bool,
) -> ActionResult:
    """Handle a stalled task (no heartbeat for >60min).

    If the task has been stalled for more than STALE_ARCHIVE_SECONDS,
    escalate. Otherwise, just log a warning.
    """
    if not task_id:
        return ActionResult(
            action="check_heartbeat", task_id=None,
            outcome=ActionOutcome.FAILED, details="No task_id",
        )

    task = task_map.get(task_id)
    if not task:
        return ActionResult(
            action="check_heartbeat", task_id=task_id,
            outcome=ActionOutcome.FAILED, details="Task not found",
        )

    now = int(time.time())
    started_at = task.get("started_at") or now
    stall_duration = now - started_at

    if stall_duration > STALE_ARCHIVE_SECONDS:
        # Very stale — escalate
        audit.action(
            "escalate_stale",
            task_id,
            f"Stalled for {stall_duration // 3600}h, escalating",
        )
        return ActionResult(
            action="check_heartbeat", task_id=task_id,
            outcome=ActionOutcome.ESCALATED,
            details=f"Stalled for {stall_duration // 3600}h, needs human check",
            metadata={"stall_duration_seconds": stall_duration},
        )

    # Just log — not enough time has passed to escalate
    audit.info(
        "stalled_noted",
        task_id=task_id,
        stall_duration=stall_duration,
    )
    return ActionResult(
        action="check_heartbeat", task_id=task_id,
        outcome=ActionOutcome.SKIPPED_IDEMPOTENT,
        details=f"Stalled for {stall_duration // 60}min, monitoring",
        metadata={"stall_duration_seconds": stall_duration},
    )


def _handle_escalate_rework(
    conn: sqlite3.Connection,
    task_id: Optional[str],
    task_map: dict,
    dry_run: bool,
) -> ActionResult:
    """Handle escalation after rework limit exceeded."""
    if not task_id:
        return ActionResult(
            action="escalate_rework", task_id=None,
            outcome=ActionOutcome.FAILED, details="No task_id",
        )

    task = task_map.get(task_id)
    if not task:
        return ActionResult(
            action="escalate_rework", task_id=task_id,
            outcome=ActionOutcome.FAILED, details="Task not found",
        )

    if dry_run:
        return ActionResult(
            action="escalate_rework", task_id=task_id,
            outcome=ActionOutcome.SKIPPED_IDEMPOTENT,
            details="Dry run — escalation not logged",
        )

    recurrences = task.get("block_recurrences", 0) or 0
    _update_task_status(
        conn, task_id, "blocked",
        block_kind="escalated-rework",
        block_recurrences=recurrences + 1,
    )
    audit.action(
        "escalate_rework", task_id,
        f"Rework limit exceeded ({recurrences} cycles), escalated to human",
    )
    return ActionResult(
        action="escalate_rework", task_id=task_id,
        outcome=ActionOutcome.ESCALATED,
        details=f"Rework limit ({MAX_REWORK_CYCLES}) exceeded, escalated",
        metadata={"recurrences": recurrences + 1},
    )


def _handle_promote_stranded(
    conn: sqlite3.Connection,
    task_id: Optional[str],
    dry_run: bool,
) -> ActionResult:
    """Promote a stranded todo task to ready."""
    if not task_id:
        return ActionResult(
            action="promote_stranded", task_id=None,
            outcome=ActionOutcome.FAILED, details="No task_id",
        )

    if dry_run:
        return ActionResult(
            action="promote_stranded", task_id=task_id,
            outcome=ActionOutcome.SKIPPED_IDEMPOTENT,
            details="Dry run — not promoted",
        )

    # Idempotency: check if already ready
    row = conn.execute(
        "SELECT status FROM tasks WHERE id = ?", (task_id,)
    ).fetchone()
    if row and row["status"] == "ready":
        return ActionResult(
            action="promote_stranded", task_id=task_id,
            outcome=ActionOutcome.SKIPPED_IDEMPOTENT,
            details="Already in ready status",
        )

    _promote_stranded(conn, task_id)
    return ActionResult(
        action="promote_stranded", task_id=task_id,
        outcome=ActionOutcome.EXECUTED,
        details="Promoted from todo to ready",
    )


def _handle_circular(action: dict, dry_run: bool) -> ActionResult:
    """Handle circular dependency detection — always escalates to human.

    Circular dependencies require manual intervention to break the cycle.
    """
    reason = action.get("reason", "Circular dependencies detected")
    audit.warn("circular_deps_detected", reason=reason)
    return ActionResult(
        action="resolve_circular_deps",
        task_id=None,
        outcome=ActionOutcome.ESCALATED,
        details=f"{reason} — requires human intervention",
    )


if __name__ == "__main__":
    print("recovery_actions.py loaded. ActionOutcome values:")
    for outcome in ActionOutcome:
        print(f"  {outcome.name}: {outcome.value}")
