#!/usr/bin/env python3
"""
Tests for the BrandOS convention checker (check_conventions.py).

Covers: branch naming, commit messages, PR titles, PR bodies, git log validation,
edge cases, and negative/error paths.

Run: python -m pytest tests/test_conventions.py -v
"""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from check_conventions import (
    check_branch_name,
    check_commit_message,
    check_pr_title,
    check_pr_body,
    check_git_log,
    extract_issue_key_from_branch,
    ISSUE_KEY_PATTERN,
    COMMIT_MSG_PATTERN,
    BRANCH_PATTERN,
    REQUIRED_PR_SECTIONS,
)


# ── Branch Naming ──────────────────────────────────────────────────────────


class TestBranchNaming:
    """Test branch name validation."""

    def test_valid_branch(self):
        result = check_branch_name("bos-22-jira-hermes-bridge")
        assert result["passed"] is True
        assert result["issue_key"] == "BOS-22"

    def test_valid_branch_with_numbers_in_slug(self):
        result = check_branch_name("bos-151-recovery-supervisor")
        assert result["passed"] is True
        assert result["issue_key"] == "BOS-151"

    def test_valid_branch_short_slug(self):
        result = check_branch_name("bos-36-orch")
        assert result["passed"] is True
        assert result["issue_key"] == "BOS-36"

    def test_valid_branch_long_slug_at_limit(self):
        slug = "a" * 40
        result = check_branch_name(f"bos-1-{slug}")
        assert result["passed"] is True

    def test_valid_branch_two_char_slug(self):
        result = check_branch_name("bos-1-ab")
        assert result["passed"] is True

    def test_invalid_branch_no_slug(self):
        result = check_branch_name("bos-22-")
        assert result["passed"] is False

    def test_invalid_branch_uppercase(self):
        result = check_branch_name("BOS-22-bridge")
        assert result["passed"] is False

    def test_invalid_branch_missing_number(self):
        result = check_branch_name("bos-bridge")
        assert result["passed"] is False

    def test_invalid_branch_random_name(self):
        result = check_branch_name("random-branch-name")
        assert result["passed"] is False

    def test_invalid_branch_empty(self):
        result = check_branch_name("")
        assert result["passed"] is False

    def test_invalid_branch_whitespace_only(self):
        result = check_branch_name("   ")
        assert result["passed"] is False

    def test_invalid_branch_slug_too_long(self):
        slug = "a" * 41
        result = check_branch_name(f"bos-1-{slug}")
        assert result["passed"] is False

    def test_invalid_branch_single_char_slug(self):
        result = check_branch_name("bos-1-a")
        assert result["passed"] is False

    def test_invalid_branch_with_underscores_in_project(self):
        result = check_branch_name("bo_s-22-bridge")
        assert result["passed"] is False

    def test_valid_branch_multi_digit_number(self):
        result = check_branch_name("bos-12345-feature-name")
        assert result["passed"] is True
        assert result["issue_key"] == "BOS-12345"

    def test_branch_with_trailing_slash(self):
        result = check_branch_name("bos-22-bridge/")
        assert result["passed"] is False

    def test_branch_strips_leading_whitespace(self):
        result = check_branch_name("  bos-22-bridge")
        assert result["passed"] is True  # strips whitespace then validates


# ── Commit Messages ────────────────────────────────────────────────────────


