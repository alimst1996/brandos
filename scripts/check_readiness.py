#!/usr/bin/env python3
"""
Definition of Readiness checker for BrandOS Jira issues.

Validates a Jira issue (as JSON) against the Definition of Ready.
Exit code 0 = ready, 1 = not ready. Prints a structured report.

Usage:
    python scripts/check_readiness.py <issue_json_file>
    python scripts/check_readiness.py --inline '{"fields": {...}}'
"""

import json
import sys
import re
from pathlib import Path
from typing import Any

# --- Label sets ---------------------------------------------------------------

BLOCK_LABELS = {"do-not-dispatch-yet", "status-blocked", "deferred-scope"}
REQUIRED_PREFIXES = {
    "role": r"^role-",
    "reviewer": r"^review-",
    "risk": r"^risk-",
    "phase": r"^phase-",
    "points": r"^points-",
    "version": r"^ver-",
}

# --- Checks -------------------------------------------------------------------

def check_no_block_labels(labels: list[str]) -> tuple[bool, str]:
    found = BLOCK_LABELS & set(labels)
    if found:
        return False, f"Block labels present: {', '.join(sorted(found))}"
    return True, "No block labels"


def check_ready_for_dispatch(labels: list[str]) -> tuple[bool, str]:
    if "ready-for-dispatch" in labels:
        return True, "ready-for-dispatch label present"
    return False, "ready-for-dispatch label missing"


def check_description_structure(desc: str | None) -> tuple[bool, str]:
    if not desc or not desc.strip():
        return False, "Description is empty"
    has_sections = bool(re.search(r"#{1,3}\s+\w", desc))
    return (True, "Description has structured sections") if has_sections else (False, "Description has no markdown headings")


def check_acceptance_criteria(desc: str | None) -> tuple[bool, str]:
    if not desc:
        return False, "No description to check"
    pattern = r"acceptance\s+criteria"
    if re.search(pattern, desc, re.IGNORECASE):
        return True, "Acceptance criteria section found"
    return False, "No 'Acceptance Criteria' section in description"


def check_dependency_links(issuelinks: list[dict]) -> tuple[bool, str]:
    blocking = [
        lk for lk in issuelinks
        if lk.get("type", {}).get("inward") == "is blocked by"
    ]
    if not blocking:
        return True, "No unresolved block links"
    statuses = []
    for lk in blocking:
        inward = lk.get("inwardIssue", {})
        status_name = inward.get("fields", {}).get("status", {}).get("name", "Unknown")
        statuses.append(f"{inward.get('key','?')}={status_name}")
    unresolved = [
        lk for lk in blocking
        if lk.get("inwardIssue", {}).get("fields", {}).get("status", {}).get("name", "").lower()
        not in ("done", "resolved", "closed")
    ]
    if unresolved:
        keys = [lk["inwardIssue"]["key"] for lk in unresolved]
        return False, f"Unresolved blockers: {', '.join(keys)}"
    return True, f"All block links resolved ({', '.join(statuses)})"


def check_required_labels(labels: list[str]) -> tuple[bool, list[str]]:
    missing = []
    present = []
    for category, pattern in REQUIRED_PREFIXES.items():
        if any(re.match(pattern, lbl) for lbl in labels):
            present.append(category)
        else:
            missing.append(category)
    return len(missing) == 0, missing


def check_human_approval(labels: list[str], version_labels: list[str]) -> tuple[bool, str]:
    has_ha = "human-approval-required" in labels
    has_risk_high = "risk-high" in labels
    pre_v1 = any(not re.match(r"^ver-1", v) for v in version_labels) if version_labels else True

    if (pre_v1 or has_risk_high) and not has_ha:
        return False, "Pre-1.0 or high-risk issue needs human-approval-required"
    return True, "Human approval requirement satisfied"


def check_tests_evidence(desc: str | None) -> tuple[bool, str]:
    """Policy item 3: Required tests and evidence are specified."""
    if not desc:
        return False, "No description to check for tests/evidence"
    pattern = r"test|evidence|spec|verif|qa"
    if re.search(pattern, desc, re.IGNORECASE):
        return True, "Tests or evidence referenced in description"
    return False, "No tests or evidence referenced in description"


