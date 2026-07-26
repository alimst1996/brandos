#!/usr/bin/env python3
"""Autopilot daily reporter data-collection script.

Gathers board statistics for the BrandOS daily executive report.
Runs as a cron script before the agent formats and sends the Telegram report.

Output: JSON with 24h stats, current WIP, blocked tasks, and risk signals.
"""
import json
import os
import sqlite3
import sys
import time
from collections import Counter

KANBAN_DB = os.path.join(
    os.path.expanduser("~"),
    "AppData", "Local", "hermes", "kanban", "boards", "brandos", "kanban.db"
)

def query(db_path, sql, params=()):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(sql, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

def extract_jira_key(title):
    import re
    m = re.match(r"(BOS-\d+)", title)
    return m.group(1) if m else None

def main():
    if not os.path.exists(KANBAN_DB):
        print(json.dumps({"error": f"kanban DB not found: {KANBAN_DB}"}))
        sys.exit(1)

    now = int(time.time())
    h24 = now - 86400
    h7d = now - 7 * 86400

    # Current active tasks
    active = query(KANBAN_DB, """
        SELECT id, title, assignee, status, block_kind, started_at
        FROM tasks WHERE status IN ('running', 'blocked')
        ORDER BY priority DESC, created_at ASC
    """)

    # Completed in last 24h
    completed_24h = query(KANBAN_DB, """
        SELECT id, title, assignee, completed_at
        FROM tasks WHERE status = 'done' AND completed_at >= ?
        ORDER BY completed_at DESC
    """, (h24,))

    # Completed in last 7 days
    completed_7d = query(KANBAN_DB, """
        SELECT id, title, assignee, completed_at
        FROM tasks WHERE status = 'done' AND completed_at >= ?
        ORDER BY completed_at DESC
    """, (h7d,))

    # Blocked tasks (potential blockers)
    blocked = query(KANBAN_DB, """
        SELECT id, title, assignee, block_kind, started_at
        FROM tasks WHERE status = 'blocked'
        ORDER BY started_at ASC
    """)

    # Tasks with failures
    failed = query(KANBAN_DB, """
        SELECT id, title, assignee, consecutive_failures, last_failure_error
        FROM tasks WHERE consecutive_failures > 0 AND status NOT IN ('done', 'archived')
        ORDER BY consecutive_failures DESC
    """)

    # Per-assignee stats for last 7d
    assignee_completions = Counter()
    for t in completed_7d:
        assignee_completions[t["assignee"]] += 1

    report = {
        "timestamp": now,
        "date": time.strftime("%Y-%m-%d", time.localtime(now)),
        "active_tasks": [
            {
                "id": t["id"],
                "title": t["title"],
                "assignee": t["assignee"],
                "status": t["status"],
                "block_kind": t.get("block_kind"),
                "jira_key": extract_jira_key(t["title"]),
                "running_hours": round((now - t["started_at"]) / 3600, 1) if t["started_at"] else None,
            }
            for t in active
        ],
        "completed_24h": [
            {
                "id": t["id"],
                "title": t["title"],
                "assignee": t["assignee"],
                "jira_key": extract_jira_key(t["title"]),
            }
            for t in completed_24h
        ],
        "completed_7d_count": len(completed_7d),
        "completed_24h_count": len(completed_24h),
        "blocked_tasks": [
            {
                "id": t["id"],
                "title": t["title"],
                "assignee": t["assignee"],
                "block_kind": t.get("block_kind"),
                "jira_key": extract_jira_key(t["title"]),
            }
            for t in blocked
        ],
        "failed_tasks": [
            {
                "id": t["id"],
                "title": t["title"],
                "consecutive_failures": t["consecutive_failures"],
                "error": (t.get("last_failure_error") or "")[:200],
            }
            for t in failed
        ],
        "assignee_completions_7d": dict(assignee_completions),
    }

    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
