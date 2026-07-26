#!/usr/bin/env python3
"""Comprehensive test suite for BrandOS autonomous recovery supervisor.

Tests cover task classification, circular dependency detection, stranded task
detection, WIP counting, recovery plan building, audit logging, and restart
idempotency.

Run: python -m unittest tests.test_recovery -v
"""

import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from io import StringIO
from pathlib import Path

# Ensure scripts/ is importable
_root = Path(__file__).resolve().parent.parent
_scripts = _root / "scripts"
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))

from recovery_classify import (
    IMPLEM_PROFILES,
    NON_WIP_PROFILES,
    TaskState,
    classify_all,
    classify_task,
    count_implementation_wip,
    detect_circular_links,
    detect_stranded_tasks,
)
from recovery_audit import AuditLogger, RedactingFilter, redact_dict
from recovery_supervisor import (
    build_recovery_plan,
    extract_jira_key,
    get_task_links,
    get_task_runs,
    get_tasks,
)


def make_temp_kanban_db(tasks: list, links: list = None) -> str:
    """Create a temporary SQLite DB mimicking the kanban schema.

    Args:
        tasks: List of task dicts to insert.
        links: Optional list of (parent_id, child_id) tuples.

    Returns:
        Path to the temporary SQLite database file.
    """
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


class TestClassifyTask(unittest.TestCase):
    """Tests for the classify_task function."""

    def test_done_task(self):
        """A task with status 'done' should classify as DONE."""
        task = {"id": "1", "status": "done"}
        self.assertEqual(classify_task(task, 1000), TaskState.DONE)

    def test_timed_out_no_heartbeat(self):
        """Running task past max_runtime with no heartbeat → TIMED_OUT."""
        task = {
            "id": "1",
            "status": "running",
            "started_at": 1000,
            "max_runtime_seconds": 3600,
            "heartbeat_at": None,
        }
        self.assertEqual(classify_task(task, 5000), TaskState.TIMED_OUT)

    def test_timed_out_stale_heartbeat(self):
        """Running task past max_runtime with old heartbeat (>30min) → TIMED_OUT."""
        task = {
            "id": "1",
            "status": "running",
            "started_at": 1000,
            "max_runtime_seconds": 3600,
            "heartbeat_at": 3200,  # 1800s old at now=5000
        }
        self.assertEqual(classify_task(task, 5000), TaskState.TIMED_OUT)

    def test_stalled_no_heartbeat(self):
        """Running task with no heartbeat and NOT timed out → STALLED."""
        task = {
            "id": "1",
            "status": "running",
            "started_at": 9000,
            "max_runtime_seconds": 36000,
            "heartbeat_at": None,
        }
        self.assertEqual(classify_task(task, 9100), TaskState.STALLED)

    def test_stalled_old_heartbeat(self):
        """Running task with heartbeat >60min old → STALLED."""
        old_heartbeat = 9100 - 3700  # 3700s ago = ~62min
        task = {
            "id": "1",
            "status": "running",
            "started_at": 5000,
            "max_runtime_seconds": 36000,
            "heartbeat_at": old_heartbeat,
        }
        self.assertEqual(classify_task(task, 9100), TaskState.STALLED)

    def test_running_healthy(self):
        """Running task with recent heartbeat → RUNNING_HEALTHY."""
        task = {
            "id": "1",
            "status": "running",
            "started_at": 9000,
            "heartbeat_at": 9050,
            "max_runtime_seconds": 36000,
        }
        self.assertEqual(classify_task(task, 9100), TaskState.RUNNING_HEALTHY)

    def test_needs_review(self):
        """Blocked with 'review-required' → NEEDS_REVIEW."""
        task = {"id": "1", "status": "blocked", "block_kind": "review-required"}
        self.assertEqual(classify_task(task, 1000), TaskState.NEEDS_REVIEW)

    def test_needs_rework_first(self):
        """Blocked with 'rework-needed' and recurrences < 2 → NEEDS_REWORK."""
        task = {
            "id": "1",
            "status": "blocked",
            "block_kind": "rework-needed",
            "block_recurrences": 1,
        }
        self.assertEqual(classify_task(task, 1000), TaskState.NEEDS_REWORK)

    def test_needs_rework_escalate(self):
        """Blocked with 'rework-needed' and recurrences >= 2 → NEEDS_REWORK_ESCALATE."""
        task = {
            "id": "1",
            "status": "blocked",
            "block_kind": "rework-needed",
            "block_recurrences": 2,
        }
        self.assertEqual(classify_task(task, 1000), TaskState.NEEDS_REWORK_ESCALATE)

    def test_merge_ready(self):
        """Blocked with 'merge-ready' → MERGE_READY."""
        task = {"id": "1", "status": "blocked", "block_kind": "merge-ready"}
        self.assertEqual(classify_task(task, 1000), TaskState.MERGE_READY)

    def test_blocked_human_needs_input(self):
        """Blocked with 'needs_input' → BLOCKED_HUMAN."""
        task = {"id": "1", "status": "blocked", "block_kind": "needs_input"}
        self.assertEqual(classify_task(task, 1000), TaskState.BLOCKED_HUMAN)

    def test_blocked_dependency(self):
        """Blocked with 'dependency' → BLOCKED_DEPENDENCY."""
        task = {"id": "1", "status": "blocked", "block_kind": "dependency"}
        self.assertEqual(classify_task(task, 1000), TaskState.BLOCKED_DEPENDENCY)

    def test_ready_dispatch_no_assignee(self):
        """Ready task with no assignee → READY_DISPATCH."""
        task = {"id": "1", "status": "ready", "assignee": ""}
        self.assertEqual(classify_task(task, 1000), TaskState.READY_DISPATCH)

    def test_ready_dispatch_with_assignee(self):
        """Ready task with assignee → READY_DISPATCH."""
        task = {"id": "1", "status": "ready", "assignee": "brandosbackend"}
        self.assertEqual(classify_task(task, 1000), TaskState.READY_DISPATCH)

    def test_todo_generic(self):
        """Todo task with no special conditions → OTHER."""
        task = {"id": "1", "status": "todo"}
        self.assertEqual(classify_task(task, 1000), TaskState.OTHER)

    def test_empty_task(self):
        """Empty task dict → OTHER."""
        self.assertEqual(classify_task({}, 1000), TaskState.OTHER)

    def test_classify_all(self):
        """classify_all groups tasks correctly by state."""
        now = 10000
        tasks = [
            {"id": "1", "status": "done"},
            {"id": "2", "status": "running", "started_at": 9000, "heartbeat_at": 9950, "max_runtime_seconds": 36000},
            {"id": "3", "status": "blocked", "block_kind": "review-required"},
        ]
        grouped = classify_all(tasks, now)
        self.assertEqual(len(grouped["done"]), 1)
        self.assertEqual(len(grouped["running_healthy"]), 1)
        self.assertEqual(len(grouped["needs_review"]), 1)

    def test_running_with_no_max_runtime(self):
        """Running task with no max_runtime set → should classify based on heartbeat."""
        task = {
            "id": "1",
            "status": "running",
            "started_at": 5000,
            "heartbeat_at": 9900,
            "max_runtime_seconds": None,
        }
        self.assertEqual(classify_task(task, 10000), TaskState.RUNNING_HEALTHY)