def check_security_privacy(desc: str | None, labels: list[str]) -> tuple[bool, str]:
    """Policy item 6: Security/privacy implications recorded."""
    if "risk-high" in labels:
        return True, "risk-high label triggers security review"
    if not desc:
        return False, "No description to check for security/privacy"
    pattern = r"security|privacy|auth|credential|pii|gdpr|encrypt|bcrypt|hash"
    if re.search(pattern, desc, re.IGNORECASE):
        return True, "Security/privacy implications found in description"
    return False, "No security/privacy implications recorded"


def check_repository_context(desc: str | None) -> tuple[bool, str]:
    """Policy item 8: Repository/module context identified."""
    if not desc:
        return False, "No description to check for repository context"
    pattern = r"repositor|module|component|repo|service|api|frontend|backend|library|package|plugin"
    if re.search(pattern, desc, re.IGNORECASE):
        return True, "Repository/module context found in description"
    return False, "No repository or module context identified"


# --- Main validator ------------------------------------------------------------

def validate_issue(issue: dict[str, Any]) -> dict:
    """Validate a Jira issue object against the Definition of Ready.

    Returns dict with keys:
        ready: bool
        checks: list of {name, passed, detail}
    """
    fields = issue.get("fields", {})
    labels: list[str] = fields.get("labels", [])
    description = fields.get("description", "")

    # Extract description text from ADF if needed
    if isinstance(description, dict):
        desc_text = _extract_text_from_adf(description)
    else:
        desc_text = description or ""

    issuelinks = fields.get("issuelinks", [])

    checks = []

    # 1. No block labels
    passed, detail = check_no_block_labels(labels)
    checks.append({"name": "no_block_labels", "passed": passed, "detail": detail})

    # 2. Description structure
    passed, detail = check_description_structure(desc_text)
    checks.append({"name": "description_structure", "passed": passed, "detail": detail})

    # 3. Acceptance criteria
    passed, detail = check_acceptance_criteria(desc_text)
    checks.append({"name": "acceptance_criteria", "passed": passed, "detail": detail})

    # 4. Dependency links resolved
    passed, detail = check_dependency_links(issuelinks)
    checks.append({"name": "dependency_links", "passed": passed, "detail": detail})

    # 5. Required labels
    passed, missing = check_required_labels(labels)
    detail = "All required label categories present" if passed else f"Missing categories: {', '.join(missing)}"
    checks.append({"name": "required_labels", "passed": passed, "detail": detail})

    # 6. Human approval
    version_labels = [l for l in labels if re.match(r"^ver-", l)]
    passed, detail = check_human_approval(labels, version_labels)
    checks.append({"name": "human_approval", "passed": passed, "detail": detail})

    # 7. ready-for-dispatch label
    passed, detail = check_ready_for_dispatch(labels)
    checks.append({"name": "ready_for_dispatch", "passed": passed, "detail": detail})

    # 8. Tests/evidence specified (policy item 3)
    passed, detail = check_tests_evidence(desc_text)
    checks.append({"name": "tests_evidence", "passed": passed, "detail": detail})

    # 9. Security/privacy recorded (policy item 6)
    passed, detail = check_security_privacy(desc_text, labels)
    checks.append({"name": "security_privacy", "passed": passed, "detail": detail})

    # 10. Repository/module context (policy item 8)
    passed, detail = check_repository_context(desc_text)
    checks.append({"name": "repository_context", "passed": passed, "detail": detail})

    all_passed = all(c["passed"] for c in checks)
    return {"ready": all_passed, "checks": checks}


def _extract_text_from_adf(adf: dict) -> str:
    """Best-effort extraction of plain text from Atlassian Document Format."""
    texts: list[str] = []
    def walk(obj):
        if isinstance(obj, dict):
            if obj.get("type") == "text":
                texts.append(obj.get("text", ""))
            if obj.get("type") == "heading":
                level = obj.get("attrs", {}).get("level", 1)
                texts.append("#" * level + " ")
            for child in obj.get("content", []):
                walk(child)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)
    walk(adf)
    return " ".join(texts)


# --- CLI entry point -----------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print("Usage: check_readiness.py <issue_json_file | --inline '{...}'>")
        sys.exit(2)

    if sys.argv[1] == "--inline":
        issue = json.loads(sys.argv[2])
    else:
        with open(sys.argv[1]) as f:
            issue = json.load(f)

    result = validate_issue(issue)

    print(f"{'READY' if result['ready'] else 'NOT READY'}")
    for c in result["checks"]:
        mark = "PASS" if c["passed"] else "FAIL"
        print(f"  [{mark}] {c['name']}: {c['detail']}")

    sys.exit(0 if result["ready"] else 1)


if __name__ == "__main__":
    main()