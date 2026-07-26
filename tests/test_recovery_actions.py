#!/usr/bin/env python3
"""Comprehensive tests for BrandOS recovery actions, notifications, and execution.

Tests cover:
- Action executor (restart, rework, merge, escalate, promote)
- Idempotency guards (no duplicate actions across runs)
- Rework cycle limits (max 2 cycles before escalation)
- Continuation task creation (preserves worktree context)
- Notification formatting (escalation, daily digest)
- End-to-end recovery plan execution
- Restart idempotency and state transitions

Run: python -m unittest tests.test_recovery_actions -v
"""

import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

# Ensure scripts/ is importable
_root = Path(__file__).resolve().parent.parent
_scripts = _root / "scripts"
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))

from recovery_actions import (
    ActionOutcome,
    ActionResult,
    MAX_REWORK_CYCLES,
    STALE_ARCHIVE_SECONDS,
    execute_plan,
    _create_continuation_task,
    _handle_restart,
    _handle_stalled,
    _handle_escalate_rework,
    _handle_promote_stranded,
    _handle_circular,
    _merge_ready_action,
    _route_rework,
    _unblock_dependency,
    _update_task_status,
)
from recovery_classify import TaskState, classify_task
from recovery_supervisor import build_recovery_plan
from recovery_notify import (
    _format_escalation_message,
    _format_daily_digest,
    notify_escalation,
    notify_daily_digest,
)