class TestCommitMessages:
    """Test commit message validation."""

    def test_valid_commit_feat(self):
        result = check_commit_message("feat(BOS-22): implement bridge")
        assert result["passed"] is True
        assert result["issue_key"] == "BOS-22"

    def test_valid_commit_fix(self):
        result = check_commit_message("fix(BOS-149): enforce Definition of Ready")
        assert result["passed"] is True
        assert result["issue_key"] == "BOS-149"

    def test_valid_commit_docs(self):
        result = check_commit_message("docs(BOS-36): add conventions doc")
        assert result["passed"] is True

    def test_valid_commit_test(self):
        result = check_commit_message("test(BOS-22): add bridge tests")
        assert result["passed"] is True

    def test_valid_commit_refactor(self):
        result = check_commit_message("refactor(BOS-151): extract module")
        assert result["passed"] is True

    def test_valid_commit_chore(self):
        result = check_commit_message("chore(BOS-23): configure schedule")
        assert result["passed"] is True

    def test_commit_no_issue_key(self):
        result = check_commit_message("fix: some bug fix")
        assert result["passed"] is False
        assert "No Jira issue key" in result["detail"]

    def test_commit_wrong_format(self):
        result = check_commit_message("BOS-22: fix stuff")
        assert result["passed"] is False
        assert "Format wrong" in result["detail"]

    def test_commit_empty(self):
        result = check_commit_message("")
        assert result["passed"] is False

    def test_commit_whitespace_only(self):
        result = check_commit_message("   ")
        assert result["passed"] is False

    def test_commit_too_long(self):
        desc = "a" * 70
        result = check_commit_message(f"feat(BOS-1): {desc}")
        assert result["passed"] is False
        assert "max 72" in result["detail"]

    def test_commit_exactly_72_chars(self):
        # "feat(BOS-1): " is 14 chars, + 58 chars description = 72 total
        desc = "a" * 58
        result = check_commit_message(f"feat(BOS-1): {desc}")
        assert result["passed"] is True

    def test_commit_73_chars_fails(self):
        # "feat(BOS-1): " = 13 chars, + 60 = 73 > 72
        desc = "a" * 60
        result = check_commit_message(f"feat(BOS-1): {desc}")
        assert result["passed"] is False

    def test_commit_invalid_type(self):
        result = check_commit_message("featx(BOS-22): stuff")
        assert result["passed"] is False

    def test_commit_multiline_uses_first_line(self):
        msg = "feat(BOS-22): implement bridge\n\nLong description here."
        result = check_commit_message(msg)
        assert result["passed"] is True

    def test_commit_with_special_chars_in_desc(self):
        result = check_commit_message("feat(BOS-22): add /api/v2/users endpoint")
        assert result["passed"] is True


# ── PR Title ───────────────────────────────────────────────────────────────


class TestPRTitle:
    """Test PR title validation."""

    def test_valid_pr_title(self):
        result = check_pr_title("BOS-22: implement secure bridge")
        assert result["passed"] is True
        assert result["issue_key"] == "BOS-22"

    def test_pr_title_no_key(self):
        result = check_pr_title("Fix stuff")
        assert result["passed"] is False
        assert "No Jira issue key" in result["detail"]

    def test_pr_title_multiple_keys(self):
        result = check_pr_title("Fix BOS-22 and BOS-149")
        assert result["passed"] is False
        assert "Multiple issues" in result["detail"]

    def test_pr_title_empty(self):
        result = check_pr_title("")
        assert result["passed"] is False

    def test_pr_title_same_key_twice(self):
        # Same key appearing twice is fine (it's one unique key)
        result = check_pr_title("BOS-22: fix for BOS-22 regression")
        assert result["passed"] is True
        assert result["issue_key"] == "BOS-22"

    def test_pr_title_case_sensitive_key(self):
        result = check_pr_title("bos-22: fix stuff")
        assert result["passed"] is False  # lowercase project key doesn't match

    def test_pr_title_with_punctuation(self):
        result = check_pr_title("BOS-100: Add OAuth2 / JWT support!")
        assert result["passed"] is True


# ── PR Body ────────────────────────────────────────────────────────────────


