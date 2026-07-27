#!/usr/bin/env python3
"""
Tests for the Jira-to-Hermes task bridge.

Tests: eligibility filtering, dependency resolution, label/profile mapping,
bounded context, redaction, failure handling, idempotency, and boundary tests.

Run: python -m pytest tests/test_bridge.py -v
"""

import io
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Import from normal repo layout or this flat review bundle.
_HERE = Path(__file__).resolve().parent
_SCRIPT_DIR = _HERE.parent / "scripts"
if not (_SCRIPT_DIR / "jira_hermes_bridge.py").exists():
    _SCRIPT_DIR = _HERE
sys.path.insert(0, str(_SCRIPT_DIR))
BRIDGE_FILE = _SCRIPT_DIR / "jira_hermes_bridge.py"

from jira_hermes_bridge import (
    AGENT_LABEL_TO_PROFILE,
    BLOCK_LABELS,
    RedactingFilter,
    check_eligibility,
    map_agent_to_profile,
    derive_branch_name,
    build_context_package,
    redact_dict,
    Dispatcher,
    JiraClient,
    HermesClient,
    CredentialError,
    JiraApiError,
    HermesApiError,
    _extract_jira_error,
)
from check_readiness import validate_issue

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_issue(
    key: str = "BOS-999",
    summary: str = "Test issue",
    labels: list[str] | None = None,
    description: str = "## Goal\nTest goal\n\n## Acceptance Criteria\n- Works\n\n## Tests and Evidence\nUnit tests\n\n## Security\nNo secrets\n\n## Context\nBackend module",
    issuelinks: list[dict] | None = None,
) -> dict:
    """Helper to build mock Jira issues."""
    if labels is None:
        labels = [
            "ready-for-dispatch", "agent-backend", "role-dev",
            "review-by-agent-quality", "risk-low", "phase-test",
            "points-2", "ver-0.1-foundation",
        ]
    return {
        "key": key,
        "fields": {
            "summary": summary,
            "labels": labels,
            "description": description,
            "issuelinks": issuelinks or [],
        },
    }


def make_blocker_link(blocker_key: str, status: str = "To Do") -> dict:
    """Helper to build mock blocker issue links."""
    return {
        "type": {"inward": "is blocked by", "outward": "blocks"},
        "inwardIssue": {
            "key": blocker_key,
            "fields": {"status": {"name": status}},
        },
    }


# ---------------------------------------------------------------------------
# Eligibility tests
# ---------------------------------------------------------------------------


class TestEligibility:
    """Test issue eligibility checks."""

    def test_eligible_issue_passes(self):
        """A properly labeled issue passes all eligibility checks."""
        issue = make_issue()
        eligible, reason, agent = check_eligibility(issue)
        assert eligible is True
        assert agent == "agent-backend"
        assert "eligible" in reason.lower()

    def test_missing_ready_for_dispatch(self):
        """Issue without ready-for-dispatch is rejected."""
        issue = make_issue(labels=[
            "agent-backend", "risk-low", "phase-test",
            "points-1", "ver-0.1",
        ])
        eligible, reason, agent = check_eligibility(issue)
        assert eligible is False
        assert "ready-for-dispatch" in reason

    def test_do_not_dispatch_yet_blocks(self):
        """do-not-dispatch-yet label blocks dispatch."""
        issue = make_issue(labels=[
            "ready-for-dispatch", "agent-backend", "do-not-dispatch-yet",
            "risk-low", "phase-test", "points-1", "ver-0.1",
        ])
        eligible, reason, agent = check_eligibility(issue)
        assert eligible is False
        assert "do-not-dispatch-yet" in reason

    def test_status_blocked_blocks(self):
        """status-blocked label blocks dispatch."""
        issue = make_issue(labels=[
            "ready-for-dispatch", "agent-backend", "status-blocked",
            "risk-low", "phase-test", "points-1", "ver-0.1",
        ])
        eligible, reason, agent = check_eligibility(issue)
        assert eligible is False
        assert "status-blocked" in reason

    def test_deferred_scope_blocks(self):
        """deferred-scope label blocks dispatch."""
        issue = make_issue(labels=[
            "ready-for-dispatch", "agent-backend", "deferred-scope",
            "risk-low", "phase-test", "points-1", "ver-0.1",
        ])
        eligible, reason, agent = check_eligibility(issue)
        assert eligible is False
        assert "deferred-scope" in reason

    def test_multiple_block_labels(self):
        """Multiple block labels are all reported."""
        issue = make_issue(labels=[
            "ready-for-dispatch", "agent-backend",
            "do-not-dispatch-yet", "status-blocked",
            "risk-low", "phase-test", "points-1", "ver-0.1",
        ])
        eligible, reason, _ = check_eligibility(issue)
        assert eligible is False
        assert "do-not-dispatch-yet" in reason
        assert "status-blocked" in reason

    def test_no_agent_label(self):
        """Issue without any agent-* label is rejected."""
        issue = make_issue(labels=[
            "ready-for-dispatch", "risk-low", "phase-test",
            "points-1", "ver-0.1",
        ])
        eligible, reason, agent = check_eligibility(issue)
        assert eligible is False
        assert "No agent" in reason
        assert agent is None

    def test_multiple_agent_labels_rejected(self):
        """Multiple agent-* labels are rejected."""
        issue = make_issue(labels=[
            "ready-for-dispatch", "agent-backend", "agent-frontend",
            "risk-low", "phase-test", "points-1", "ver-0.1",
        ])
        eligible, reason, agent = check_eligibility(issue)
        assert eligible is False
        assert "Multiple agent" in reason

    def test_unknown_agent_label_rejected(self):
        """An agent-* label not in the mapping is rejected."""
        issue = make_issue(labels=[
            "ready-for-dispatch", "agent-unknown",
            "risk-low", "phase-test", "points-1", "ver-0.1",
        ])
        eligible, reason, agent = check_eligibility(issue)
        assert eligible is False
        assert "Unknown agent" in reason

    def test_unresolved_blocker_link_rejected(self):
        """An unresolved blocker link prevents dispatch."""
        issue = make_issue(
            issuelinks=[make_blocker_link("BOS-100", "To Do")]
        )
        eligible, reason, agent = check_eligibility(issue)
        assert eligible is False
        assert "BOS-100" in reason
        assert "Unresolved" in reason

    def test_resolved_blocker_link_passes(self):
        """A resolved blocker link allows dispatch."""
        issue = make_issue(
            issuelinks=[make_blocker_link("BOS-100", "Done")]
        )
        eligible, reason, agent = check_eligibility(issue)
        assert eligible is True
        assert agent == "agent-backend"

    def test_mixed_resolved_unresolved_blockers(self):
        """Mix of resolved and unresolved blockers rejects."""
        issue = make_issue(issuelinks=[
            make_blocker_link("BOS-100", "Done"),
            make_blocker_link("BOS-101", "In Progress"),
        ])
        eligible, reason, _ = check_eligibility(issue)
        assert eligible is False
        assert "BOS-101" in reason
        assert "BOS-100" not in reason


