#!/usr/bin/env python3
"""Task state classification engine for BrandOS autonomous recovery supervisor.

Pure classification logic with no I/O side effects. Classifies kanban tasks
into actionable states, detects dependency cycles, identifies stranded tasks,
and counts implementation WIP.
"""

from enum import Enum
from typing import Dict, List, Set, Tuple


class TaskState(str, Enum):
    """Possible classification states for a kanban task."""
    TIMED_OUT = "timed_out"
    STALLED = "stalled"
    NEEDS_REVIEW = "needs_review"
    NEEDS_REWORK = "needs_rework"
    NEEDS_REWORK_ESCALATE = "needs_rework_escalate"
    MERGE_READY = "merge_ready"
    BLOCKED_HUMAN = "blocked_human"
    BLOCKED_DEPENDENCY = "blocked_dependency"
    STRANDED = "stranded"
    READY_DISPATCH = "ready_dispatch"
    RUNNING_HEALTHY = "running_healthy"
    DONE = "done"
    OTHER = "other"


# Heartbeat thresholds in seconds
HEARTBEAT_STALE_SECONDS = 60 * 60       # 60 minutes → stalled
HEARTBEAT_TIMEOUT_SECONDS = 30 * 60     # 30 minutes → timed out (heartbeat stale for timeout)

# Implementation profiles that consume WIP
IMPLEM_PROFILES: Set[str] = {
    "brandosbackend",
    "brandosfrontend",
    "brandosintelligence",
    "brandospreview",
}

# Profiles that do NOT consume WIP (quality review, orchestrator, social)
NON_WIP_PROFILES: Set[str] = {
    "brandosquality",
    "brandosorchestrator",
    "brandossocial",
}


def classify_task(task: dict, now: int) -> TaskState:
    """Classify a single kanban task into a TaskState.

    Args:
        task: Task dict with keys like 'status', 'started_at', 'last_heartbeat_at',
              'block_kind', 'block_recurrences', 'assignee', 'max_runtime_seconds',
              'id', 'title', etc.
        now: Current Unix timestamp (seconds since epoch).

    Returns:
        TaskState enum value for the task's current classification.
    """
    status = task.get("status", "")
    started_at = task.get("started_at")
    # Accept both last_heartbeat_at (real DB) and heartbeat_at (tests/legacy)
    heartbeat_at = task.get("last_heartbeat_at") or task.get("heartbeat_at")
    block_kind = task.get("block_kind", "")
    block_recurrences = task.get("block_recurrences", 0) or 0
    max_runtime = task.get("max_runtime_seconds")

    # Done is always done
    if status == "done":
        return TaskState.DONE

    # Running tasks: check heartbeat and timeout
    if status == "running":
        heartbeat_age = None
        if heartbeat_at:
            heartbeat_age = now - heartbeat_at

        # Timed out: started + max_runtime < now AND (no heartbeat or heartbeat > 30min old)
        if started_at and max_runtime and max_runtime > 0:
            elapsed = now - started_at
            no_recent_heartbeat = heartbeat_at is None or (heartbeat_age is not None and heartbeat_age >= HEARTBEAT_TIMEOUT_SECONDS)
            if elapsed > max_runtime and no_recent_heartbeat:
                return TaskState.TIMED_OUT

        # Stalled: no heartbeat for > 60min
        if heartbeat_at is None or (heartbeat_age is not None and heartbeat_age >= HEARTBEAT_STALE_SECONDS):
            return TaskState.STALLED

        # Healthy running
        return TaskState.RUNNING_HEALTHY

    # Blocked tasks: check block kind
    if status == "blocked":
        if block_kind == "review-required":
            return TaskState.NEEDS_REVIEW
        if block_kind == "rework-needed":
            if block_recurrences >= 2:
                return TaskState.NEEDS_REWORK_ESCALATE
            return TaskState.NEEDS_REWORK
        if block_kind == "merge-ready":
            return TaskState.MERGE_READY
        if block_kind == "needs_input":
            return TaskState.BLOCKED_HUMAN
        if block_kind == "dependency":
            return TaskState.BLOCKED_DEPENDENCY
        # Generic blocked with unknown kind
        return TaskState.BLOCKED_HUMAN

    # Stranded: todo but parents all done (needs caller to pass parent context)
    # We check the stranded flag if present, otherwise caller should use detect_stranded_tasks
    if status == "todo" and task.get("_stranded_flag"):
        return TaskState.STRANDED

    # Ready for dispatch
    if status == "ready":
        assignee = task.get("assignee", "")
        if not assignee or assignee == "":
            return TaskState.READY_DISPATCH
        # Has assignee but ready → still needs dispatch
        return TaskState.READY_DISPATCH

    # Todo with no special conditions
    if status == "todo":
        return TaskState.OTHER

    # Everything else
    return TaskState.OTHER