def make_temp_kanban_db(tasks: list, links: list = None) -> str:
    """Create a temporary SQLite DB mimicking the kanban schema."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            title TEXT,
            body TEXT,
            assignee TEXT,
            status TEXT,
            priority INTEGER DEFAULT 0,
            created_by TEXT,
            created_at INTEGER,
            started_at INTEGER,
            completed_at INTEGER,
            workspace_kind TEXT,
            workspace_path TEXT,
            branch_name TEXT,
            project_id TEXT,
            claim_lock TEXT,
            claim_expires INTEGER,
            tenant TEXT,
            result TEXT,
            idempotency_key TEXT,
            consecutive_failures INTEGER DEFAULT 0,
            worker_pid INTEGER,
            last_failure_error TEXT,
            max_runtime_seconds INTEGER,
            last_heartbeat_at INTEGER,
            current_run_id INTEGER,
            workflow_template_id TEXT,
            current_step_key TEXT,
            skills TEXT,
            model_override TEXT,
            max_retries INTEGER,
            goal_mode INTEGER,
            goal_max_turns INTEGER,
            session_id TEXT,
            block_kind TEXT,
            block_recurrences INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS task_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id TEXT,
            child_id TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS task_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT,
            outcome TEXT,
            started_at INTEGER,
            finished_at INTEGER,
            created_at INTEGER
        )
    """)

    for t in tasks:
        conn.execute(
            """INSERT OR REPLACE INTO tasks
               (id, title, status, assignee, started_at, last_heartbeat_at,
                max_runtime_seconds, block_kind, block_recurrences,
                created_at, completed_at, priority, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                t.get("id", ""),
                t.get("title", ""),
                t.get("status", ""),
                t.get("assignee", ""),
                t.get("started_at"),
                t.get("heartbeat_at") or t.get("last_heartbeat_at"),
                t.get("max_runtime_seconds"),
                t.get("block_kind"),
                t.get("block_recurrences", 0),
                t.get("created_at", int(time.time())),
                t.get("completed_at"),
                t.get("priority", 0),
                t.get("created_by", "test"),
            ),
        )

    if links:
        for parent_id, child_id in links:
            conn.execute(
                "INSERT INTO task_links (parent_id, child_id) VALUES (?, ?)",
                (parent_id, child_id),
            )

    conn.commit()
    conn.close()
    return db_path


class TestUpdateTaskStatus(unittest.TestCase):
    """Tests for _update_task_status helper."""

    def setUp(self):
        self._temp_files = []

    def tearDown(self):
        for f in self._temp_files:
            if os.path.exists(f):
                os.unlink(f)

    def _make_db(self, tasks, links=None):
        db = make_temp_kanban_db(tasks, links)
        self._temp_files.append(db)
        return db

    def test_update_status_only(self):
        """Updating status changes it in DB."""
        db = self._make_db([{"id": "1", "status": "todo"}])
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        _update_task_status(conn, "1", "ready")
        row = conn.execute("SELECT status FROM tasks WHERE id = '1'").fetchone()
        self.assertEqual(row["status"], "ready")
        conn.close()

    def test_update_with_block_kind(self):
        """Updating with block_kind sets both fields."""
        db = self._make_db([{"id": "1", "status": "running"}])
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        _update_task_status(conn, "1", "blocked", block_kind="timed-out")
        row = conn.execute("SELECT status, block_kind FROM tasks WHERE id = '1'").fetchone()
        self.assertEqual(row["status"], "blocked")
        self.assertEqual(row["block_kind"], "timed-out")
        conn.close()

    def test_update_with_recurrences(self):
        """Updating with block_recurrences increments the counter."""
        db = self._make_db([{"id": "1", "status": "blocked", "block_recurrences": 1}])
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        _update_task_status(conn, "1", "blocked", block_kind="rework-needed",
                           block_recurrences=2)
        row = conn.execute(
            "SELECT block_recurrences FROM tasks WHERE id = '1'"
        ).fetchone()
        self.assertEqual(row["block_recurrences"], 2)
        conn.close()


class TestContinuationCreation(unittest.TestCase):
    """Tests for continuation task creation from timed-out tasks."""

    def setUp(self):
        self._temp_files = []

    def tearDown(self):
        for f in self._temp_files:
            if os.path.exists(f):
                os.unlink(f)

    def _make_db(self, tasks, links=None):
        db = make_temp_kanban_db(tasks, links)
        self._temp_files.append(db)
        return db

    def test_creates_continuation(self):
        """Timed-out task gets a continuation with correct structure."""
        db = self._make_db([{
            "id": "t_orig",
            "title": "BOS-42: Build the feature",
            "status": "running",
            "assignee": "brandosbackend",
            "started_at": 1000,
            "max_runtime_seconds": 3600,
        }])
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        task = dict(conn.execute("SELECT * FROM tasks WHERE id = 't_orig'").fetchone())

        cont_id = _create_continuation_task(conn, task, "Resume work")
        self.assertEqual(cont_id, "t_orig_continue")

        # Verify continuation exists
        cont = conn.execute(
            "SELECT * FROM tasks WHERE id = 't_orig_continue'"
        ).fetchone()
        self.assertIsNotNone(cont)
        cont = dict(cont)
        self.assertEqual(cont["status"], "ready")
        self.assertEqual(cont["assignee"], "brandosbackend")
        self.assertIn("BOS-42", cont["title"])

        # Verify original is blocked as timed-out
        orig = dict(conn.execute(
            "SELECT * FROM tasks WHERE id = 't_orig'"
        ).fetchone())
        self.assertEqual(orig["status"], "blocked")
        self.assertEqual(orig["block_kind"], "timed-out")

        # Verify dependency link
        links = conn.execute(
            "SELECT * FROM task_links WHERE parent_id = 't_orig'"
        ).fetchall()
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0][2], "t_orig_continue")
        conn.close()

    def test_idempotent_continuation(self):
        """Creating continuation twice returns same ID without duplicate."""
        db = self._make_db([{"id": "t_orig", "title": "Task", "status": "running"}])
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        task = dict(conn.execute("SELECT * FROM tasks WHERE id = 't_orig'").fetchone())

        id1 = _create_continuation_task(conn, task, "Work 1")
        id2 = _create_continuation_task(conn, task, "Work 2")
        self.assertEqual(id1, id2)

        # Only one continuation task should exist
        conts = conn.execute(
            "SELECT * FROM tasks WHERE id LIKE 't_orig_continue%'"
        ).fetchall()
        self.assertEqual(len(conts), 1)
        conn.close()

    def test_jira_key_preserved_in_title(self):
        """Jira key from original title is preserved in continuation."""
        db = self._make_db([{
            "id": "t_abc",
            "title": "bos-99: Some task title",
            "status": "running",
        }])
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        task = dict(conn.execute("SELECT * FROM tasks WHERE id = 't_abc'").fetchone())

        cont_id = _create_continuation_task(conn, task, "Remaining work")
        cont = dict(conn.execute(
            "SELECT title FROM tasks WHERE id = ?", (cont_id,)
        ).fetchone())
        self.assertIn("BOS-99", cont["title"])
        conn.close()


class TestRestartHandling(unittest.TestCase):
    """Tests for the restart action handler."""

    def setUp(self):
        self._temp_files = []

    def tearDown(self):
        for f in self._temp_files:
            if os.path.exists(f):
                os.unlink(f)

    def _make_db(self, tasks, links=None):
        db = make_temp_kanban_db(tasks, links)
        self._temp_files.append(db)
        return db

    def test_restart_creates_continuation(self):
        """Timed-out task gets continuation on restart."""
        db = self._make_db([{
            "id": "t1",
            "title": "BOS-10: Build API",
            "status": "running",
            "assignee": "brandosbackend",
            "started_at": 1000,
            "max_runtime_seconds": 3600,
        }])
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        task_map = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM tasks").fetchall()}

        result = _handle_restart(conn, "t1", task_map, dry_run=False)
        self.assertEqual(result.outcome, ActionOutcome.EXECUTED)
        self.assertIn("t1_continue", result.details)
        conn.close()

    def test_restart_already_timed_out(self):
        """Already timed-out task is skipped."""
        db = self._make_db([{
            "id": "t1",
            "status": "blocked",
            "block_kind": "timed-out",
        }])
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        task_map = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM tasks").fetchall()}

        result = _handle_restart(conn, "t1", task_map, dry_run=False)
        self.assertEqual(result.outcome, ActionOutcome.SKIPPED_IDEMPOTENT)
        conn.close()

    def test_restart_dry_run(self):
        """Dry run doesn't create continuation."""
        db = self._make_db([{
            "id": "t1",
            "status": "running",
            "started_at": 1000,
            "max_runtime_seconds": 3600,
        }])
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        task_map = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM tasks").fetchall()}

        result = _handle_restart(conn, "t1", task_map, dry_run=True)
        self.assertEqual(result.outcome, ActionOutcome.SKIPPED_IDEMPOTENT)

        # No continuation should exist
        cont = conn.execute("SELECT * FROM tasks WHERE id LIKE 't1_continue%'").fetchone()
        self.assertIsNone(cont)
        conn.close()

    def test_restart_no_task_id(self):
        """Missing task_id returns failure."""
        db = self._make_db([])
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        result = _handle_restart(conn, None, {}, dry_run=False)
        self.assertEqual(result.outcome, ActionOutcome.FAILED)
        conn.close()

    def test_restart_task_not_found(self):
        """Nonexistent task returns failure."""
        db = self._make_db([])
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        result = _handle_restart(conn, "nonexistent", {}, dry_run=False)
        self.assertEqual(result.outcome, ActionOutcome.FAILED)
        conn.close()


class TestStalledHandling(unittest.TestCase):
    """Tests for stalled task handler."""

    def setUp(self):
        self._temp_files = []

    def tearDown(self):
        for f in self._temp_files:
            if os.path.exists(f):
                os.unlink(f)

    def _make_db(self, tasks):
        db = make_temp_kanban_db(tasks)
        self._temp_files.append(db)
        return db

    def test_stalled_short_duration(self):
        """Recently stalled task is monitored, not escalated."""
        now = int(time.time())
        db = self._make_db([{
            "id": "t1",
            "status": "running",
            "started_at": now - 3600,  # 1 hour ago
        }])
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        task_map = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM tasks").fetchall()}

        result = _handle_stalled(conn, "t1", task_map, dry_run=False)
        self.assertEqual(result.outcome, ActionOutcome.SKIPPED_IDEMPOTENT)
        self.assertIn("monitoring", result.details)
        conn.close()

    def test_stalled_long_duration_escalates(self):
        """Task stalled for >7 days gets escalated."""
        now = int(time.time())
        db = self._make_db([{
            "id": "t1",
            "status": "running",
            "started_at": now - (8 * 24 * 3600),  # 8 days ago
        }])
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        task_map = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM tasks").fetchall()}

        result = _handle_stalled(conn, "t1", task_map, dry_run=False)
        self.assertEqual(result.outcome, ActionOutcome.ESCALATED)
        self.assertIn("human check", result.details)
        conn.close()

    def test_stalled_no_task_id(self):
        """Missing task_id returns failure."""
        db = self._make_db([])
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        result = _handle_stalled(conn, None, {}, dry_run=False)
        self.assertEqual(result.outcome, ActionOutcome.FAILED)
        conn.close()


class TestReworkEscalation(unittest.TestCase):
    """Tests for rework routing and escalation limits."""

    def setUp(self):
        self._temp_files = []

    def tearDown(self):
        for f in self._temp_files:
            if os.path.exists(f):
                os.unlink(f)

    def _make_db(self, tasks):
        db = make_temp_kanban_db(tasks)
        self._temp_files.append(db)
        return db

    def test_rework_first_cycle(self):
        """First rework cycle routes to rework."""
        db = self._make_db([{
            "id": "t1",
            "status": "blocked",
            "block_kind": "review-required",
            "block_recurrences": 0,
        }])
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        task = dict(conn.execute("SELECT * FROM tasks WHERE id = 't1'").fetchone())

        result = _route_rework(conn, "t1", task)
        self.assertEqual(result.outcome, ActionOutcome.EXECUTED)
        self.assertEqual(result.metadata["recurrences"], 1)

        # Verify DB state
        updated = dict(conn.execute(
            "SELECT block_kind, block_recurrences FROM tasks WHERE id = 't1'"
        ).fetchone())
        self.assertEqual(updated["block_kind"], "rework-needed")
        self.assertEqual(updated["block_recurrences"], 1)
        conn.close()

    def test_rework_second_cycle(self):
        """Second rework cycle still routes to rework."""
        db = self._make_db([{
            "id": "t1",
            "status": "blocked",
            "block_kind": "rework-needed",
            "block_recurrences": 1,
        }])
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        task = dict(conn.execute("SELECT * FROM tasks WHERE id = 't1'").fetchone())

        result = _route_rework(conn, "t1", task)
        self.assertEqual(result.outcome, ActionOutcome.EXECUTED)
        self.assertEqual(result.metadata["recurrences"], 2)
        conn.close()

    def test_rework_exceeds_limit_escalates(self):
        """Third rework attempt escalates to human."""
        db = self._make_db([{
            "id": "t1",
            "status": "blocked",
            "block_kind": "rework-needed",
            "block_recurrences": MAX_REWORK_CYCLES,
        }])
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        task = dict(conn.execute("SELECT * FROM tasks WHERE id = 't1'").fetchone())

        result = _route_rework(conn, "t1", task)
        self.assertEqual(result.outcome, ActionOutcome.ESCALATED)
        self.assertIn("exceeded", result.details)

        # Verify escalated state
        updated = dict(conn.execute(
            "SELECT block_kind FROM tasks WHERE id = 't1'"
        ).fetchone())
        self.assertEqual(updated["block_kind"], "escalated-rework")
        conn.close()


class TestEscalateReworkHandler(unittest.TestCase):
    """Tests for the escalate rework action handler."""

    def setUp(self):
        self._temp_files = []

    def tearDown(self):
        for f in self._temp_files:
            if os.path.exists(f):
                os.unlink(f)

    def _make_db(self, tasks):
        db = make_temp_kanban_db(tasks)
        self._temp_files.append(db)
        return db

    def test_escalate_marks_blocked(self):
        """Escalation marks task as blocked with escalated-rework kind."""
        db = self._make_db([{
            "id": "t1",
            "status": "blocked",
            "block_kind": "rework-needed",
            "block_recurrences": 3,
        }])
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        task_map = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM tasks").fetchall()}

        result = _handle_escalate_rework(conn, "t1", task_map, dry_run=False)
        self.assertEqual(result.outcome, ActionOutcome.ESCALATED)
        self.assertEqual(result.metadata["recurrences"], 4)
        conn.close()

    def test_escalate_dry_run(self):
        """Dry run doesn't modify the task."""
        db = self._make_db([{
            "id": "t1",
            "status": "blocked",
            "block_kind": "rework-needed",
            "block_recurrences": 3,
        }])
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        task_map = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM tasks").fetchall()}

        result = _handle_escalate_rework(conn, "t1", task_map, dry_run=True)
        self.assertEqual(result.outcome, ActionOutcome.SKIPPED_IDEMPOTENT)
        conn.close()


class TestStrandedPromotion(unittest.TestCase):
    """Tests for stranded task promotion handler."""

    def setUp(self):
        self._temp_files = []

    def tearDown(self):
        for f in self._temp_files:
            if os.path.exists(f):
                os.unlink(f)

    def _make_db(self, tasks, links=None):
        db = make_temp_kanban_db(tasks, links)
        self._temp_files.append(db)
        return db

    def test_promote_stranded(self):
        """Stranded todo task is promoted to ready."""
        db = self._make_db([{"id": "t1", "status": "todo"}])
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row

        result = _handle_promote_stranded(conn, "t1", dry_run=False)
        self.assertEqual(result.outcome, ActionOutcome.EXECUTED)

        updated = dict(conn.execute(
            "SELECT status FROM tasks WHERE id = 't1'"
        ).fetchone())
        self.assertEqual(updated["status"], "ready")
        conn.close()

    def test_promote_already_ready(self):
        """Already-ready task is skipped."""
        db = self._make_db([{"id": "t1", "status": "ready"}])
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row

        result = _handle_promote_stranded(conn, "t1", dry_run=False)
        self.assertEqual(result.outcome, ActionOutcome.SKIPPED_IDEMPOTENT)
        conn.close()

    def test_promote_dry_run(self):
        """Dry run doesn't modify the task."""
        db = self._make_db([{"id": "t1", "status": "todo"}])
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row

        result = _handle_promote_stranded(conn, "t1", dry_run=True)
        self.assertEqual(result.outcome, ActionOutcome.SKIPPED_IDEMPOTENT)

        updated = dict(conn.execute(
            "SELECT status FROM tasks WHERE id = 't1'"
        ).fetchone())
        self.assertEqual(updated["status"], "todo")
        conn.close()

    def test_promote_no_task_id(self):
        """Missing task_id returns failure."""
        db = self._make_db([])
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        result = _handle_promote_stranded(conn, None, dry_run=False)
        self.assertEqual(result.outcome, ActionOutcome.FAILED)
        conn.close()


class TestMergeReadyAction(unittest.TestCase):
    """Tests for merge-ready action."""

    def setUp(self):
        self._temp_files = []

    def tearDown(self):
        for f in self._temp_files:
            if os.path.exists(f):
                os.unlink(f)

    def _make_db(self, tasks):
        db = make_temp_kanban_db(tasks)
        self._temp_files.append(db)
        return db

    def test_merge_marks_done(self):
        """Merge-ready task is marked done."""
        db = self._make_db([{"id": "t1", "status": "blocked", "block_kind": "merge-ready"}])
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row

        result = _merge_ready_action(conn, "t1", dry_run=False)
        self.assertEqual(result.outcome, ActionOutcome.EXECUTED)

        updated = dict(conn.execute(
            "SELECT status FROM tasks WHERE id = 't1'"
        ).fetchone())
        self.assertEqual(updated["status"], "done")
        conn.close()

    def test_merge_dry_run(self):
        """Dry run doesn't merge."""
        db = self._make_db([{"id": "t1", "status": "blocked", "block_kind": "merge-ready"}])
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row

        result = _merge_ready_action(conn, "t1", dry_run=True)
        self.assertEqual(result.outcome, ActionOutcome.SKIPPED_IDEMPOTENT)
        conn.close()


class TestCircularHandling(unittest.TestCase):
    """Tests for circular dependency handling."""

    def test_circular_always_escalates(self):
        """Circular deps always escalate to human."""
        action = {"action": "resolve_circular_deps", "reason": "Found 2 cycles"}
        result = _handle_circular(action, dry_run=False)
        self.assertEqual(result.outcome, ActionOutcome.ESCALATED)
        self.assertIn("human intervention", result.details)

    def test_circular_dry_run(self):
        """Dry run still escalates (circular deps always need human)."""
        action = {"action": "resolve_circular_deps", "reason": "Cycle detected"}
        result = _handle_circular(action, dry_run=True)
        self.assertEqual(result.outcome, ActionOutcome.ESCALATED)


class TestUnblockDependency(unittest.TestCase):
    """Tests for dependency unblocking."""

    def setUp(self):
        self._temp_files = []

    def tearDown(self):
        for f in self._temp_files:
            if os.path.exists(f):
                os.unlink(f)

    def _make_db(self, tasks, links=None):
        db = make_temp_kanban_db(tasks, links)
        self._temp_files.append(db)
        return db

    def test_unblock_when_parent_done(self):
        """Dependency-blocked task is unblocked when parent is done."""
        db = self._make_db(
            [
                {"id": "P", "status": "done"},
                {"id": "C", "status": "blocked", "block_kind": "dependency"},
            ],
            links=[("P", "C")],
        )
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        _unblock_dependency(conn, "C")
        conn.commit()
        conn.close()

        # Read with a fresh connection to avoid Windows lock issues
        conn2 = sqlite3.connect(db)
        conn2.row_factory = sqlite3.Row
        updated = dict(conn2.execute(
            "SELECT status, block_kind FROM tasks WHERE id = 'C'"
        ).fetchone())
        self.assertEqual(updated["status"], "ready")
        self.assertIsNone(updated["block_kind"])
        conn2.close()

    def test_no_unblock_when_parent_running(self):
        """Task stays blocked if parent is still running."""
        db = self._make_db(
            [
                {"id": "P", "status": "running"},
                {"id": "C", "status": "blocked", "block_kind": "dependency"},
            ],
            links=[("P", "C")],
        )
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        _unblock_dependency(conn, "C")

        updated = dict(conn.execute(
            "SELECT status FROM tasks WHERE id = 'C'"
        ).fetchone())
        self.assertEqual(updated["status"], "blocked")
        conn.close()


class TestExecutePlan(unittest.TestCase):
    """Tests for execute_plan (full plan execution)."""

    def setUp(self):
        self._temp_files = []

    def tearDown(self):
        for f in self._temp_files:
            if os.path.exists(f):
                os.unlink(f)

    def _make_db(self, tasks, links=None):
        db = make_temp_kanban_db(tasks, links)
        self._temp_files.append(db)
        return db

    def test_empty_plan(self):
        """Empty plan produces no results."""
        db = self._make_db([])
        plan = build_recovery_plan(db, now=10000)
        results = execute_plan(db, plan)
        self.assertEqual(results, [])

    def test_execute_stranded_promotion(self):
        """Stranded tasks are promoted to ready."""
        tasks = [
            {"id": "P1", "status": "done"},
            {"id": "C1", "status": "todo"},
        ]
        links = [("P1", "C1")]
        db = self._make_db(tasks, links)
        plan = build_recovery_plan(db, now=10000)

        # Verify stranded is detected
        self.assertEqual(len(plan["stranded"]), 1)

        results = execute_plan(db, plan)
        promote_results = [r for r in results if r.action == "promote_stranded"]
        self.assertEqual(len(promote_results), 1)
        self.assertEqual(promote_results[0].outcome, ActionOutcome.EXECUTED)

        # Verify task is now ready
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT status FROM tasks WHERE id = 'C1'").fetchone()
        self.assertEqual(row["status"], "ready")
        conn.close()

    def test_execute_timed_out_restart(self):
        """Timed-out task gets continuation."""
        tasks = [{
            "id": "t1",
            "title": "BOS-50: Build feature",
            "status": "running",
            "assignee": "brandosbackend",
            "started_at": 1000,
            "max_runtime_seconds": 3600,
            "heartbeat_at": None,
        }]
        db = self._make_db(tasks)
        plan = build_recovery_plan(db, now=5000)

        self.assertEqual(len(plan["timed_out_tasks"]), 1)

        results = execute_plan(db, plan)
        restart_results = [r for r in results if r.action == "restart_task"]
        self.assertEqual(len(restart_results), 1)
        self.assertEqual(restart_results[0].outcome, ActionOutcome.EXECUTED)
        self.assertIn("continuation_id", restart_results[0].metadata)

    def test_execute_wip_limit_suppresses(self):
        """WIP limit action produces skip result."""
        tasks = [
            {"id": "1", "status": "running", "assignee": "brandosbackend"},
            {"id": "2", "status": "running", "assignee": "brandosfrontend"},
        ]
        db = self._make_db(tasks)
        plan = build_recovery_plan(db, now=10000)

        self.assertTrue(plan["wip"]["at_limit"])

        results = execute_plan(db, plan)
        wip_results = [r for r in results if r.action == "wip_limit_reached"]
        self.assertEqual(len(wip_results), 1)
        self.assertEqual(wip_results[0].outcome, ActionOutcome.SKIPPED_WIP)

    def test_execute_circular_escalates(self):
        """Circular dependency action escalates to human."""
        tasks = [
            {"id": "A", "status": "blocked", "block_kind": "dependency"},
            {"id": "B", "status": "blocked", "block_kind": "dependency"},
        ]
        links = [("A", "B"), ("B", "A")]
        db = self._make_db(tasks, links)
        plan = build_recovery_plan(db, now=10000)

        self.assertGreater(len(plan["circular_links"]), 0)

        results = execute_plan(db, plan)
        circular_results = [r for r in results if r.action == "resolve_circular_deps"]
        self.assertEqual(len(circular_results), 1)
        self.assertEqual(circular_results[0].outcome, ActionOutcome.ESCALATED)

    def test_execute_dry_run_no_mutation(self):
        """Dry run doesn't modify the database."""
        tasks = [
            {"id": "P1", "status": "done"},
            {"id": "C1", "status": "todo"},
        ]
        links = [("P1", "C1")]
        db = self._make_db(tasks, links)
        plan = build_recovery_plan(db, now=10000)

        results = execute_plan(db, plan, dry_run=True)
        promote_results = [r for r in results if r.action == "promote_stranded"]
        self.assertEqual(len(promote_results), 1)
        self.assertEqual(promote_results[0].outcome, ActionOutcome.SKIPPED_IDEMPOTENT)

        # Task should still be todo
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT status FROM tasks WHERE id = 'C1'").fetchone()
        self.assertEqual(row["status"], "todo")
        conn.close()


class TestRestartIdempotency(unittest.TestCase):
    """Tests that restart actions are idempotent across multiple runs."""

    def setUp(self):
        self._temp_files = []

    def tearDown(self):
        for f in self._temp_files:
            if os.path.exists(f):
                os.unlink(f)

    def _make_db(self, tasks, links=None):
        db = make_temp_kanban_db(tasks, links)
        self._temp_files.append(db)
        return db

    def test_restart_idempotent_across_runs(self):
        """Running execute_plan twice produces no duplicate continuations."""
        tasks = [{
            "id": "t1",
            "title": "BOS-50: Build feature",
            "status": "running",
            "assignee": "brandosbackend",
            "started_at": 1000,
            "max_runtime_seconds": 3600,
            "heartbeat_at": None,
        }]
        db = self._make_db(tasks)

        # First execution
        plan1 = build_recovery_plan(db, now=5000)
        results1 = execute_plan(db, plan1)
        restart1 = [r for r in results1 if r.action == "restart_task"]
        self.assertEqual(len(restart1), 1)
        self.assertEqual(restart1[0].outcome, ActionOutcome.EXECUTED)

        # Second execution with same plan context
        plan2 = build_recovery_plan(db, now=5000)
        results2 = execute_plan(db, plan2)
        restart2 = [r for r in results2 if r.action == "restart_task"]
        # Should be skipped (already timed-out) or no action recommended
        if restart2:
            self.assertEqual(restart2[0].outcome, ActionOutcome.SKIPPED_IDEMPOTENT)

        # Only one continuation task should exist
        conn = sqlite3.connect(db)
        conts = conn.execute(
            "SELECT * FROM tasks WHERE id LIKE 't1_continue%'"
        ).fetchall()
        self.assertEqual(len(conts), 1)
        conn.close()

    def test_stranded_promotion_idempotent(self):
        """Promoting a stranded task twice skips the second time."""
        tasks = [
            {"id": "P1", "status": "done"},
            {"id": "C1", "status": "todo"},
        ]
        links = [("P1", "C1")]
        db = self._make_db(tasks, links)

        # First execution
        plan1 = build_recovery_plan(db, now=10000)
        results1 = execute_plan(db, plan1)
        promote1 = [r for r in results1 if r.action == "promote_stranded"]
        self.assertEqual(len(promote1), 1)
        self.assertEqual(promote1[0].outcome, ActionOutcome.EXECUTED)

        # Second execution — task is now ready, should not be in plan
        plan2 = build_recovery_plan(db, now=10000)
        self.assertEqual(len(plan2["stranded"]), 0)  # No longer stranded

    def test_full_lifecycle_timed_out_to_done(self):
        """Full lifecycle: timed-out → continuation → ready → done."""
        tasks = [{
            "id": "t1",
            "title": "BOS-50: Build API",
            "status": "running",
            "assignee": "brandosbackend",
            "started_at": 1000,
            "max_runtime_seconds": 3600,
            "heartbeat_at": None,
        }]
        db = self._make_db(tasks)

        # Step 1: Detect and restart
        plan = build_recovery_plan(db, now=5000)
        results = execute_plan(db, plan)
        restart = [r for r in results if r.action == "restart_task"][0]
        self.assertEqual(restart.outcome, ActionOutcome.EXECUTED)
        cont_id = restart.metadata["continuation_id"]

        # Step 2: Verify continuation is ready
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        cont = dict(conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (cont_id,)
        ).fetchone())
        self.assertEqual(cont["status"], "ready")
        self.assertEqual(cont["assignee"], "brandosbackend")

        # Step 3: Original is blocked
        orig = dict(conn.execute(
            "SELECT * FROM tasks WHERE id = 't1'"
        ).fetchone())
        self.assertEqual(orig["status"], "blocked")
        self.assertEqual(orig["block_kind"], "timed-out")

        # Step 4: Simulate continuation completing → done
        _update_task_status(conn, cont_id, "done")
        final = dict(conn.execute(
            "SELECT status FROM tasks WHERE id = ?", (cont_id,)
        ).fetchone())
        self.assertEqual(final["status"], "done")
        conn.close()