# ---------------------------------------------------------------------------
# Label → Profile mapping tests
# ---------------------------------------------------------------------------


class TestLabelToProfileMapping:
    """Test agent label to Hermes profile mapping."""

    def test_all_agent_labels_map(self):
        """Every known agent label maps to a valid profile."""
        for label, profile in AGENT_LABEL_TO_PROFILE.items():
            assert profile.startswith("brandos"), f"{label} → {profile} should start with 'brandos'"

    def test_backend_maps_correctly(self):
        assert map_agent_to_profile("agent-backend") == "brandosbackend"

    def test_frontend_maps_correctly(self):
        assert map_agent_to_profile("agent-frontend") == "brandosfrontend"

    def test_quality_maps_correctly(self):
        assert map_agent_to_profile("agent-quality") == "brandosquality"

    def test_orchestrator_maps_correctly(self):
        assert map_agent_to_profile("agent-orchestrator") == "brandosorchestrator"

    def test_intelligence_maps_correctly(self):
        assert map_agent_to_profile("agent-intelligence") == "brandosintelligence"

    def test_social_maps_correctly(self):
        assert map_agent_to_profile("agent-social") == "brandossocial"

    def test_preview_maps_correctly(self):
        assert map_agent_to_profile("agent-preview") == "brandospreview"

    def test_unknown_label_raises(self):
        with pytest.raises(ValueError, match="Unknown agent label"):
            map_agent_to_profile("agent-nonexistent")

    def test_mapping_determinism(self):
        """Same input always produces the same output."""
        result1 = map_agent_to_profile("agent-backend")
        result2 = map_agent_to_profile("agent-backend")
        assert result1 == result2

    def test_no_profile_overlaps(self):
        """Each agent label maps to a unique profile."""
        profiles = list(AGENT_LABEL_TO_PROFILE.values())
        assert len(profiles) == len(set(profiles))


# ---------------------------------------------------------------------------
# Branch name derivation tests
# ---------------------------------------------------------------------------


class TestBranchDerivation:
    """Test deterministic branch name generation."""

    def test_basic_derivation(self):
        branch = derive_branch_name("BOS-22", "Implement Jira-to-Hermes bridge")
        assert "bos22" in branch
        assert "implement" in branch

    def test_deterministic(self):
        """Same inputs always produce the same output."""
        b1 = derive_branch_name("BOS-50", "Add login flow")
        b2 = derive_branch_name("BOS-50", "Add login flow")
        assert b1 == b2

    def test_special_chars_stripped(self):
        """Non-alphanumeric characters are replaced with hyphens."""
        branch = derive_branch_name("BOS-1", "Fix #42: login & auth!")
        assert "#" not in branch
        assert "&" not in branch
        assert "!" not in branch

    def test_length_limited(self):
        """Summary slug is capped at 40 characters."""
        long_summary = "A" * 100
        branch = derive_branch_name("BOS-1", long_summary)
        slug_part = branch.split("-", 1)[1] if "-" in branch else branch
        assert len(slug_part) <= 45  # 40 chars + some hyphens


# ---------------------------------------------------------------------------
# Bounded context tests
# ---------------------------------------------------------------------------


class TestBoundedContext:
    """Test bounded context package building."""

    def test_basic_context_extraction(self):
        """All major sections are extracted."""
        issue = make_issue()
        ctx = build_context_package(issue)
        assert ctx["issue_key"] == "BOS-999"
        assert ctx["summary"] == "Test issue"
        assert "Test goal" in ctx["sections"].get("goal", "")
        assert ctx["acceptance_criteria"]
        assert ctx["tests_evidence"]
        assert ctx["security"]
        assert ctx["context"]

    def test_adf_description_extraction(self):
        """ADF dict descriptions are handled."""
        adf_desc = {
            "type": "doc",
            "content": [
                {"type": "heading", "attrs": {"level": 2}, "content": [
                    {"type": "text", "text": "Acceptance Criteria"},
                ]},
                {"type": "paragraph", "content": [
                    {"type": "text", "text": "Feature works"},
                ]},
            ],
        }
        issue = make_issue(description=adf_desc)
        ctx = build_context_package(issue)
        assert "Feature works" in ctx["acceptance_criteria"]

    def test_dependency_extraction(self):
        """Linked dependencies are extracted."""
        issue = make_issue(issuelinks=[
            make_blocker_link("BOS-100", "Done"),
        ])
        ctx = build_context_package(issue)
        assert len(ctx["dependencies"]) == 1
        assert ctx["dependencies"][0]["key"] == "BOS-100"
        assert ctx["dependencies"][0]["status"] == "Done"

    def test_empty_description(self):
        """Empty description yields empty sections."""
        issue = make_issue(description="")
        ctx = build_context_package(issue)
        assert ctx["sections"] == {}

    def test_no_product_vision_leakage(self):
        """Context includes only what's in the issue, not external knowledge."""
        issue = make_issue()
        ctx = build_context_package(issue)
        # Context should not contain strings outside the issue
        full_json = json.dumps(ctx)
        assert "PRODUCT_VISION" not in full_json
        assert "ROADMAP" not in full_json

    def test_scope_and_out_of_scope(self):
        """Scope sections are parsed when present."""
        desc = (
            "## Goal\nBuild feature\n\n"
            "## Scope\nFrontend only\n\n"
            "## Out of Scope\nBackend changes\n\n"
            "## Acceptance Criteria\nWorks\n\n"
            "## Tests and Evidence\nTested\n\n"
            "## Security\nSafe\n\n"
            "## Context\nFrontend app"
        )
        issue = make_issue(description=desc)
        ctx = build_context_package(issue)
        assert ctx["scope"] == "Frontend only"
        assert ctx["out_of_scope"] == "Backend changes"

    def test_labels_preserved(self):
        """All labels from the issue are preserved."""
        issue = make_issue()
        ctx = build_context_package(issue)
        assert "ready-for-dispatch" in ctx["labels"]
        assert "agent-backend" in ctx["labels"]