class TestCircularDetection(unittest.TestCase):
    """Tests for detect_circular_links."""

    def test_no_cycles(self):
        """Simple chain A→B→C has no cycles."""
        links = [("A", "B"), ("B", "C")]
        self.assertEqual(detect_circular_links(links), [])

    def test_two_node_cycle(self):
        """A→B→A is a two-node cycle."""
        links = [("A", "B"), ("B", "A")]
        cycles = detect_circular_links(links)
        self.assertEqual(len(cycles), 1)
        cycle = cycles[0]
        self.assertIn("A", cycle)
        self.assertIn("B", cycle)

    def test_three_node_cycle(self):
        """A→B→C→A is a three-node cycle."""
        links = [("A", "B"), ("B", "C"), ("C", "A")]
        cycles = detect_circular_links(links)
        self.assertEqual(len(cycles), 1)
        cycle = cycles[0]
        self.assertIn("A", cycle)
        self.assertIn("B", cycle)
        self.assertIn("C", cycle)

    def test_empty_links(self):
        """Empty links → no cycles."""
        self.assertEqual(detect_circular_links([]), [])

    def test_disconnected_graph(self):
        """Disconnected components with no cycles."""
        links = [("A", "B"), ("C", "D")]
        self.assertEqual(detect_circular_links(links), [])

    def test_self_loop(self):
        """A→A is a self-loop (cycle)."""
        links = [("A", "A")]
        cycles = detect_circular_links(links)
        self.assertEqual(len(cycles), 1)