class TestNotificationFormatting(unittest.TestCase):
    """Tests for Telegram notification formatting."""

    def test_escalation_message_basic(self):
        """Basic escalation message includes key info."""
        results = [
            {"action": "escalate_rework", "task_id": "t1",
             "outcome": "escalated", "details": "Rework limit exceeded"},
            {"action": "restart_task", "task_id": "t2",
             "outcome": "failed", "details": "Task not found"},
        ]
        msg = _format_escalation_message(results)
        self.assertIn("Escalation Alert", msg)
        self.assertIn("t1", msg)
        self.assertIn("Rework limit exceeded", msg)
        self.assertIn("Escalated: 1", msg)
        self.assertIn("Failed: 1", msg)

    def test_escalation_message_with_summary(self):
        """Escalation message includes board summary."""
        results = [
            {"action": "escalate_rework", "task_id": "t1",
             "outcome": "escalated", "details": "Too many reworks"},
        ]
        summary = {"wip": {"current": 2, "limit": 2}, "timed_out": ["a"], "stalled": []}
        msg = _format_escalation_message(results, board_summary=summary)
        self.assertIn("WIP", msg)
        self.assertIn("Timed out: 1", msg)

    def test_daily_digest_all_clear(self):
        """Daily digest shows all-clear when no issues."""
        plan = {
            "wip": {"current": 0, "limit": 2, "at_limit": False},
            "healthy_running": [],
            "ready_for_dispatch": ["a"],
            "needs_review": [],
            "needs_rework": [],
            "needs_rework_escalate": [],
            "timed_out_tasks": [],
            "stalled_tasks": [],
            "blocked_human": [],
            "blocked_dependency": [],
            "stranded": [],
            "circular_links": [],
            "actions_recommended": [],
        }
        msg = _format_daily_digest(plan)
        self.assertIn("Daily Recovery Digest", msg)
        self.assertIn("all clear", msg)

    def test_daily_digest_with_issues(self):
        """Daily digest shows counts when there are issues."""
        plan = {
            "wip": {"current": 2, "limit": 2, "at_limit": True},
            "healthy_running": ["a", "b"],
            "ready_for_dispatch": [],
            "needs_review": ["c"],
            "needs_rework": ["d"],
            "needs_rework_escalate": [],
            "timed_out_tasks": ["e"],
            "stalled_tasks": [],
            "blocked_human": [],
            "blocked_dependency": [],
            "stranded": ["f"],
            "circular_links": [["A", "B", "A"]],
            "actions_recommended": [
                {"action": "restart_task", "priority": "high", "reason": "Timed out"},
            ],
        }
        msg = _format_daily_digest(plan)
        self.assertIn("AT LIMIT", msg)
        self.assertIn("Timed out: 1", msg)
        self.assertIn("Stranded: 1", msg)
        self.assertIn("Circular deps: 1", msg)

    def test_escalation_caps_at_5(self):
        """Escalation message caps at 5 items to avoid overflow."""
        results = [
            {"action": "escalate_rework", "task_id": f"t{i}",
             "outcome": "escalated", "details": f"Escalated {i}"}
            for i in range(10)
        ]
        msg = _format_escalation_message(results)
        self.assertIn("and 5 more", msg)