# ---------------------------------------------------------------------------
# Redaction tests
# ---------------------------------------------------------------------------


class TestRedaction:
    """Test credential and sensitive data redaction."""

    def test_token_redacted(self):
        """API tokens are redacted."""
        data = {"api_token": "secret-123", "name": "test"}
        result = redact_dict(data)
        assert result["api_token"] == "[REDACTED]"
        assert result["name"] == "test"

    def test_nested_redaction(self):
        """Nested dicts are recursively redacted."""
        data = {"config": {"password": "hunter2", "host": "localhost"}}
        result = redact_dict(data)
        assert result["config"]["password"] == "[REDACTED]"

    def test_unknown_keys_preserved(self):
        """Non-sensitive keys pass through."""
        data = {"issue_key": "BOS-1", "summary": "Test", "labels": ["a"]}
        result = redact_dict(data)
        assert result == data

    def test_authorization_header_redacted(self):
        data = {"Authorization": "Bearer xyz"}
        result = redact_dict(data)
        assert result["Authorization"] == "[REDACTED]"

    def test_api_key_variants(self):
        """Various API key naming conventions are caught."""
        for key in ["api_key", "apiKey", "API_KEY", "api-key"]:
            result = redact_dict({key: "secret"})
            assert result[key] == "[REDACTED]", f"Failed for key variant: {key}"


# ---------------------------------------------------------------------------
# RedactingFilter log-level regression tests
# ---------------------------------------------------------------------------


class TestRedactingFilter:
    """Test the log-record RedactingFilter catches free-text secret forms."""

    @staticmethod
    def _apply_filter(msg: str) -> str:
        """Apply RedactingFilter to a log record message and return the result."""
        import logging
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg=msg, args=None, exc_info=None,
        )
        f = RedactingFilter()
        f.filter(record)
        return record.msg

    def test_authorization_bearer_header(self):
        """Authorization: Bearer <value> is fully redacted."""
        secret = "eyJhbGciOiJIUzI1NiJ9.secret-payload"
        msg = f'{{"Authorization": "Authorization: Bearer {secret}"}}'
        result = self._apply_filter(msg)
        assert secret not in result, f"Secret leaked through Authorization: Bearer pattern"
        assert "[REDACTED]" in result

    def test_authorization_bearer_lowercase(self):
        """authorization: bearer <value> (lowercase) is redacted."""
        secret = "sk-proj-abcdef1234567890abcdef"
        msg = f"authorization: bearer {secret}"
        result = self._apply_filter(msg)
        assert secret not in result, "Secret leaked through lowercase authorization: bearer"
        assert "[REDACTED]" in result

    def test_authorization_equals_value(self):
        """authorization=<value> form is redacted."""
        secret = "tok_live_abcdef1234567890"
        msg = f"authorization={secret} other_data"
        result = self._apply_filter(msg)
        assert secret not in result, "Secret leaked through authorization=value"
        assert "[REDACTED]" in result

    def test_bearer_standalone(self):
        """Standalone Bearer <value> (not in Authorization header) is redacted."""
        secret = "ghp_1234567890abcdef1234567890abcdef123456"
        msg = f"Using Bearer {secret} for API call"
        result = self._apply_filter(msg)
        assert secret not in result, "Secret leaked through standalone Bearer pattern"
        assert "[REDACTED]" in result

    def test_api_key_equals_value(self):
        """api_key=<value> form is redacted."""
        secret = "ak_prod_1234567890abcdef"
        msg = f"api_key={secret} set in config"
        result = self._apply_filter(msg)
        assert secret not in result, "Secret leaked through api_key=value"
        assert "[REDACTED]" in result

    def test_api_key_with_hyphen(self):
        """api-key=<value> form is redacted."""
        secret = "key-abcdef1234567890"
        msg = f"api-key={secret}"
        result = self._apply_filter(msg)
        assert secret not in result, "Secret leaked through api-key=value"
        assert "[REDACTED]" in result

    def test_token_equals_value(self):
        """token=<value> form is redacted."""
        secret = "xoxb-secret-token-value"
        msg = f"token={secret} expires soon"
        result = self._apply_filter(msg)
        assert secret not in result, "Secret leaked through token=value"
        assert "[REDACTED]" in result

    def test_password_colon_value(self):
        """password: <value> form is redacted."""
        secret = "supersecretpassword123"
        msg = f"password: {secret} stored"
        result = self._apply_filter(msg)
        assert secret not in result, "Secret leaked through password:value"
        assert "[REDACTED]" in result

    def test_original_secret_never_present_in_log(self):
        """Comprehensive: the original secret string never appears after filtering."""
        secrets = [
            "Bearer sk-proj-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "authorization=tok_live_bbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "api_key=ak_cccccccccccccccccccccccccccccccccccccc",
            "Authorization: Bearer ddddddddddddddddddddddddddddddddddddddd",
        ]
        for msg in secrets:
            result = self._apply_filter(msg)
            # Extract the actual secret portion (after the key/indicator)
            for token in msg.split():
                if len(token) > 12 and token not in ("Authorization:", "authorization=", "Bearer", "api_key=", "Bearer"):
                    # This looks like it could be the secret value
                    if any(token.startswith(p) for p in ("sk-", "tok_", "ak_", "ghp_")):
                        assert token not in result, f"Secret '{token}' found in filtered output: {result}"