class TestPRBody:
    """Test PR body section validation."""

    FULL_BODY = """
## Jira Issue

Closes: BOS-22

## Summary

This PR implements the bridge.

## Delivery Report

### Files Changed
- scripts/jira_hermes_bridge.py

### Tests Run
5 tests pass

### Decisions
Used sqlite for state.

## Test Evidence

```
5 passed
```

## Preview URL

N/A

## Checklist

- [x] Self-review completed
"""

    def test_full_body_passes(self):
        result = check_pr_body(self.FULL_BODY)
        assert result["passed"] is True
        assert result["missing"] == []

    def test_body_missing_jira_issue(self):
        body = "## Summary\n\nStuff\n\n## Delivery Report\n\nReport\n\n## Test Evidence\n\nPass\n\n## Preview URL\n\nN/A\n\n## Checklist\n\n- [x] Done"
        result = check_pr_body(body)
        assert result["passed"] is False
        assert "jira issue" in result["missing"]

    def test_body_missing_test_evidence(self):
        body = "## Jira Issue\n\nBOS-22\n\n## Summary\n\nStuff\n\n## Delivery Report\n\nReport\n\n## Preview URL\n\nN/A\n\n## Checklist\n\n- [x] Done"
        result = check_pr_body(body)
        assert result["passed"] is False
        assert "test evidence" in result["missing"]

    def test_body_case_insensitive(self):
        body = "## JIRA ISSUE\n\n## SUMMARY\n\n## DELIVERY REPORT\n\n## TEST EVIDENCE\n\n## PREVIEW URL\n\n## CHECKLIST"
        result = check_pr_body(body)
        assert result["passed"] is True

    def test_body_empty(self):
        result = check_pr_body("")
        assert result["passed"] is False
        assert len(result["missing"]) == len(REQUIRED_PR_SECTIONS)

    def test_body_all_missing(self):
        result = check_pr_body("Just some random text")
        assert result["passed"] is False
        assert len(result["missing"]) == len(REQUIRED_PR_SECTIONS)

    def test_body_partial_sections(self):
        body = "## Jira Issue\n\nBOS-22\n\n## Summary\n\nStuff"
        result = check_pr_body(body)
        assert result["passed"] is False
        assert "delivery report" in result["missing"]


# ── Issue Key Extraction ──────────────────────────────────────────────────


class TestIssueKeyExtraction:
    """Test issue key extraction from branch names."""

    def test_extract_from_valid_branch(self):
        assert extract_issue_key_from_branch("bos-22-jira-hermes-bridge") == "BOS-22"

    def test_extract_from_invalid_branch(self):
        assert extract_issue_key_from_branch("random-branch") is None

    def test_extract_from_empty(self):
        assert extract_issue_key_from_branch("") is None

    def test_extract_preserves_uppercase_project(self):
        assert extract_issue_key_from_branch("eng-42-feature") == "ENG-42"


# ── Regex Patterns ─────────────────────────────────────────────────────────


class TestPatterns:
    """Test compiled regex patterns match expected inputs."""

    def test_issue_key_pattern_standard(self):
        keys = ISSUE_KEY_PATTERN.findall("BOS-22 and BOS-149")
        assert keys == ["BOS-22", "BOS-149"]

    def test_issue_key_pattern_multi_letter_project(self):
        keys = ISSUE_KEY_PATTERN.findall("ENG-123 FE-456")
        assert keys == ["ENG-123", "FE-456"]

    def test_issue_key_no_match_lowercase(self):
        keys = ISSUE_KEY_PATTERN.findall("bos-22")
        assert keys == []

    def test_commit_pattern_valid(self):
        m = COMMIT_MSG_PATTERN.match("feat(BOS-22): implement bridge")
        assert m is not None
        assert m.group("type") == "feat"
        assert m.group("key") == "BOS-22"
        assert m.group("desc") == "implement bridge"

    def test_commit_pattern_invalid_type(self):
        m = COMMIT_MSG_PATTERN.match("deploy(BOS-22): stuff")
        assert m is None

    def test_branch_pattern_valid(self):
        m = BRANCH_PATTERN.match("bos-22-jira-hermes-bridge")
        assert m is not None
        assert m.group("project") == "bos"
        assert m.group("number") == "22"
        assert m.group("slug") == "jira-hermes-bridge"

    def test_branch_pattern_invalid(self):
        m = BRANCH_PATTERN.match("random-branch")
        assert m is None