def classify_all(tasks: list, now: int) -> Dict[str, list]:
    """Classify a list of tasks and group them by state.

    Args:
        tasks: List of task dicts from the kanban DB.
        now: Current Unix timestamp.

    Returns:
        Dict mapping TaskState value strings to lists of task dicts.
    """
    grouped: Dict[str, list] = {state.value: [] for state in TaskState}
    for task in tasks:
        state = classify_task(task, now)
        grouped[state.value].append(task)
    return grouped


def detect_circular_links(task_links: List[Tuple[str, str]]) -> List[List[str]]:
    """Detect cycles in task dependency links.

    Args:
        task_links: List of (parent_id, child_id) tuples.

    Returns:
        List of cycles found. Each cycle is a list of task IDs forming the loop,
        where the first and last elements are the same node (closing the cycle).
        Returns empty list if no cycles exist.
    """
    # Build adjacency list
    graph: Dict[str, List[str]] = {}
    for parent, child in task_links:
        graph.setdefault(parent, []).append(child)

    WHITE, GRAY, BLACK = 0, 1, 2
    color: Dict[str, int] = {}
    parent_map: Dict[str, str] = {}
    cycles: List[List[str]] = []

    all_nodes = set()
    for p, c in task_links:
        all_nodes.add(p)
        all_nodes.add(c)

    for node in all_nodes:
        color[node] = WHITE

    def dfs(node: str) -> None:
        """Depth-first search to detect back edges (cycles)."""
        color[node] = GRAY
        for neighbor in graph.get(node, []):
            if color.get(neighbor) == GRAY:
                # Found a cycle: reconstruct from neighbor back to node
                cycle = [neighbor]
                current = node
                while current != neighbor:
                    cycle.append(current)
                    current = parent_map.get(current, "")
                    if not current:
                        break
                cycle.append(neighbor)  # close the cycle
                cycle.reverse()
                cycles.append(cycle)
            elif color.get(neighbor) == WHITE:
                parent_map[neighbor] = node
                dfs(neighbor)
        color[node] = BLACK

    for node in sorted(all_nodes):
        if color.get(node) == WHITE:
            dfs(node)

    return cycles


def detect_stranded_tasks(tasks: list, links: List[Tuple[str, str]]) -> List[str]:
    """Find tasks in 'todo' status whose all parent tasks are 'done'.

    These tasks should be promoted to 'ready' but are stuck in 'todo'.

    Args:
        tasks: List of task dicts.
        links: List of (parent_id, child_id) dependency tuples.

    Returns:
        List of task IDs that are stranded (should be ready but are in todo).
    """
    task_map = {t["id"]: t for t in tasks}

    # Build child -> parents mapping
    child_to_parents: Dict[str, List[str]] = {}
    for parent_id, child_id in links:
        child_to_parents.setdefault(child_id, []).append(parent_id)

    stranded = []
    for task in tasks:
        if task.get("status") != "todo":
            continue

        task_id = task["id"]
        parents = child_to_parents.get(task_id, [])

        # No parents → should already be ready, but if it's todo it's not stranded
        # (it's likely awaiting triage or assignment)
        if not parents:
            continue

        # Check if ALL parents are done
        all_parents_done = all(
            task_map.get(pid, {}).get("status") == "done"
            for pid in parents
        )

        if all_parents_done:
            stranded.append(task_id)

    return stranded


def count_implementation_wip(tasks: list) -> int:
    """Count active implementation tasks consuming WIP capacity.

    Only tasks assigned to implementation profiles (brandosbackend, brandosfrontend,
    brandosintelligence, brandospreview) in running or blocked status count.
    Quality review, orchestrator, and social tasks do NOT consume WIP.

    Args:
        tasks: List of task dicts.

    Returns:
        Number of tasks consuming WIP slots.
    """
    count = 0
    for task in tasks:
        status = task.get("status", "")
        assignee = task.get("assignee", "") or ""

        # Only running or blocked tasks consume WIP
        if status not in ("running", "blocked"):
            continue

        # Non-WIP profiles are exempt
        if assignee in NON_WIP_PROFILES:
            continue

        # Must be an implementation profile
        if assignee in IMPLEM_PROFILES:
            count += 1

    return count


if __name__ == "__main__":
    import sys
    print(f"recovery_classify.py loaded. TaskState values: {[s.value for s in TaskState]}")