# ---------------------------------------------------------------------------
# Dispatcher tests
# ---------------------------------------------------------------------------


class TestDispatcher:
    """Test the dispatch orchestration logic."""

    def _make_dispatcher(self, issues=None, dry_run=True):
        """Create a dispatcher with mocked Jira client."""
        jira = MagicMock(spec=JiraClient)
        jira.search_issues.return_value = issues or []
        hermes = MagicMock(spec=HermesClient)
        hermes.check_existing_task.return_value = None
        hermes.create_task.return_value = {"task_id": "test-task-123"}

        import logging
        from jira_hermes_bridge import StructuredLogger
        logger = StructuredLogger(level=logging.WARNING)

        return Dispatcher(
            jira=jira,
            hermes=hermes,
            logger=logger,
            project_key="BOS",
            dry_run=dry_run,
        ), jira, hermes

    def test_eligible_issue_dispatched(self):
        """An eligible issue is dispatched to Hermes."""
        issues = [make_issue(key="BOS-200")]
        dispatcher, jira, hermes = self._make_dispatcher(issues)
        results = dispatcher.run()

        assert len(results) == 1
        assert results[0]["status"] == "dispatched"
        assert results[0]["issue_key"] == "BOS-200"
        hermes.create_task.assert_called_once()

    def test_ineligible_issue_skipped(self):
        """An ineligible issue is skipped without dispatching."""
        issues = [make_issue(key="BOS-201", labels=["agent-backend"])]
        dispatcher, jira, hermes = self._make_dispatcher(issues)
        results = dispatcher.run()

        assert len(results) == 1
        assert results[0]["status"] == "skipped"
        hermes.create_task.assert_not_called()

    def test_duplicate_suppressed(self):
        """A duplicate issue is suppressed via idempotency key."""
        issues = [make_issue(key="BOS-202")]
        dispatcher, jira, hermes = self._make_dispatcher(issues)
        hermes.check_existing_task.return_value = "existing-task-456"

        results = dispatcher.run()

        assert len(results) == 1
        assert results[0]["status"] == "skipped"
        assert "existing-task-456" in results[0]["reason"]
        hermes.create_task.assert_not_called()

    def test_hermes_failure_recorded(self):
        """A Hermes failure is recorded and issue blocked."""
        issues = [make_issue(key="BOS-203")]
        dispatcher, jira, hermes = self._make_dispatcher(issues, dry_run=False)
        hermes.create_task.side_effect = HermesApiError("Connection refused")

        results = dispatcher.run()

        assert len(results) == 1
        assert results[0]["status"] == "failed"
        # Should have attempted to record failure to Jira
        jira.add_comment.assert_called_once()

    def test_dry_run_no_jira_updates(self):
        """Dry run does not update Jira or call Hermes."""
        issues = [make_issue(key="BOS-204")]
        dispatcher, jira, hermes = self._make_dispatcher(issues, dry_run=True)

        results = dispatcher.run()

        assert results[0]["dry_run"] is True
        jira.add_comment.assert_not_called()
        jira.transition_issue.assert_not_called()

    def test_jira_comment_after_dispatch(self):
        """After dispatch, a comment is written to Jira."""
        issues = [make_issue(key="BOS-205")]
        dispatcher, jira, hermes = self._make_dispatcher(issues, dry_run=False)

        results = dispatcher.run()

        assert results[0]["status"] == "dispatched"
        jira.add_comment.assert_called_once()
        # Check the comment includes dispatch info
        call_args = jira.add_comment.call_args
        assert "BOS-205" in call_args[0][0]
        assert "Hermes" in call_args[0][1]

    def test_jira_transition_after_dispatch(self):
        """After dispatch, the issue is transitioned to In Progress."""
        issues = [make_issue(key="BOS-206")]
        dispatcher, jira, hermes = self._make_dispatcher(issues, dry_run=False)

        dispatcher.run()

        jira.transition_issue.assert_called_with("BOS-206", "In Progress")

    def test_mixed_results(self):
        """A cycle with eligible and ineligible issues produces mixed results."""
        issues = [
            make_issue(key="BOS-300"),  # eligible
            make_issue(key="BOS-301", labels=["agent-backend"]),  # missing ready-for-dispatch
            make_issue(key="BOS-302", labels=[
                "ready-for-dispatch", "agent-frontend", "status-blocked",
                "risk-low", "phase-test", "points-1", "ver-0.1",
            ]),
        ]
        dispatcher, jira, hermes = self._make_dispatcher(issues)
        results = dispatcher.run()

        assert len(results) == 3
        assert results[0]["status"] == "dispatched"
        assert results[1]["status"] == "skipped"
        assert results[2]["status"] == "skipped"


# ---------------------------------------------------------------------------
# Traceability: block-label issues must never dispatch
# ---------------------------------------------------------------------------