class TestStrandedDetection(unittest.TestCase):
    """Tests for detect_stranded_tasks."""

    def test_stranded_with_all_parents_done(self):
        """Task in todo with all parents done → stranded."""
        tasks = [
            {"id": "P1", "status": "done"},
            {"id": "P2", "status": "done"},
            {"id": "C1", "status": "todo"},
        ]
        links = [("P1", "C1"), ("P2", "C1")]
        stranded = detect_stranded_tasks(tasks, links)
        self.assertIn("C1", stranded)

    def test_not_stranded_partial_parents(self):
        """Task with one parent not done → not stranded."""
        tasks = [
            {"id": "P1", "status": "done"},
            {"id": "P2", "status": "running"},
            {"id": "C1", "status": "todo"},
        ]
        links = [("P1", "C1"), ("P2", "C1")]
        stranded = detect_stranded_tasks(tasks, links)
        self.assertNotIn("C1", stranded)

    def test_not_stranded_already_ready(self):
        """Task already in 'ready' → not stranded."""
        tasks = [
            {"id": "P1", "status": "done"},
            {"id": "C1", "status": "ready"},
        ]
        links = [("P1", "C1")]
        stranded = detect_stranded_tasks(tasks, links)
        self.assertEqual(stranded, [])

    def test_no_parents_not_stranded(self):
        """Todo task with no parents → not stranded (needs triage)."""
        tasks = [{"id": "A", "status": "todo"}]
        links = []
        stranded = detect_stranded_tasks(tasks, links)
        self.assertEqual(stranded, [])

    def test_empty_db(self):
        """Empty task list → no stranded."""
        self.assertEqual(detect_stranded_tasks([], []), [])

    def test_multiple_stranded(self):
        """Multiple todo tasks with all parents done."""
        tasks = [
            {"id": "P1", "status": "done"},
            {"id": "C1", "status": "todo"},
            {"id": "C2", "status": "todo"},
        ]
        links = [("P1", "C1"), ("P1", "C2")]
        stranded = detect_stranded_tasks(tasks, links)
        self.assertEqual(set(stranded), {"C1", "C2"})


class TestWipCounting(unittest.TestCase):
    """Tests for count_implementation_wip."""

    def test_running_impl_profile(self):
        """Running task with impl profile → counts."""
        tasks = [{"id": "1", "status": "running", "assignee": "brandosbackend"}]
        self.assertEqual(count_implementation_wip(tasks), 1)

    def test_blocked_impl_profile(self):
        """Blocked task with impl profile → counts."""
        tasks = [{"id": "1", "status": "blocked", "assignee": "brandosfrontend"}]
        self.assertEqual(count_implementation_wip(tasks), 1)

    def test_quality_does_not_count(self):
        """Quality profile tasks → do NOT count."""
        tasks = [{"id": "1", "status": "running", "assignee": "brandosquality"}]
        self.assertEqual(count_implementation_wip(tasks), 0)

    def test_orchestrator_does_not_count(self):
        """Orchestrator profile tasks → do NOT count."""
        tasks = [{"id": "1", "status": "blocked", "assignee": "brandosorchestrator"}]
        self.assertEqual(count_implementation_wip(tasks), 0)

    def test_social_does_not_count(self):
        """Social profile tasks → do NOT count."""
        tasks = [{"id": "1", "status": "running", "assignee": "brandossocial"}]
        self.assertEqual(count_implementation_wip(tasks), 0)

    def test_done_impl_does_not_count(self):
        """Done tasks → do NOT count regardless of profile."""
        tasks = [{"id": "1", "status": "done", "assignee": "brandosbackend"}]
        self.assertEqual(count_implementation_wip(tasks), 0)

    def test_empty_assignee(self):
        """Task with no assignee → does NOT count."""
        tasks = [{"id": "1", "status": "running", "assignee": ""}]
        self.assertEqual(count_implementation_wip(tasks), 0)

    def test_max_wip(self):
        """Multiple impl tasks running → count all."""
        tasks = [
            {"id": "1", "status": "running", "assignee": "brandosbackend"},
            {"id": "2", "status": "blocked", "assignee": "brandosfrontend"},
            {"id": "3", "status": "running", "assignee": "brandosintelligence"},
            {"id": "4", "status": "running", "assignee": "brandosquality"},  # exempt
        ]
        self.assertEqual(count_implementation_wip(tasks), 3)


