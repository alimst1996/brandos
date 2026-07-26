#!/usr/bin/env python3
"""
Tests for the Definition of Readiness checker.

Run: python -m pytest tests/test_readiness.py -v
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Add scripts dir to path so we can import the validator
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from check_readiness import validate_issue, _extract_text_from_adf

FIXTURES = Path(__file__).parent / "fixtures"


# --- Unit tests (imported validator) ------------------------------------------

class TestPassingIssue:
    def setup_method(self):
        with open(FIXTURES / "ready_issue.json") as f:
            self.result = validate_issue(json.load(f))

    def test_overall_ready(self):
        assert self.result["ready"] is True

    def test_no_block_labels(self):
        c = next(c for c in self.result["checks"] if c["name"] == "no_block_labels")
        assert c["passed"] is True

    def test_description_structure(self):
        c = next(c for c in self.result["checks"] if c["name"] == "description_structure")
        assert c["passed"] is True

    def test_acceptance_criteria(self):
        c = next(c for c in self.result["checks"] if c["name"] == "acceptance_criteria")
        assert c["passed"] is True

    def test_dependency_links(self):
        c = next(c for c in self.result["checks"] if c["name"] == "dependency_links")
        assert c["passed"] is True

    def test_required_labels(self):
        c = next(c for c in self.result["checks"] if c["name"] == "required_labels")
        assert c["passed"] is True

    def test_human_approval(self):
        c = next(c for c in self.result["checks"] if c["name"] == "human_approval")
        assert c["passed"] is True

    def test_ready_for_dispatch(self):
        c = next(c for c in self.result["checks"] if c["name"] == "ready_for_dispatch")
        assert c["passed"] is True

    def test_tests_evidence(self):
        c = next(c for c in self.result["checks"] if c["name"] == "tests_evidence")
        assert c["passed"] is True

    def test_security_privacy(self):
        c = next(c for c in self.result["checks"] if c["name"] == "security_privacy")
        assert c["passed"] is True

    def test_repository_context(self):
        c = next(c for c in self.result["checks"] if c["name"] == "repository_context")
        assert c["passed"] is True


class TestIncompleteIssue:
    def setup_method(self):
        with open(FIXTURES / "not_ready_issue.json") as f:
            self.result = validate_issue(json.load(f))

    def test_overall_not_ready(self):
        assert self.result["ready"] is False

    def test_block_labels_present(self):
        c = next(c for c in self.result["checks"] if c["name"] == "no_block_labels")
        assert c["passed"] is False
        assert "do-not-dispatch-yet" in c["detail"]

    def test_description_structure_fails(self):
        c = next(c for c in self.result["checks"] if c["name"] == "description_structure")
        assert c["passed"] is False

    def test_acceptance_criteria_fails(self):
        c = next(c for c in self.result["checks"] if c["name"] == "acceptance_criteria")
        assert c["passed"] is False

    def test_dependency_links_fails(self):
        c = next(c for c in self.result["checks"] if c["name"] == "dependency_links")
        assert c["passed"] is False
        assert "EXAMPLE-100" in c["detail"]

    def test_required_labels_missing(self):
        c = next(c for c in self.result["checks"] if c["name"] == "required_labels")
        assert c["passed"] is False

    def test_ready_for_dispatch_missing(self):
        c = next(c for c in self.result["checks"] if c["name"] == "ready_for_dispatch")
        assert c["passed"] is False

    def test_human_approval_fails(self):
        c = next(c for c in self.result["checks"] if c["name"] == "human_approval")
        assert c["passed"] is False

    def test_tests_evidence_fails(self):
        c = next(c for c in self.result["checks"] if c["name"] == "tests_evidence")
        assert c["passed"] is False

    def test_security_privacy_passes_via_risk_high(self):
        """risk-high label alone satisfies security/privacy check."""
        c = next(c for c in self.result["checks"] if c["name"] == "security_privacy")
        assert c["passed"] is True

    def test_repository_context_fails(self):
        c = next(c for c in self.result["checks"] if c["name"] == "repository_context")
        assert c["passed"] is False


# --- CLI integration test -----------------------------------------------------

class TestCLI:
    def test_ready_exits_zero(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_readiness.py"),
             str(FIXTURES / "ready_issue.json")],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "READY" in result.stdout
        assert "NOT READY" not in result.stdout

    def test_not_ready_exits_one(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_readiness.py"),
             str(FIXTURES / "not_ready_issue.json")],
            capture_output=True, text=True,
        )
        assert result.returncode == 1
        assert "NOT READY" in result.stdout

    def test_inline_flag(self):
        with open(FIXTURES / "ready_issue.json") as f:
            payload = json.dumps(json.load(f))
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_readiness.py"),
             "--inline", payload],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "READY" in result.stdout

    def test_no_args_exits_two(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_readiness.py")],
            capture_output=True, text=True,
        )
        assert result.returncode == 2
        assert "Usage" in result.stdout

    def test_missing_file_exits_error(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_readiness.py"),
             "/nonexistent/path.json"],
            capture_output=True, text=True,
        )
        assert result.returncode != 0

    def test_malformed_json_exits_error(self):
        import tempfile, os
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{not valid json")
            tmp = f.name
        try:
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "check_readiness.py"), tmp],
                capture_output=True, text=True,
            )
            assert result.returncode != 0
        finally:
            os.unlink(tmp)


# --- Edge cases ---------------------------------------------------------------

class TestEdgeCases:
    def test_empty_description(self):
        issue = {"fields": {"labels": ["ready-for-dispatch", "role-dev", "review-by-agent-quality",
                                       "risk-low", "phase-test", "points-1", "ver-0.1"],
                            "description": "", "issuelinks": []}}
        result = validate_issue(issue)
        assert result["ready"] is False

    def test_description_text_only_no_headings(self):
        issue = {"fields": {"labels": ["ready-for-dispatch", "role-dev", "review-by-agent-quality",
                                       "risk-low", "phase-test", "points-1", "ver-0.1"],
                            "description": "## Acceptance Criteria\nDo stuff\n\n## Goal\nGoal here",
                            "issuelinks": []}}
        result = validate_issue(issue)
        desc_check = next(c for c in result["checks"] if c["name"] == "description_structure")
        assert desc_check["passed"] is True

    def test_resolved_blocker_passes(self):
        issue = {"fields": {
            "labels": ["ready-for-dispatch", "role-dev", "review-by-agent-quality",
                       "risk-low", "phase-test", "points-1", "ver-0.1"],
            "description": "## Goal\nGoal\n## Acceptance Criteria\nAC",
            "issuelinks": [{
                "type": {"inward": "is blocked by", "outward": "blocks"},
                "inwardIssue": {"key": "X-1", "fields": {"status": {"name": "Done"}}}
            }]
        }}
        result = validate_issue(issue)
        dep_check = next(c for c in result["checks"] if c["name"] == "dependency_links")
        assert dep_check["passed"] is True

    def test_risk_high_without_human_approval(self):
        issue = {"fields": {
            "labels": ["ready-for-dispatch", "role-dev", "review-by-agent-quality",
                       "risk-high", "phase-test", "points-1", "ver-0.1-foundation"],
            "description": "## Goal\nGoal\n## Acceptance Criteria\nAC",
            "issuelinks": []
        }}
        result = validate_issue(issue)
        ha_check = next(c for c in result["checks"] if c["name"] == "human_approval")
        assert ha_check["passed"] is False

    def test_pre_v1_low_risk_without_human_approval(self):
        """Pre-1.0 + risk-low without human-approval-required should fail."""
        issue = {"fields": {
            "labels": ["ready-for-dispatch", "role-dev", "review-by-agent-quality",
                       "risk-low", "phase-test", "points-1", "ver-0.1-foundation"],
            "description": "## Goal\nGoal\n## Acceptance Criteria\nAC\n"
                           "## Tests and Evidence\nUnit tests\n"
                           "## Security\nN/A\n"
                           "## Context\nFrontend module",
            "issuelinks": []
        }}
        result = validate_issue(issue)
        ha_check = next(c for c in result["checks"] if c["name"] == "human_approval")
        assert ha_check["passed"] is False
        assert "Pre-1.0" in ha_check["detail"]

    def test_v1_risk_low_without_human_approval_passes(self):
        """v1.0+ risk-low does NOT require human-approval-required."""
        issue = {"fields": {
            "labels": ["ready-for-dispatch", "role-dev", "review-by-agent-quality",
                       "risk-low", "phase-test", "points-1", "ver-1.0"],
            "description": "## Goal\nGoal\n## Acceptance Criteria\nAC\n"
                           "## Tests and Evidence\nUnit tests\n"
                           "## Security\nN/A\n"
                           "## Context\nFrontend module",
            "issuelinks": []
        }}
        result = validate_issue(issue)
        ha_check = next(c for c in result["checks"] if c["name"] == "human_approval")
        assert ha_check["passed"] is True


# --- ADF extraction tests -----------------------------------------------------

class TestADFExtraction:
    def test_adf_dict_description_passes(self):
        """A dict (ADF) description with text+headings should pass structure check."""
        adf_desc = {
            "type": "doc",
            "content": [
                {"type": "heading", "attrs": {"level": 2}, "content": [
                    {"type": "text", "text": "Goal"}
                ]},
                {"type": "paragraph", "content": [
                    {"type": "text", "text": "Build the feature"}
                ]},
                {"type": "heading", "attrs": {"level": 2}, "content": [
                    {"type": "text", "text": "Acceptance Criteria"}
                ]},
                {"type": "paragraph", "content": [
                    {"type": "text", "text": "Feature works correctly"}
                ]},
                {"type": "heading", "attrs": {"level": 2}, "content": [
                    {"type": "text", "text": "Tests and Evidence"}
                ]},
                {"type": "paragraph", "content": [
                    {"type": "text", "text": "Unit and integration tests"}
                ]},
                {"type": "heading", "attrs": {"level": 2}, "content": [
                    {"type": "text", "text": "Security"}
                ]},
                {"type": "paragraph", "content": [
                    {"type": "text", "text": "No PII exposure"}
                ]},
                {"type": "heading", "attrs": {"level": 2}, "content": [
                    {"type": "text", "text": "Context"}
                ]},
                {"type": "paragraph", "content": [
                    {"type": "text", "text": "Frontend API service"}
                ]}
            ]
        }
        issue = {"fields": {
            "labels": ["ready-for-dispatch", "role-dev", "review-by-agent-quality",
                       "risk-low", "phase-test", "points-1", "ver-0.1",
                       "human-approval-required"],
            "description": adf_desc,
            "issuelinks": []
        }}
        result = validate_issue(issue)
        desc_check = next(c for c in result["checks"] if c["name"] == "description_structure")
        assert desc_check["passed"] is True
        ac_check = next(c for c in result["checks"] if c["name"] == "acceptance_criteria")
        assert ac_check["passed"] is True
        te_check = next(c for c in result["checks"] if c["name"] == "tests_evidence")
        assert te_check["passed"] is True
        sp_check = next(c for c in result["checks"] if c["name"] == "security_privacy")
        assert sp_check["passed"] is True
        rc_check = next(c for c in result["checks"] if c["name"] == "repository_context")
        assert rc_check["passed"] is True

    def test_adf_text_extraction(self):
        adf = {
            "type": "doc",
            "content": [
                {"type": "heading", "attrs": {"level": 2}, "content": [
                    {"type": "text", "text": "Title"}
                ]},
                {"type": "paragraph", "content": [
                    {"type": "text", "text": "Body text"}
                ]}
            ]
        }
        result = _extract_text_from_adf(adf)
        assert "Title" in result
        assert "Body text" in result
        assert "##" in result