class TestEndToEndRecovery(unittest.TestCase):
    """End-to-end tests for full recovery plan execution."""

    def setUp(self):
        self._temp_files = []

    def tearDown(self):
        for f in self._temp_files:
            if os.path.exists(f):
                os.unlink(f)

    def _make_db(self, tasks, links=None):
        db = make_temp_kanban_db(tasks, links)
        self._temp_files.append(db)
        return db

    def test_mixed_scenario(self):
        """Multiple task states handled in single execution."""
        now = 10000
        tasks = [
            # Timed out
            {"id": "t1", "title": "BOS-1: API", "status": "running",
             "assignee": "brandosbackend", "started_at": 1000,
             "max_runtime_seconds": 3600, "heartbeat_at": None},
            # Healthy
            {"id": "t2", "status": "running", "assignee": "brandosfrontend",
             "started_at": 9000, "heartbeat_at": 9950, "max_runtime_seconds": 36000},
            # Stranded
            {"id": "P1", "status": "done"},
            {"id": "C1", "status": "todo"},
        ]
        links = [("P1", "C1")]
        db = self._make_db(tasks, links)

        plan = build_recovery_plan(db, now=now)
        results = execute_plan(db, plan)

        # Should have restart + promote actions
        actions = {r.action: r for r in results}
        self.assertIn("restart_task", actions)
        self.assertIn("promote_stranded", actions)
        self.assertEqual(actions["restart_task"].outcome, ActionOutcome.EXECUTED)
        self.assertEqual(actions["promote_stranded"].outcome, ActionOutcome.EXECUTED)

    def test_no_actions_on_healthy_board(self):
        """Healthy board with no issues produces no actions."""
        now = 10000
        tasks = [
            {"id": "1", "status": "done"},
            {"id": "2", "status": "running", "assignee": "brandosbackend",
             "started_at": 9000, "heartbeat_at": 9950, "max_runtime_seconds": 36000},
        ]
        db = self._make_db(tasks)

        plan = build_recovery_plan(db, now=now)
        results = execute_plan(db, plan)
        self.assertEqual(len(results), 0)


if __name__ == "__main__":
    unittest.main()