class TestRecoveryPlan(unittest.TestCase):
    """Tests for build_recovery_plan and supporting functions."""

    def setUp(self):
        """Clean up temp files after each test."""
        self._temp_files = []

    def tearDown(self):
        for f in self._temp_files:
            if os.path.exists(f):
                os.unlink(f)

    def _make_db(self, tasks, links=None):
        db = make_temp_kanban_db(tasks, links)
        self._temp_files.append(db)
        return db

    def test_empty_db(self):
        """Recovery plan with empty DB returns valid structure."""
        db = self._make_db([])
        plan = build_recovery_plan(db, now=10000)
        self.assertIn("timestamp", plan)
        self.assertIn("wip", plan)
        self.assertIn("actions_recommended", plan)
        self.assertEqual(plan["wip"]["current"], 0)
        self.assertEqual(plan["wip"]["limit"], 2)
        self.assertEqual(plan["wip"]["at_limit"], False)

    def test_all_done(self):
        """All done tasks → no actions recommended."""
        tasks = [
            {"id": "1", "status": "done"},
            {"id": "2", "status": "done"},
        ]
        db = self._make_db(tasks)
        plan = build_recovery_plan(db, now=10000)
        self.assertEqual(plan["healthy_running"], [])
        self.assertEqual(plan["timed_out_tasks"], [])
        self.assertEqual(plan["stalled_tasks"], [])

    def test_timed_out_detected(self):
        """Timed out task appears in plan."""
        tasks = [{
            "id": "1",
            "status": "running",
            "started_at": 1000,
            "max_runtime_seconds": 3600,
            "heartbeat_at": None,
        }]
        db = self._make_db(tasks)
        plan = build_recovery_plan(db, now=5000)
        self.assertEqual(len(plan["timed_out_tasks"]), 1)
        self.assertEqual(plan["timed_out_tasks"][0]["id"], "1")

    def test_wip_limit_in_plan(self):
        """WIP limit reached appears in actions."""
        tasks = [
            {"id": "1", "status": "running", "assignee": "brandosbackend"},
            {"id": "2", "status": "running", "assignee": "brandosfrontend"},
            {"id": "3", "status": "running", "assignee": "brandosquality"},  # exempt
        ]
        db = self._make_db(tasks)
        plan = build_recovery_plan(db, now=10000)
        self.assertTrue(plan["wip"]["at_limit"])
        wip_actions = [a for a in plan["actions_recommended"] if a["action"] == "wip_limit_reached"]
        self.assertEqual(len(wip_actions), 1)

    def test_circular_in_plan(self):
        """Circular dependencies appear in plan."""
        tasks = [
            {"id": "A", "status": "blocked", "block_kind": "dependency"},
            {"id": "B", "status": "blocked", "block_kind": "dependency"},
        ]
        links = [("A", "B"), ("B", "A")]
        db = self._make_db(tasks, links)
        plan = build_recovery_plan(db, now=10000)
        self.assertGreater(len(plan["circular_links"]), 0)

    def test_stranded_in_plan(self):
        """Stranded tasks appear in plan."""
        tasks = [
            {"id": "P1", "status": "done"},
            {"id": "C1", "status": "todo"},
        ]
        links = [("P1", "C1")]
        db = self._make_db(tasks, links)
        plan = build_recovery_plan(db, now=10000)
        self.assertEqual(len(plan["stranded"]), 1)
        self.assertEqual(plan["stranded"][0]["id"], "C1")

    def test_extract_jira_key(self):
        """Jira key extraction works correctly."""
        self.assertEqual(extract_jira_key("BOS-151: implement supervisor"), "BOS-151")
        self.assertEqual(extract_jira_key("fix(bos-42): patch"), "BOS-42")
        self.assertIsNone(extract_jira_key("no key here"))
        self.assertIsNone(extract_jira_key(""))
        self.assertIsNone(extract_jira_key(None))

    def test_get_tasks_from_db(self):
        """get_tasks reads tasks from DB correctly."""
        tasks_in = [
            {"id": "1", "status": "running"},
            {"id": "2", "status": "done"},
        ]
        db = self._make_db(tasks_in)
        tasks_out = get_tasks(db)
        self.assertEqual(len(tasks_out), 2)

    def test_get_task_links_from_db(self):
        """get_task_links reads links from DB correctly."""
        db = self._make_db(
            [{"id": "A"}, {"id": "B"}],
            links=[("A", "B")],
        )
        links = get_task_links(db)
        self.assertEqual(links, [("A", "B")])

    def test_get_task_runs_empty(self):
        """get_task_runs returns empty for nonexistent task."""
        db = self._make_db([])
        runs = get_task_runs(db, "nonexistent")
        self.assertEqual(runs, [])

    def test_archived_tasks_excluded(self):
        """Archived tasks are not included in recovery plan."""
        tasks = [
            {"id": "1", "status": "running", "assignee": "brandosbackend"},
            {"id": "2", "status": "archived", "assignee": "brandosfrontend"},
        ]
        db = self._make_db(tasks)
        all_tasks = get_tasks(db)
        self.assertEqual(len(all_tasks), 1)