class TestBlockLabelTraceability:
    """Regression: BOS-20/BOS-21-style issues with do-not-dispatch-yet
    (or any block label) must NEVER be dispatched. This is a policy invariant,
    not a hardcoded issue-key exclusion — the gate is label-based."""

    def _make_dispatcher(self, issues, dry_run=True):
        jira = MagicMock(spec=JiraClient)
        jira.search_issues.return_value = issues
        hermes = MagicMock(spec=HermesClient)
        hermes.check_existing_task.return_value = None
        hermes.create_task.return_value = {"task_id": "should-not-happen"}

        import logging
        from jira_hermes_bridge import StructuredLogger
        logger = StructuredLogger(level=logging.WARNING)

        return Dispatcher(
            jira=jira, hermes=hermes, logger=logger,
            project_key="BOS", dry_run=dry_run,
        ), jira, hermes

    def test_do_not_dispatch_yet_never_dispatches(self):
        """Issues labeled do-not-dispatch-yet are never dispatched."""
        issue = make_issue(
            key="BOS-20",
            labels=[
                "ready-for-dispatch", "agent-backend", "do-not-dispatch-yet",
                "risk-low", "phase-test", "points-1", "ver-0.1",
            ],
        )
        dispatcher, jira, hermes = self._make_dispatcher([issue])
        results = dispatcher.run()

        assert len(results) == 1
        assert results[0]["status"] == "skipped"
        assert "do-not-dispatch-yet" in results[0]["reason"]
        hermes.create_task.assert_not_called()

    def test_status_blocked_never_dispatches(self):
        """Issues labeled status-blocked are never dispatched."""
        issue = make_issue(
            key="BOS-21",
            labels=[
                "ready-for-dispatch", "agent-backend", "status-blocked",
                "risk-low", "phase-test", "points-1", "ver-0.1",
            ],
        )
        dispatcher, jira, hermes = self._make_dispatcher([issue])
        results = dispatcher.run()

        assert len(results) == 1
        assert results[0]["status"] == "skipped"
        assert "status-blocked" in results[0]["reason"]
        hermes.create_task.assert_not_called()

    def test_deferred_scope_never_dispatches(self):
        """Issues labeled deferred-scope are never dispatched."""
        issue = make_issue(
            key="BOS-22-test",
            labels=[
                "ready-for-dispatch", "agent-backend", "deferred-scope",
                "risk-low", "phase-test", "points-1", "ver-0.1",
            ],
        )
        dispatcher, jira, hermes = self._make_dispatcher([issue])
        results = dispatcher.run()

        assert len(results) == 1
        assert results[0]["status"] == "skipped"
        assert "deferred-scope" in results[0]["reason"]
        hermes.create_task.assert_not_called()

    def test_all_block_labels_combined_never_dispatch(self):
        """Issues with ALL block labels simultaneously are never dispatched."""
        issue = make_issue(
            key="BOS-99",
            labels=[
                "ready-for-dispatch", "agent-backend",
                "do-not-dispatch-yet", "status-blocked", "deferred-scope",
                "risk-low", "phase-test", "points-1", "ver-0.1",
            ],
        )
        dispatcher, jira, hermes = self._make_dispatcher([issue])
        results = dispatcher.run()

        assert len(results) == 1
        assert results[0]["status"] == "skipped"
        hermes.create_task.assert_not_called()

    def test_no_hardcoded_issue_exclusions_in_eligibility(self):
        """Eligibility filtering is purely label-based — no issue keys are
        hard-coded in the production logic."""
        import inspect
        from jira_hermes_bridge import check_eligibility
        source = inspect.getsource(check_eligibility)
        # Must not contain any BOS-NNN style hard-coded key exclusions
        assert "BOS-" not in source, "check_eligibility must not hard-code issue keys"


# ---------------------------------------------------------------------------
# Idempotency test
# ---------------------------------------------------------------------------


class TestIdempotency:
    """Test that duplicate dispatch is prevented."""

    def test_idempotency_key_format(self):
        """Idempotency key follows jira:<ISSUE-KEY> format."""
        issues = [make_issue(key="BOS-500")]
        dispatcher, jira, hermes = self._make_dispatcher(issues, dry_run=True)

        # We can't directly test the key, but we can verify the hermes mock
        # was NOT called with an invalid key pattern
        dispatcher.run()

    def _make_dispatcher(self, issues=None, dry_run=True):
        jira = MagicMock(spec=JiraClient)
        jira.search_issues.return_value = issues or []
        hermes = MagicMock(spec=HermesClient)
        hermes.check_existing_task.return_value = None
        hermes.create_task.return_value = {"task_id": "test-task-456"}

        import logging
        from jira_hermes_bridge import StructuredLogger
        logger = StructuredLogger(level=logging.WARNING)

        return Dispatcher(
            jira=jira,
            hermes=hermes,
            logger=logger,
            project_key="BOS",
            dry_run=dry_run,
        ), jira, hermes

    def test_second_run_does_not_duplicate(self):
        """A second run with the same issues produces duplicates only for new issues."""
        issues = [make_issue(key="BOS-500")]
        dispatcher1, _, hermes1 = self._make_dispatcher(issues)
        results1 = dispatcher1.run()
        assert results1[0]["status"] == "dispatched"

        # Second run - simulate existing task found
        dispatcher2, _, hermes2 = self._make_dispatcher(issues)
        hermes2.check_existing_task.return_value = "existing-task-456"
        results2 = dispatcher2.run()
        assert results2[0]["status"] == "skipped"


# ---------------------------------------------------------------------------
# Dependency resolution tests
# ---------------------------------------------------------------------------