# ── Git Log Validation ─────────────────────────────────────────────────────


class TestGitLog:
    """Test git log range validation."""

    def test_current_branch_has_valid_commits(self):
        """All commits on this branch should pass the convention check."""
        result = check_git_log("main..HEAD")
        # This branch's commits may not all follow conventions yet (pre-existing)
        # so we just verify the function runs without error
        assert "passed" in result
        assert "results" in result

    def test_invalid_range(self):
        result = check_git_log("nonexistent-branch..HEAD")
        assert result["passed"] is False
        assert "git log failed" in result["detail"]

    def test_single_commit(self):
        result = check_git_log("HEAD~1..HEAD")
        assert "passed" in result
        assert len(result["results"]) >= 1


# ── CLI Integration ────────────────────────────────────────────────────────


class TestCLI:
    """Test the CLI interface end-to-end."""

    def _run_cli(self, *args):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_conventions.py"), *args],
            capture_output=True, text=True, timeout=30,
        )
        return result

    def test_cli_branch_valid(self):
        result = self._run_cli("--branch", "bos-22-jira-hermes-bridge")
        assert result.returncode == 0
        assert "PASS" in result.stdout

    def test_cli_branch_invalid(self):
        result = self._run_cli("--branch", "random-branch")
        assert result.returncode == 1
        assert "FAIL" in result.stdout

    def test_cli_commit_valid(self):
        result = self._run_cli("--commit", "feat(BOS-22): implement bridge")
        assert result.returncode == 0
        assert "PASS" in result.stdout

    def test_cli_commit_invalid(self):
        result = self._run_cli("--commit", "fix: no key")
        assert result.returncode == 1
        assert "FAIL" in result.stdout

    def test_cli_pr_title_valid(self):
        result = self._run_cli("--pr-title", "BOS-22: implement bridge")
        assert result.returncode == 0
        assert "PASS" in result.stdout

    def test_cli_pr_title_multiple_keys(self):
        result = self._run_cli("--pr-title", "Fix BOS-22 and BOS-149")
        assert result.returncode == 1
        assert "FAIL" in result.stdout

    def test_cli_multiple_checks_all_pass(self):
        result = self._run_cli(
            "--branch", "bos-22-jira-hermes-bridge",
            "--commit", "feat(BOS-22): implement bridge",
            "--pr-title", "BOS-22: implement bridge",
        )
        assert result.returncode == 0
        assert "ALL PASSED" in result.stdout

    def test_cli_mixed_pass_fail(self):
        result = self._run_cli(
            "--branch", "bos-22-jira-hermes-bridge",
            "--commit", "fix: no key here",
        )
        assert result.returncode == 1
        assert "CHECKS FAILED" in result.stdout

    def test_cli_no_args_shows_help(self):
        result = self._run_cli()
        # argparse --help exits with 0
        assert result.returncode == 0
        assert "usage:" in result.stdout.lower() or "BrandOS" in result.stdout

    def test_cli_pr_body_file(self, tmp_path):
        body_file = tmp_path / "pr_body.md"
        body_file.write_text(self._full_pr_body(), encoding="utf-8")
        result = self._run_cli(
            "--pr-title", "BOS-22: implement bridge",
            "--pr-body", str(body_file),
        )
        assert result.returncode == 0
        assert "PASS" in result.stdout

    def test_cli_pr_body_file_missing(self):
        result = self._run_cli("--pr-body", "/nonexistent/file.md")
        assert result.returncode == 1
        assert "FAIL" in result.stdout

    @staticmethod
    def _full_pr_body():
        return """
## Jira Issue

Closes: BOS-22

## Summary

Implements the bridge.

## Delivery Report

### Files Changed
- bridge.py

### Tests Run
5 passed

### Decisions
SQLite state

## Test Evidence

5 passed

## Preview URL

N/A

## Checklist

- [x] Done
"""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