class TestAudit(unittest.TestCase):
    """Tests for audit logging and redaction."""

    def test_redact_api_key(self):
        """API keys in values are redacted."""
        result = redact_dict({"api_key": "sk_live_12345", "name": "test"})
        self.assertEqual(result["api_key"], "[REDACTED]")
        self.assertEqual(result["name"], "test")

    def test_redact_password(self):
        """Password fields are redacted."""
        result = redact_dict({"password": "hunter2", "user": "admin"})
        self.assertEqual(result["password"], "[REDACTED]")
        self.assertEqual(result["user"], "admin")

    def test_redact_nested(self):
        """Nested sensitive keys are redacted."""
        result = redact_dict({
            "data": {"token": "secret123", "name": "test"},
            "api_token": "key_abc",
        })
        self.assertEqual(result["data"]["token"], "[REDACTED]")
        self.assertEqual(result["api_token"], "[REDACTED]")

    def test_redact_list_of_dicts(self):
        """Sensitive keys in list elements are redacted."""
        result = redact_dict({
            "items": [{"secret": "val1", "id": 1}, {"api_key": "val2", "id": 2}]
        })
        self.assertEqual(result["items"][0]["secret"], "[REDACTED]")
        self.assertEqual(result["items"][1]["api_key"], "[REDACTED]")

    def test_redact_bearer_in_value(self):
        """Bearer tokens in string values are redacted."""
        result = redact_dict({"header": "Bearer eyJhbGciOiJIUzI1NiJ9"})
        self.assertEqual(result["header"], "[REDACTED]")

    def test_redact_basic_auth_in_value(self):
        """Basic auth in string values are redacted."""
        result = redact_dict({"auth": "Basic dXNlcjpwYXNz"})
        self.assertEqual(result["auth"], "[REDACTED]")

    def test_redact_env_var(self):
        """Environment variable references to secrets are redacted."""
        result = redact_dict({"ref": "$MY_TOKEN_VAR"})
        self.assertEqual(result["ref"], "[REDACTED]")

    def test_redact_authorization_header(self):
        """Authorization headers are redacted."""
        result = redact_dict({"authorization": "Bearer token123"})
        self.assertEqual(result["authorization"], "[REDACTED]")

    def test_redact_credential_key(self):
        """Credential fields are redacted."""
        result = redact_dict({"credential": "some-value", "normal": "keep"})
        self.assertEqual(result["credential"], "[REDACTED]")
        self.assertEqual(result["normal"], "keep")

    def test_redacting_filter(self):
        """RedactingFilter modifies log messages."""
        f = RedactingFilter()
        import logging
        record = logging.LogRecord(
            "test", logging.INFO, "", 0,
            "Using Bearer eyJhbGciOiJIUzI1NiJ9 for auth", (), None
        )
        f.filter(record)
        self.assertIn("[REDACTED]", record.msg)
        self.assertNotIn("eyJhbGciOiJIUzI1NiJ9", record.msg)

    def test_audit_logger_json_output(self):
        """AuditLogger emits valid JSON."""
        stream = StringIO()
        audit = AuditLogger("test", stream=stream)
        audit.info("test_event", key="value")
        output = stream.getvalue().strip()
        parsed = json.loads(output)
        self.assertEqual(parsed["level"], "INFO")
        self.assertEqual(parsed["event"], "test_event")
        self.assertEqual(parsed["key"], "value")
        self.assertIn("timestamp", parsed)

    def test_audit_action_method(self):
        """AuditLogger.action produces correct structure."""
        stream = StringIO()
        audit = AuditLogger("test", stream=stream)
        audit.action("restart", "task-1", "Timed out")
        output = stream.getvalue().strip()
        parsed = json.loads(output)
        self.assertEqual(parsed["level"], "ACTION")
        self.assertEqual(parsed["action_type"], "restart")
        self.assertEqual(parsed["task_id"], "task-1")
        self.assertEqual(parsed["details"], "Timed out")

    def test_audit_warn_method(self):
        """AuditLogger.warn produces correct structure."""
        stream = StringIO()
        audit = AuditLogger("test", stream=stream)
        audit.warn("low_disk", free_mb=10)
        output = stream.getvalue().strip()
        parsed = json.loads(output)
        self.assertEqual(parsed["level"], "WARN")
        self.assertEqual(parsed["free_mb"], 10)

    def test_audit_error_method(self):
        """AuditLogger.error produces correct structure."""
        stream = StringIO()
        audit = AuditLogger("test", stream=stream)
        audit.error("db_not_found", path="/tmp/fake.db")
        output = stream.getvalue().strip()
        parsed = json.loads(output)
        self.assertEqual(parsed["level"], "ERROR")
        self.assertEqual(parsed["path"], "/tmp/fake.db")

    def test_audit_redacts_secrets(self):
        """Audit entries automatically redact sensitive data."""
        stream = StringIO()
        audit = AuditLogger("test", stream=stream)
        audit.info("auth", token="supersecret123", api_key="sk_live_abc")
        output = stream.getvalue().strip()
        parsed = json.loads(output)
        self.assertEqual(parsed["token"], "[REDACTED]")
        self.assertEqual(parsed["api_key"], "[REDACTED]")
        self.assertNotIn("supersecret123", output)
        self.assertNotIn("sk_live_abc", output)