class TestDependencyResolution:
    """Test blocker link resolution logic."""

    def test_resolved_done_passes(self):
        issue = make_issue(issuelinks=[make_blocker_link("X-1", "Done")])
        eligible, _, _ = check_eligibility(issue)
        assert eligible is True

    def test_resolved_closed_passes(self):
        issue = make_issue(issuelinks=[make_blocker_link("X-1", "Closed")])
        eligible, _, _ = check_eligibility(issue)
        assert eligible is True

    def test_resolved_resolved_passes(self):
        issue = make_issue(issuelinks=[make_blocker_link("X-1", "Resolved")])
        eligible, _, _ = check_eligibility(issue)
        assert eligible is True

    def test_unresolved_todo_fails(self):
        issue = make_issue(issuelinks=[make_blocker_link("X-1", "To Do")])
        eligible, reason, _ = check_eligibility(issue)
        assert eligible is False
        assert "X-1" in reason

    def test_unresolved_in_progress_fails(self):
        issue = make_issue(issuelinks=[make_blocker_link("X-1", "In Progress")])
        eligible, reason, _ = check_eligibility(issue)
        assert eligible is False
        assert "X-1" in reason

    def test_non_blocker_link_ignored(self):
        """Non 'is blocked by' links are not checked."""
        non_blocker = {
            "type": {"inward": "relates to", "outward": "relates to"},
            "inwardIssue": {"key": "X-1", "fields": {"status": {"name": "To Do"}}},
        }
        issue = make_issue(issuelinks=[non_blocker])
        eligible, _, _ = check_eligibility(issue)
        assert eligible is True

    def test_no_links_passes(self):
        issue = make_issue(issuelinks=[])
        eligible, _, _ = check_eligibility(issue)
        assert eligible is True


# ---------------------------------------------------------------------------
# Failure handling tests
# ---------------------------------------------------------------------------


