#!/usr/bin/env python3
"""Autopilot dispatcher data-collection script.

Gathers current kanban board state for the BrandOS continuous delivery
autopilot. Runs as a cron script; stdout is injected into the agent prompt.

Output: JSON with board state, WIP counts, and tasks needing attention.
"""
import json
import os
import sqlite3
import sys
import time

KANBAN_DB = os.path.join(
    os.path.expanduser("~"),
    "AppData", "Local", "hermes", "kanban", "boards", "brandos", "kanban.db"
)

WIP_LIMIT = 2
REVIEW_STATUSES = {"blocked"}  # tasks blocked on review-required
ACTIVE_STATUSES = {"running", "blocked"}

def get_tasks(db_path):
    """Read all non-done, non-archived tasks from kanban DB."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT id, title, assignee, status, priority, branch_name,
               workspace_path, block_kind, created_at, started_at,
               completed_at, result, idempotency_key, consecutive_failures
        FROM tasks
        WHERE status NOT IN ('done', 'archived')
        ORDER BY priority DESC, created_at ASC
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

def get_recent_completions(db_path, hours=24):
    """Get tasks completed in the last N hours."""
    cutoff = int(time.time()) - (hours * 3600)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT id, title, assignee, status, completed_at, result
        FROM tasks
        WHERE status = 'done' AND completed_at >= ?
        ORDER BY completed_at DESC
    """, (cutoff,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

def extract_jira_key(title):
    """Extract BOS-NNN from task title."""
    import re
    m = re.match(r"(BOS-\d+)", title)
    return m.group(1) if m else None

def classify_tasks(tasks):
    """Classify tasks by their role in the autopilot loop."""
    active = []       # running or blocked (counts toward WIP)
    needs_review = [] # blocked with review-required
    needs_rework = [] # blocked with rework-needed
    other_blocked = []

    for t in tasks:
        if t["status"] in ACTIVE_STATUSES:
            active.append(t)
            if t["status"] == "blocked":
                if t.get("block_kind") == "review-required":
                    needs_review.append(t)
                elif t.get("block_kind") == "rework-needed":
                    needs_rework.append(t)
                else:
                    other_blocked.append(t)

    return {
        "active": active,
        "needs_review": needs_review,
        "needs_rework": needs_rework,
        "other_blocked": other_blocked,
    }

def main():
    if not os.path.exists(KANBAN_DB):
        print(json.dumps({"error": f"kanban DB not found: {KANBAN_DB}"}))
        sys.exit(1)

    tasks = get_tasks(KANBAN_DB)
    recent = get_recent_completions(KANBAN_DB, hours=24)
    classified = classify_tasks(tasks)

    active_count = len(classified["active"])
    wip_remaining = max(0, WIP_LIMIT - active_count)

    # Extract BOS keys already in flight (to avoid duplicate dispatch)
    inflight_keys = set()
    for t in tasks:
        key = extract_jira_key(t["title"])
        if key:
            inflight_keys.add(key)

    # Also check recent completions to avoid re-dispatch
    for t in recent:
        key = extract_jira_key(t["title"])
        if key:
            inflight_keys.add(key)

    report = {
        "timestamp": int(time.time()),
        "wip_limit": WIP_LIMIT,
        "active_count": active_count,
        "wip_remaining": wip_remaining,
        "inflight_jira_keys": sorted(inflight_keys),
        "active_tasks": [
            {
                "id": t["id"],
                "title": t["title"],
                "assignee": t["assignee"],
                "status": t["status"],
                "block_kind": t.get("block_kind"),
                "jira_key": extract_jira_key(t["title"]),
            }
            for t in classified["active"]
        ],
        "needs_review": [
            {
                "id": t["id"],
                "title": t["title"],
                "assignee": t["assignee"],
                "jira_key": extract_jira_key(t["title"]),
            }
            for t in classified["needs_review"]
        ],
        "needs_rework": [
            {
                "id": t["id"],
                "title": t["title"],
                "assignee": t["assignee"],
                "jira_key": extract_jira_key(t["title"]),
            }
            for t in classified["needs_rework"]
        ],
        "recent_completions_24h": [
            {
                "id": t["id"],
                "title": t["title"],
                "assignee": t["assignee"],
                "jira_key": extract_jira_key(t["title"]),
            }
            for t in recent[:10]
        ],
    }

    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