class TestRestartIdempotency(unittest.TestCase):
    """Tests that restart actions are idempotent and don't create duplicates."""

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

    def test_timed_out_stays_timed_out(self):
        """A timed-out task stays timed-out across multiple scans."""
        tasks = [{
            "id": "1",
            "status": "running",
            "started_at": 1000,
            "max_runtime_seconds": 3600,
            "heartbeat_at": None,
        }]
        db = self._make_db(tasks)
        now = 5000

        plan1 = build_recovery_plan(db, now=now)
        plan2 = build_recovery_plan(db, now=now + 100)

        self.assertEqual(len(plan1["timed_out_tasks"]), len(plan2["timed_out_tasks"]))
        self.assertEqual(
            plan1["timed_out_tasks"][0]["id"],
            plan2["timed_out_tasks"][0]["id"],
        )

    def test_stalled_then_timed_out(self):
        """A stalled task transitions to timed_out as time passes."""
        tasks = [{
            "id": "1",
            "status": "running",
            "started_at": 1000,
            "max_runtime_seconds": 3600,
            "heartbeat_at": None,
        }]
        db = self._make_db(tasks)

        # Before max_runtime: stalled (no heartbeat)
        plan_early = build_recovery_plan(db, now=3000)
        self.assertEqual(len(plan_early["stalled_tasks"]), 1)
        self.assertEqual(len(plan_early["timed_out_tasks"]), 0)

        # After max_runtime: timed out
        plan_late = build_recovery_plan(db, now=5000)
        self.assertEqual(len(plan_late["timed_out_tasks"]), 1)
        self.assertEqual(len(plan_late["stalled_tasks"]), 0)

    def test_recovery_plan_deterministic(self):
        """Same inputs produce same output."""
        tasks = [
            {"id": "1", "status": "done"},
            {"id": "2", "status": "running", "started_at": 9000, "heartbeat_at": 9950, "max_runtime_seconds": 36000},
        ]
        db = self._make_db(tasks)
        plan1 = build_recovery_plan(db, now=10000)
        plan2 = build_recovery_plan(db, now=10000)
        # Compare everything except timestamp-dependent fields
        self.assertEqual(plan1["wip"], plan2["wip"])
        self.assertEqual(len(plan1["healthy_running"]), len(plan2["healthy_running"]))


if __name__ == "__main__":
    unittest.main()