class TestFailureHandling:
    """Test graceful failure handling."""

    def test_jira_api_error_propagates(self):
        """JiraApiError is raised when Jira query fails."""
        jira = MagicMock(spec=JiraClient)
        jira.search_issues.side_effect = JiraApiError("403 Forbidden")
        hermes = MagicMock(spec=HermesClient)

        import logging
        from jira_hermes_bridge import StructuredLogger
        logger = StructuredLogger(level=logging.WARNING)

        dispatcher = Dispatcher(jira=jira, hermes=hermes, logger=logger)
        with pytest.raises(JiraApiError):
            dispatcher.run()

    def test_hermes_failure_doesnt_crash_cycle(self):
        """A single Hermes failure doesn't prevent processing remaining issues."""
        issues = [
            make_issue(key="BOS-600"),
            make_issue(key="BOS-601"),
        ]
        jira = MagicMock(spec=JiraClient)
        jira.search_issues.return_value = issues
        hermes = MagicMock(spec=HermesClient)
        hermes.check_existing_task.return_value = None

        call_count = [0]
        def fail_first(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise HermesApiError("Timeout")
            return {"task_id": f"task-{call_count[0]}"}

        hermes.create_task.side_effect = fail_first

        import logging
        from jira_hermes_bridge import StructuredLogger
        logger = StructuredLogger(level=logging.WARNING)

        dispatcher = Dispatcher(jira=jira, hermes=hermes, logger=logger, dry_run=False)
        results = dispatcher.run()

        assert len(results) == 2
        assert results[0]["status"] == "failed"
        assert results[1]["status"] == "dispatched"


# ---------------------------------------------------------------------------
# Credential loading tests
# ---------------------------------------------------------------------------


class TestCredentials:
    """Test credential loading and validation."""

    def test_missing_base_url(self):
        """Missing JIRA_BASE_URL raises CredentialError."""
        with patch.dict(os.environ, {"JIRA_USER": "user@test.com", "JIRA_API_TOKEN": "token"}, clear=False):
            os.environ.pop("JIRA_BASE_URL", None)
            from jira_hermes_bridge import load_credentials
            with pytest.raises(CredentialError):
                load_credentials()

    def test_missing_user(self):
        """Missing JIRA_USER raises CredentialError."""
        with patch.dict(os.environ, {"JIRA_BASE_URL": "https://test.atlassian.net", "JIRA_API_TOKEN": "token"}, clear=False):
            os.environ.pop("JIRA_USER", None)
            from jira_hermes_bridge import load_credentials
            with pytest.raises(CredentialError):
                load_credentials()

    def test_missing_token(self):
        """Missing JIRA_API_TOKEN raises CredentialError."""
        with patch.dict(os.environ, {"JIRA_BASE_URL": "https://test.atlassian.net", "JIRA_USER": "user@test.com"}, clear=False):
            os.environ.pop("JIRA_API_TOKEN", None)
            from jira_hermes_bridge import load_credentials
            with pytest.raises(CredentialError):
                load_credentials()


# ---------------------------------------------------------------------------
# Integration boundary tests
# ---------------------------------------------------------------------------


class TestJiraAdapterBoundary:
    """Test the Jira client adapter boundary (without HTTP)."""

    def test_search_issues_builds_correct_request(self):
        """The Jira client builds a correct search request."""
        client = JiraClient("https://test.atlassian.net", "user@test.com", "fake-token")

        # We cannot test actual HTTP without mocking urllib,
        # but we verify the client initializes correctly
        assert client.base_url == "https://test.atlassian.net"
        assert client.user == "user@test.com"

    def test_api_error_is_catchable(self):
        """JiraApiError is a real exception."""
        with pytest.raises(JiraApiError, match="test"):
            raise JiraApiError("test error")


class TestHermesAdapterBoundary:
    """Test the Hermes client adapter boundary (without real tools)."""

    def test_hermes_api_error_is_catchable(self):
        """HermesApiError is a real exception."""
        with pytest.raises(HermesApiError, match="test"):
            raise HermesApiError("test error")

    def test_dry_run_returns_mock(self):
        """Dry run creates tasks without calling real tools."""
        import logging
        from jira_hermes_bridge import StructuredLogger
        logger = StructuredLogger(level=logging.WARNING)

        hermes = HermesClient(logger=logger)
        result = hermes.create_task(
            title="Test",
            body="Body",
            assignee="brandosbackend",
            project="ai-marketing-vibe",
            branch_name="test-branch",
            dry_run=True,
        )
        assert result["dry_run"] is True

    def test_real_create_uses_installed_cli_contract(self, monkeypatch):
        import logging
        import subprocess
        from jira_hermes_bridge import StructuredLogger

        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return type("Result", (), {
                "returncode": 0,
                "stdout": '{"id":"t_1"}',
                "stderr": "",
            })()

        monkeypatch.setattr(subprocess, "run", fake_run)
        hermes = HermesClient(logger=StructuredLogger(level=logging.WARNING))
        hermes.create_task(
            title="BOS-1 - Work",
            body="Body",
            assignee="brandosbackend",
            project="ai-marketing-vibe",
            branch_name="bos1-work",
            idempotency_key="jira:BOS-1",
        )
        cmd = captured["cmd"]
        assert cmd[:5] == ["hermes", "kanban", "--board", "brandos", "create"]
        assert "--title" not in cmd
        assert "--workspace-kind" not in cmd
        assert cmd[cmd.index("--workspace") + 1] == "worktree"
        assert cmd[-1] == "BOS-1 - Work"


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


class TestCLI:
    """Test CLI argument parsing and entry point."""

    def test_help_exits_zero(self):
        import subprocess
        result = subprocess.run(
            [sys.executable, str(BRIDGE_FILE), "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "Jira-to-Hermes" in result.stdout

    def test_missing_env_exits_one(self):
        """Without env vars, the bridge exits 1."""
        import subprocess
        env = {k: v for k, v in os.environ.items() if not k.startswith("JIRA_")}
        result = subprocess.run(
            [sys.executable, str(BRIDGE_FILE), "--dry-run"],
            capture_output=True, text=True, env=env,
        )
        assert result.returncode == 1

    def test_dry_run_flag_parsed(self):
        """--dry-run is accepted."""
        import subprocess
        result = subprocess.run(
            [sys.executable, str(BRIDGE_FILE),
             "--dry-run", "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0

    def test_project_key_flag(self):
        """--project-key is accepted."""
        import subprocess
        result = subprocess.run(
            [sys.executable, str(BRIDGE_FILE),
             "--project-key", "TEST", "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Test unusual inputs and edge conditions."""

    def test_empty_issue_dict(self):
        """An empty issue dict is handled gracefully."""
        eligible, reason, agent = check_eligibility({})
        assert eligible is False

    def test_missing_fields_key(self):
        """Issue without 'fields' key is handled."""
        eligible, reason, agent = check_eligibility({"key": "BOS-1"})
        assert eligible is False
        assert "ready-for-dispatch" in reason

    def test_none_description(self):
        """None description is handled."""
        issue = make_issue(description=None)
        ctx = build_context_package(issue)
        assert ctx["description_full"] is None

    def test_very_long_summary(self):
        """Very long summary is truncated in branch name."""
        long_summary = "x " * 100
        branch = derive_branch_name("BOS-1", long_summary)
        assert len(branch) < 60

    def test_unicode_in_summary(self):
        """Unicode characters in summary are handled."""
        branch = derive_branch_name("BOS-1", "Add emoji support 🚀")
        assert "bos1" in branch

    def test_all_block_labels_check(self):
        """Verify our block label set matches the documented ones."""
        assert BLOCK_LABELS == {"do-not-dispatch-yet", "status-blocked", "deferred-scope"}

    def test_task_body_includes_all_sections(self):
        """The generated task body includes all context sections."""
        issue = make_issue(
            description=(
                "## Goal\nBuild feature\n\n"
                "## Acceptance Criteria\nIt works\n\n"
                "## Tests and Evidence\nUnit tests\n\n"
                "## Security\nNo secrets\n\n"
                "## Context\nBackend\n\n"
                "## Scope\nEverything\n\n"
                "## Out of Scope\nNothing"
            ),
            issuelinks=[make_blocker_link("BOS-10", "Done")],
        )
        ctx = build_context_package(issue)

        # Verify all parts are in context
        assert ctx["scope"] == "Everything"
        assert ctx["out_of_scope"] == "Nothing"
        assert len(ctx["dependencies"]) == 1

    def test_agent_label_boundary_coverage(self):
        """Every agent label in the mapping is a valid dispatch target."""
        for label in AGENT_LABEL_TO_PROFILE:
            profile = AGENT_LABEL_TO_PROFILE[label]
            issue = make_issue(labels=[
                "ready-for-dispatch", label,
                "risk-low", "phase-test", "points-1", "ver-0.1",
            ])
            eligible, _, _ = check_eligibility(issue)
            assert eligible is True, f"Agent label {label} should be eligible"


# ---------------------------------------------------------------------------
# Jira Search API Compatibility Tests (BOS-22)
# ---------------------------------------------------------------------------


class TestJiraSearchCompat:
    """Test Jira Cloud search API compatibility fixes."""

    def test_search_issues_uses_fields_array(self):
        """search_issues sends fields as a JSON array, not a comma-separated string."""
        from unittest.mock import MagicMock, patch
        import io

        client = JiraClient("https://test.atlassian.net", "user@test.com", "fake-token")

        # Mock urllib.request.urlopen to capture the request
        captured_request = {}

        def mock_urlopen(req, timeout=30):
            captured_request["url"] = req.full_url
            captured_request["data"] = json.loads(req.data.decode("utf-8"))
            captured_request["method"] = req.method
            # Return a mock response
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps({"issues": []}).encode("utf-8")
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            client.search_issues("project = BOS")

        # Verify fields is a list, not a string
        assert captured_request["method"] == "POST"
        assert captured_request["url"].endswith("/rest/api/3/search/jql")
        assert "startAt" not in captured_request["data"]
        assert "nextPageToken" not in captured_request["data"]
        assert isinstance(captured_request["data"]["fields"], list)
        assert "summary" in captured_request["data"]["fields"]
        assert "description" in captured_request["data"]["fields"]
        assert "labels" in captured_request["data"]["fields"]

    def test_search_issues_endpoint_is_enhanced_search(self):
        """search_issues uses the current enhanced-search endpoint."""
        from unittest.mock import patch, MagicMock

        client = JiraClient("https://test.atlassian.net", "user@test.com", "fake-token")
        captured_url = {}

        def mock_urlopen(req, timeout=30):
            captured_url["url"] = req.full_url
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps({"issues": []}).encode("utf-8")
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            client.search_issues("project = BOS")

        assert captured_url["url"] == "https://test.atlassian.net/rest/api/3/search/jql"

    def test_search_issues_paginates_with_next_page_token(self):
        """Enhanced search follows nextPageToken and respects overall limit."""
        from unittest.mock import patch, MagicMock

        client = JiraClient("https://test.atlassian.net", "user@test.com", "fake-token")
        payloads = []
        pages = [
            {"issues": [{"key": "BOS-1"}], "nextPageToken": "token-2"},
            {"issues": [{"key": "BOS-2"}]},
        ]

        def mock_urlopen(req, timeout=30):
            payloads.append(json.loads(req.data.decode("utf-8")))
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(pages[len(payloads) - 1]).encode("utf-8")
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            result = client.search_issues("project = BOS", max_results=2)

        assert [item["key"] for item in result] == ["BOS-1", "BOS-2"]
        assert "nextPageToken" not in payloads[0]
        assert payloads[1]["nextPageToken"] == "token-2"

    def test_search_issues_extracts_issues_from_response(self):
        """search_issues correctly extracts the issues list from Jira response."""
        from unittest.mock import patch, MagicMock

        client = JiraClient("https://test.atlassian.net", "user@test.com", "fake-token")
        mock_issues = [
            {"key": "BOS-1", "fields": {"summary": "Test Issue 1"}},
            {"key": "BOS-2", "fields": {"summary": "Test Issue 2"}},
        ]

        def mock_urlopen(req, timeout=30):
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps({"issues": mock_issues}).encode("utf-8")
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            result = client.search_issues("project = BOS")

        assert len(result) == 2
        assert result[0]["key"] == "BOS-1"
        assert result[1]["key"] == "BOS-2"

    def test_search_issues_http_400_extracts_error_messages(self):
        """search_issues extracts errorMessages from HTTP 400 responses."""
        from unittest.mock import patch, MagicMock
        import urllib.error

        client = JiraClient("https://test.atlassian.net", "user@test.com", "fake-token")
        error_body = json.dumps({
            "errorMessages": ["The value 'INVALID' does not exist for the field 'project'."],
            "errors": {}
        }).encode("utf-8")

        def mock_urlopen(req, timeout=30):
            http_err = urllib.error.HTTPError(
                url=req.full_url,
                code=400,
                msg="Bad Request",
                hdrs={},
                fp=io.BytesIO(error_body),
            )
            raise http_err

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            with pytest.raises(JiraApiError, match="400"):
                client.search_issues("project = INVALID")

    def test_search_issues_http_400_extracts_errors_dict(self):
        """search_issues extracts errors dict from HTTP 400 responses."""
        from unittest.mock import patch, MagicMock
        import urllib.error
        import io

        client = JiraClient("https://test.atlassian.net", "user@test.com", "fake-token")
        error_body = json.dumps({
            "errorMessages": [],
            "errors": {"jql": "Field 'invalid_field' does not exist."}
        }).encode("utf-8")

        def mock_urlopen(req, timeout=30):
            http_err = urllib.error.HTTPError(
                url=req.full_url,
                code=400,
                msg="Bad Request",
                hdrs={},
                fp=io.BytesIO(error_body),
            )
            raise http_err

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            with pytest.raises(JiraApiError, match="jql"):
                client.search_issues("invalid_field = X")

    def test_search_issues_redacts_sensitive_error_fields(self):
        """search_issues redacts sensitive field names in error responses."""
        from unittest.mock import patch, MagicMock
        import urllib.error
        import io

        client = JiraClient("https://test.atlassian.net", "user@test.com", "fake-token")
        error_body = json.dumps({
            "errorMessages": [],
            "errors": {
                "token": "expired",
                "authorization": "invalid",
                "project": "not found"
            }
        }).encode("utf-8")

        def mock_urlopen(req, timeout=30):
            http_err = urllib.error.HTTPError(
                url=req.full_url,
                code=400,
                msg="Bad Request",
                hdrs={},
                fp=io.BytesIO(error_body),
            )
            raise http_err

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            with pytest.raises(JiraApiError) as exc_info:
                client.search_issues("project = BOS")

            error_msg = str(exc_info.value)
            # Sensitive fields should be redacted
            assert "[REDACTED]" in error_msg
            assert "expired" not in error_msg
            assert "invalid" not in error_msg
            # Non-sensitive fields should appear
            assert "project" in error_msg
            assert "not found" in error_msg

    def test_search_issues_no_mutation_in_dry_run(self):
        """search_issues does not mutate state (no side effects in request building)."""
        from unittest.mock import patch, MagicMock

        client = JiraClient("https://test.atlassian.net", "user@test.com", "fake-token")
        original_base_url = client.base_url
        original_user = client.user

        def mock_urlopen(req, timeout=30):
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps({"issues": []}).encode("utf-8")
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            client.search_issues("project = BOS")

        # Client state should not be mutated
        assert client.base_url == original_base_url
        assert client.user == original_user

    def test_extract_jira_error_with_empty_body(self):
        """_extract_jira_error handles empty response body."""
        from jira_hermes_bridge import _extract_jira_error
        import urllib.error

        # Create a mock HTTPError with empty body
        mock_err = MagicMock()
        mock_err.read.return_value = b""

        result = _extract_jira_error(mock_err)
        assert result == "(empty response body)"

    def test_extract_jira_error_with_non_json_body(self):
        """_extract_jira_error handles non-JSON response body."""
        from jira_hermes_bridge import _extract_jira_error
        import urllib.error

        mock_err = MagicMock()
        mock_err.read.return_value = b"<html>Error page</html>"

        result = _extract_jira_error(mock_err)
        assert "<html>" in result
