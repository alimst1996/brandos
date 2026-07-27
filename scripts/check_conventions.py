#!/usr/bin/env python3
"""
Convention checker for BrandOS branches, commits, and pull requests.

Validates that every branch, commit, and pull request carries a resolvable
Jira issue key and follows the documented conventions.

Usage:
    python scripts/check_conventions.py --branch "bos-22-jira-hermes-bridge"
    python scripts/check_conventions.py --commit "feat(BOS-22): implement bridge"
    python scripts/check_conventions.py --pr-title "BOS-22: implement bridge" --pr-body pr_body.md
    python scripts/check_conventions.py --git-log main..HEAD

Exit codes: 0 = all checks passed, 1 = one or more checks failed.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

ISSUE_KEY_PATTERN = re.compile(r"([A-Z][A-Z0-9]+-\d+)")
COMMIT_MSG_PATTERN = re.compile(
    r"^(?P<type>feat|fix|docs|test|refactor|chore)"
    r"\((?P<key>[A-Z][A-Z0-9]+-\d+)\):\s+"
    r"(?P<desc>.+)$"
)
BRANCH_PATTERN = re.compile(
    r"^(?P<project>[a-z][a-z0-9]*)-(?P<number>\d+)-(?P<slug>[a-z0-9][a-z0-9-]*)$"
)
REQUIRED_PR_SECTIONS = [
    "jira issue",
    "summary",
    "delivery report",
    "test evidence",
    "preview url",
    "checklist",
]


def check_branch_name(branch: str) -> dict:
    """Validate a branch name against convention."""
    branch = branch.strip()
    if not branch:
        return {"passed": False, "issue_key": None, "detail": "Branch name is empty"}

    match = BRANCH_PATTERN.match(branch)
    if not match:
        return {
            "passed": False,
            "issue_key": None,
            "detail": f"Branch '{branch}' does not match pattern '{{project}}-{{number}}-{{slug}}'",
        }

    project = match.group("project")
    number = match.group("number")
    issue_key = f"{project.upper()}-{number}"
    slug = match.group("slug")

    if len(slug) < 2:
        return {"passed": False, "issue_key": issue_key, "detail": f"Slug '{slug}' too short (min 2)"}
    if len(slug) > 40:
        return {"passed": False, "issue_key": issue_key, "detail": f"Slug '{slug}' exceeds 40 chars"}

    return {"passed": True, "issue_key": issue_key, "detail": f"Branch valid: {issue_key}, slug '{slug}'"}


def check_commit_message(message: str) -> dict:
    """Validate a commit message against convention."""
    message = message.strip()
    if not message:
        return {"passed": False, "issue_key": None, "detail": "Commit message is empty"}

    first_line = message.split("\n")[0].strip()
    match = COMMIT_MSG_PATTERN.match(first_line)
    if not match:
        keys = ISSUE_KEY_PATTERN.findall(first_line)
        if not keys:
            return {"passed": False, "issue_key": None, "detail": f"No Jira issue key in: '{first_line}'"}
        return {
            "passed": False,
            "issue_key": keys[0],
            "detail": f"Format wrong. Found key {keys[0]} but expected '{{type}}({{KEY}}): {{desc}}'",
        }

    commit_type = match.group("type")
    issue_key = match.group("key")
    if len(first_line) > 72:
        return {"passed": False, "issue_key": issue_key, "detail": f"First line {len(first_line)} chars (max 72)"}

    return {"passed": True, "issue_key": issue_key, "detail": f"Commit valid: {commit_type}({issue_key})"}


def check_pr_title(title: str) -> dict:
    """Validate a PR title has exactly one Jira issue key."""
    title = title.strip()
    if not title:
        return {"passed": False, "issue_key": None, "detail": "PR title is empty"}

    keys = ISSUE_KEY_PATTERN.findall(title)
    if len(keys) == 0:
        return {"passed": False, "issue_key": None, "detail": f"No Jira issue key in: '{title}'"}

    unique_keys = sorted(set(keys))
    if len(unique_keys) > 1:
        return {
            "passed": False,
            "issue_key": None,
            "detail": f"Multiple issues: {', '.join(unique_keys)}. One PR = one issue.",
        }

    return {"passed": True, "issue_key": keys[0], "detail": f"PR title valid: {keys[0]}"}


def check_pr_body(body: str) -> dict:
    """Validate a PR body has all required template sections."""
    body_lower = body.lower()
    missing = [s for s in REQUIRED_PR_SECTIONS if s not in body_lower]
    if missing:
        return {"passed": False, "missing": missing, "detail": f"Missing sections: {', '.join(missing)}"}
    return {"passed": True, "missing": [], "detail": "All required PR body sections present"}


def extract_issue_key_from_branch(branch: str) -> str | None:
    """Extract the Jira issue key from a branch name."""
    match = BRANCH_PATTERN.match(branch.strip())
    if match:
        return f"{match.group('project').upper()}-{match.group('number')}"
    return None


def check_git_log(git_range: str) -> dict:
    """Validate all commits in a git range have valid issue keys."""
    try:
        result = subprocess.run(
            ["git", "log", "--format=%H %s", git_range],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return {"passed": False, "results": [], "detail": f"git log failed: {result.stderr.strip()}"}
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return {"passed": False, "results": [], "detail": f"git log error: {e}"}

    lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
    if not lines:
        return {"passed": True, "results": [], "detail": "No commits in range"}

    results = []
    all_passed = True
    for line in lines:
        parts = line.split(" ", 1)
        commit_hash = parts[0]
        message = parts[1] if len(parts) > 1 else ""
        check = check_commit_message(message)
        results.append({"commit": commit_hash[:8], "message": message, **check})
        if not check["passed"]:
            all_passed = False

    passed_count = sum(1 for r in results if r["passed"])
    return {"passed": all_passed, "results": results, "detail": f"{passed_count}/{len(results)} commits valid"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BrandOS convention checker")
    parser.add_argument("--branch", help="Validate a branch name")
    parser.add_argument("--commit", help="Validate a commit message")
    parser.add_argument("--pr-title", help="Validate a PR title")
    parser.add_argument("--pr-body", help="Path to PR body file")
    parser.add_argument("--git-log", help="Validate commits in range (e.g. main..HEAD)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    all_passed = True

    if args.branch:
        result = check_branch_name(args.branch)
        status = "PASS" if result["passed"] else "FAIL"
        print(f"  [{status}] branch: {result['detail']}")
        if not result["passed"]:
            all_passed = False

    if args.commit:
        result = check_commit_message(args.commit)
        status = "PASS" if result["passed"] else "FAIL"
        print(f"  [{status}] commit: {result['detail']}")
        if not result["passed"]:
            all_passed = False

    if args.pr_title:
        result = check_pr_title(args.pr_title)
        status = "PASS" if result["passed"] else "FAIL"
        print(f"  [{status}] pr-title: {result['detail']}")
        if not result["passed"]:
            all_passed = False

    if args.pr_body:
        body_path = Path(args.pr_body)
        if not body_path.exists():
            print(f"  [FAIL] pr-body: File not found: {args.pr_body}")
            all_passed = False
        else:
            body = body_path.read_text(encoding="utf-8")
            result = check_pr_body(body)
            status = "PASS" if result["passed"] else "FAIL"
            print(f"  [{status}] pr-body: {result['detail']}")
            if not result["passed"]:
                all_passed = False

    if args.git_log:
        result = check_git_log(args.git_log)
        status = "PASS" if result["passed"] else "FAIL"
        print(f"  [{status}] git-log: {result['detail']}")
        for r in result["results"]:
            mark = "PASS" if r["passed"] else "FAIL"
            print(f"    [{mark}] {r['commit']}: {r['message']}")
            if not r["passed"]:
                print(f"           {r['detail']}")
        if not result["passed"]:
            all_passed = False

    if not any([args.branch, args.commit, args.pr_title, args.pr_body, args.git_log]):
        parser = argparse.ArgumentParser(description="BrandOS convention checker")
        parser.parse_args(["--help"])
        return 2

    print()
    print("ALL PASSED" if all_passed else "CHECKS FAILED")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
