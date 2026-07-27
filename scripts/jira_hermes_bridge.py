#!/usr/bin/env python3
"""
Jira-to-Hermes task bridge for BrandOS.

Selects eligible BOS Jira issues, builds bounded context packages,
and dispatches them as Hermes Kanban tasks.

Usage:
    python scripts/jira_hermes_bridge.py [--dry-run] [--project-key BOS] [--limit 10]
    python scripts/jira_hermes_bridge.py --help

Environment variables:
    JIRA_BASE_URL      — Jira instance URL (e.g. https://brandos.atlassian.net)
    JIRA_USER          — Jira user email
    JIRA_API_TOKEN     — Jira API token (never logged)
    HERMES_KANBAN_DB   — Path to Hermes kanban SQLite DB (optional)

Credentials are read ONLY from environment or Hermes secret configuration.
Never commit tokens, chat IDs, emails, or local secret files.
"""

import argparse
import json
import logging
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BLOCK_LABELS = {"do-not-dispatch-yet", "status-blocked", "deferred-scope"}

AGENT_LABEL_TO_PROFILE: dict[str, str] = {
    "agent-backend": "brandosbackend",
    "agent-frontend": "brandosfrontend",
    "agent-intelligence": "brandosintelligence",
    "agent-social": "brandossocial",
    "agent-quality": "brandosquality",
    "agent-preview": "brandospreview",
    "agent-orchestrator": "brandosorchestrator",
}

HERMES_PROJECT = "ai-marketing-vibe"
DEFAULT_RUNTIME_SECONDS = 5400  # 90 minutes
DEFAULT_RETRY_LIMIT = 3
JIRA_TRANSITION_IN_PROGRESS = "In Progress"

# ---------------------------------------------------------------------------
# Structured logging with redaction
# ---------------------------------------------------------------------------


class RedactingFilter(logging.Filter):
    """Redacts sensitive values from log records."""

    REDACTED_PATTERNS = [
        # Authorization: Bearer <value> or Authorization: Basic <value>
        (re.compile(r"(?i)authorization:\s*(bearer|basic)\s+\S+"), r"authorization: \1 [REDACTED]"),
        # Bare Bearer/Basic token (not preceded by authorization: already matched above)
        (re.compile(r"(?i)(?<!\w)(bearer|basic)\s+\S{8,}"), r"\1 [REDACTED]"),
        # key=value / key:value forms (token, api_key, password, secret, auth)
        (re.compile(r"(?i)\b(token|api[_-]?key|password|secret|authorization?)[\s]*[:=]\s*\S+"), r"\1=[REDACTED]"),
        # Environment variable assignments
        (re.compile(r"(?i)(JIRA_API_TOKEN|JIRA_USER)=\S+"), r"\1=[REDACTED]"),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            for pattern, replacement in self.REDACTED_PATTERNS:
                record.msg = pattern.sub(replacement, record.msg)
        return True


class StructuredLogger:
    """JSON-structured logger with credential redaction."""

    def __init__(self, name: str = "jira_hermes_bridge", level: int = logging.INFO):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        handler.addFilter(RedactingFilter())
        self.logger.addHandler(handler)

    def log(self, level: str, event: str, **kwargs: Any) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "event": event,
            **kwargs,
        }
        self.logger.log(getattr(logging, level.upper(), logging.INFO), json.dumps(entry))

    def info(self, event: str, **kwargs: Any) -> None:
        self.log("info", event, **kwargs)

    def warn(self, event: str, **kwargs: Any) -> None:
        self.log("warning", event, **kwargs)

    def error(self, event: str, **kwargs: Any) -> None:
        self.log("error", event, **kwargs)

    def debug(self, event: str, **kwargs: Any) -> None:
        self.log("debug", event, **kwargs)


# ---------------------------------------------------------------------------
# Redactor — strips secrets from any dict for safe logging
# ---------------------------------------------------------------------------


def redact_dict(d: dict[str, Any], sensitive_keys: set[str] | None = None) -> dict[str, Any]:
    """Return a copy of d with sensitive keys replaced by [REDACTED]."""
    if sensitive_keys is None:
        sensitive_keys = {
            "token", "api_token", "password", "secret",
            "authorization", "auth", "credentials", "api_key",
        }
    # Normalise: strip non-alpha chars and lowercase — so apiKey, api_key, api-key all match
    def _normalise(key: str) -> str:
        return re.sub(r"[^a-z]", "", key.lower())
    sensitive_norms = {_normalise(k) for k in sensitive_keys}
    result = {}
    for k, v in d.items():
        if _normalise(k) in sensitive_norms:
            result[k] = "[REDACTED]"
        elif isinstance(v, dict):
            result[k] = redact_dict(v, sensitive_keys)
        else:
            result[k] = v
    return result


# ---------------------------------------------------------------------------
# Credential loading
# ---------------------------------------------------------------------------


def load_credentials() -> dict[str, str]:
    """Load Jira credentials from environment variables only."""
    creds = {
        "base_url": os.environ.get("JIRA_BASE_URL", ""),
        "user": os.environ.get("JIRA_USER", ""),
        "api_token": os.environ.get("JIRA_API_TOKEN", ""),
    }
    missing = [k for k, v in creds.items() if not v and k != "base_url"]
    if missing:
        raise CredentialError(f"Missing required environment variables: {', '.join('JIRA_' + k.upper() for k in missing)}")
    if not creds["base_url"]:
        raise CredentialError("JIRA_BASE_URL environment variable is required")
    # Normalize base URL
    creds["base_url"] = creds["base_url"].rstrip("/")
    return creds


class CredentialError(Exception):
    """Raised when required credentials are missing."""
    pass


# ---------------------------------------------------------------------------
# Jira adapter (boundary — no real HTTP in unit tests)
# ---------------------------------------------------------------------------


class JiraClient:
    """Adapter for Jira REST API v3."""

    def __init__(self, base_url: str, user: str, api_token: str):
        self.base_url = base_url
        self.user = user
        self.api_token = api_token

    def search_issues(self, jql: str, max_results: int = 50) -> list[dict]:
        """Search issues through Jira Cloud enhanced JQL search.

        `/rest/api/3/search` has been removed. Enhanced search uses
        `nextPageToken`, not `startAt`, so this method paginates until the
        requested overall limit is reached and guards repeated tokens.
        """
        if max_results <= 0:
            return []
        url = f"{self.base_url}/rest/api/3/search/jql"
        issues: list[dict] = []
        next_token: str | None = None
        seen_tokens: set[str] = set()

        while len(issues) < max_results:
            page_size = min(100, max_results - len(issues))
            params: dict[str, Any] = {
                "jql": jql,
                "maxResults": page_size,
                "fields": [
                    "summary",
                    "description",
                    "labels",
                    "issuelinks",
                    "status",
                    "assignee",
                ],
            }
            if next_token:
                params["nextPageToken"] = next_token
            req = urllib.request.Request(
                url,
                data=json.dumps(params).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Basic {_basic_auth(self.user, self.api_token)}",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                error_detail = _extract_jira_error(e)
                raise JiraApiError(
                    f"Jira search failed: {e.code} {e.reason} — {error_detail}"
                ) from e
            except urllib.error.URLError as e:
                raise JiraApiError(f"Jira connection failed: {e.reason}") from e

            page = body.get("issues", [])
            if not isinstance(page, list):
                raise JiraApiError("Jira search returned a non-list issues field")
            issues.extend(page[:max_results - len(issues)])
            token = body.get("nextPageToken")
            if not token:
                break
            if not isinstance(token, str):
                raise JiraApiError("Jira search returned an invalid nextPageToken")
            if token in seen_tokens:
                raise JiraApiError("Jira search repeated nextPageToken")
            seen_tokens.add(token)
            next_token = token

        return issues

    def add_comment(self, issue_key: str, body: str) -> dict:
        """Add a comment to a Jira issue."""
        url = f"{self.base_url}/rest/api/3/issue/{issue_key}/comment"
        payload = json.dumps({
            "body": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": body}],
                    }
                ],
            }
        }).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Basic {_basic_auth(self.user, self.api_token)}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                # Some successful Jira write endpoints may return an empty
                # body. Treat that as success instead of raising JSONDecodeError.
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as e:
            raise JiraApiError(f"Jira comment failed: {e.code} {e.reason}") from e

    def transition_issue(self, issue_key: str, target_status: str) -> dict:
        """Transition an issue to a new status."""
        # First get available transitions
        url = f"{self.base_url}/rest/api/3/issue/{issue_key}/transitions"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Basic {_basic_auth(self.user, self.api_token)}",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                transitions = json.loads(resp.read().decode("utf-8")).get("transitions", [])
        except urllib.error.HTTPError as e:
            raise JiraApiError(f"Jira transitions fetch failed: {e.code} {e.reason}") from e

        # Find matching transition
        transition_id = None
        for t in transitions:
            if t.get("name", "").lower() == target_status.lower():
                transition_id = t["id"]
                break
            if t.get("to", {}).get("name", "").lower() == target_status.lower():
                transition_id = t["id"]
                break

        if not transition_id:
            raise JiraApiError(f"No transition found for status '{target_status}' on {issue_key}")

        # Execute transition
        payload = json.dumps({"transition": {"id": transition_id}}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Basic {_basic_auth(self.user, self.api_token)}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                # Jira transition POST normally returns HTTP 204 with no body.
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as e:
            raise JiraApiError(f"Jira transition failed: {e.code} {e.reason}") from e


def _basic_auth(user: str, token: str) -> str:
    """Build Basic auth header value."""
    import base64
    return base64.b64encode(f"{user}:{token}".encode()).decode()


# Sensitive keys to redact from error output
_SENSITIVE_KEYS = frozenset({
    "token", "api_token", "apiToken", "password", "secret",
    "authorization", "auth", "credential", "key",
})


def _extract_jira_error(http_error: urllib.error.HTTPError) -> str:
    """Extract and redact Jira error messages from an HTTPError response body.

    Returns a safe diagnostic string containing errorMessages and errors
    from the Jira response, with any sensitive values redacted.
    """
    try:
        body = http_error.read().decode("utf-8", errors="replace")
        data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        # Not JSON — return truncated raw body
        return body[:200] if body else "(empty response body)"

    parts: list[str] = []

    # errorMessages: list of strings
    for msg in data.get("errorMessages", []):
        parts.append(str(msg))

    # errors: dict of field -> message
    errors = data.get("errors", {})
    for field, msg in errors.items():
        # Redact sensitive field names
        if field.lower() in _SENSITIVE_KEYS:
            parts.append(f"{field}: [REDACTED]")
        else:
            parts.append(f"{field}: {msg}")

    return "; ".join(parts) if parts else "(no error details in response)"


class JiraApiError(Exception):
    """Raised on Jira API failures."""
    pass


# ---------------------------------------------------------------------------
# Eligibility checker
# ---------------------------------------------------------------------------


def check_eligibility(issue: dict) -> tuple[bool, str, str | None]:
    """Check if a Jira issue is eligible for dispatch.

    Returns: (eligible, reason, agent_label_or_none)
    """
    fields = issue.get("fields", {})
    labels: list[str] = fields.get("labels", [])
    label_set = set(labels)

    # 1. Must have ready-for-dispatch
    if "ready-for-dispatch" not in label_set:
        return False, "Missing ready-for-dispatch label", None

    # 2. Must NOT have block labels
    block_found = BLOCK_LABELS & label_set
    if block_found:
        return False, f"Block labels present: {', '.join(sorted(block_found))}", None

    # 3. Must have exactly one agent-* label
    agent_labels = [l for l in labels if l.startswith("agent-")]
    if len(agent_labels) == 0:
        return False, "No agent-* label found", None
    if len(agent_labels) > 1:
        return False, f"Multiple agent labels: {', '.join(sorted(agent_labels))}", None

    agent_label = agent_labels[0]

    # 4. Must map to a known profile
    if agent_label not in AGENT_LABEL_TO_PROFILE:
        return False, f"Unknown agent label: {agent_label}", agent_label

    # 5. Must not have unresolved blockers
    issuelinks = fields.get("issuelinks", [])
    unresolved = []
    for lk in issuelinks:
        if lk.get("type", {}).get("inward") == "is blocked by":
            inward = lk.get("inwardIssue", {})
            status = inward.get("fields", {}).get("status", {}).get("name", "").lower()
            if status not in ("done", "resolved", "closed"):
                unresolved.append(inward.get("key", "?"))
    if unresolved:
        return False, f"Unresolved blockers: {', '.join(unresolved)}", agent_label

    return True, "Eligible for dispatch", agent_label


# ---------------------------------------------------------------------------
# Label → profile mapper
# ---------------------------------------------------------------------------


def map_agent_to_profile(agent_label: str) -> str:
    """Map an agent-* label to a Hermes profile name."""
    profile = AGENT_LABEL_TO_PROFILE.get(agent_label)
    if not profile:
        raise ValueError(f"Unknown agent label: {agent_label}")
    return profile


# ---------------------------------------------------------------------------
# Branch name derivation
# ---------------------------------------------------------------------------


def derive_branch_name(issue_key: str, summary: str) -> str:
    """Derive a deterministic branch name from issue key and summary."""
    slug = re.sub(r"[^a-z0-9]+", "-", summary.lower()).strip("-")[:40]
    key_part = issue_key.lower().replace("-", "")
    return f"{key_part}-{slug}"


# ---------------------------------------------------------------------------
# Bounded context builder
# ---------------------------------------------------------------------------


def build_context_package(issue: dict) -> dict:
    """Build a bounded context package from a Jira issue.

    Extracts only what the assigned agent needs — no product vision injection.
    """
    fields = issue.get("fields", {})
    labels = fields.get("labels", [])
    description = fields.get("description", "")

    # Extract description text from ADF if needed
    if isinstance(description, dict):
        description = _extract_adf_as_markdown(description)

    # Parse sections from description
    sections = _parse_description_sections(description or "")

    # Extract linked dependencies
    dependencies = []
    for lk in fields.get("issuelinks", []):
        if lk.get("type", {}).get("inward") == "is blocked by":
            inward = lk.get("inwardIssue", {})
            dependencies.append({
                "key": inward.get("key"),
                "status": inward.get("fields", {}).get("status", {}).get("name"),
                "link_type": "blocks",
            })

    return {
        "issue_key": issue.get("key", "UNKNOWN"),
        "summary": fields.get("summary", ""),
        "description_full": description,
        "sections": sections,
        "labels": labels,
        "dependencies": dependencies,
        "acceptance_criteria": sections.get("acceptance criteria", ""),
        "tests_evidence": sections.get("tests and evidence", ""),
        "security": sections.get("security", ""),
        "context": sections.get("context", ""),
        "scope": sections.get("scope", ""),
        "out_of_scope": sections.get("out of scope", ""),
    }


def _extract_adf_as_markdown(adf: dict) -> str:
    """Convert ADF to markdown text preserving heading markers and newlines."""
    blocks: list[str] = []

    def walk(obj):
        if isinstance(obj, dict):
            typ = obj.get("type", "")
            if typ == "heading":
                level = obj.get("attrs", {}).get("level", 1)
                text = "".join(
                    c.get("text", "") for c in obj.get("content", []) if c.get("type") == "text"
                )
                blocks.append(f"{'#' * level} {text}")
            elif typ == "paragraph":
                text = "".join(
                    c.get("text", "") for c in obj.get("content", []) if c.get("type") == "text"
                )
                blocks.append(text)
            elif typ == "text":
                blocks.append(obj.get("text", ""))
            else:
                # Recurse into content for unknown block types
                for child in obj.get("content", []):
                    walk(child)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(adf)
    return "\n".join(blocks)


def _parse_description_sections(description: str) -> dict[str, str]:
    """Parse markdown-style sections from description into a dict."""
    sections: dict[str, str] = {}
    current_key = None
    current_lines: list[str] = []

    for line in description.split("\n"):
        heading_match = re.match(r"^#{1,3}\s+(.+)", line)
        if heading_match:
            if current_key:
                sections[current_key] = "\n".join(current_lines).strip()
            current_key = heading_match.group(1).strip().lower()
            current_lines = []
        else:
            current_lines.append(line)

    if current_key:
        sections[current_key] = "\n".join(current_lines).strip()

    return sections


# ---------------------------------------------------------------------------
# Hermes adapter (boundary — uses subprocess in real runs)
# ---------------------------------------------------------------------------


class HermesClient:
    """Adapter for Hermes Kanban operations."""

    def __init__(self, logger: StructuredLogger, db_path: str | None = None):
        self.logger = logger
        self.db_path = db_path

    def check_existing_task(self, idempotency_key: str) -> str | None:
        """Check if a task with the given idempotency key already exists.
        Returns task_id if found, None otherwise.
        Uses the kanban SQLite DB directly for idempotency lookup."""
        import sqlite3

        db_path = self.db_path or self._find_kanban_db()
        if not db_path or not Path(db_path).exists():
            return None

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.execute(
                "SELECT id FROM tasks WHERE idempotency_key = ? AND status != 'archived'",
                (idempotency_key,),
            )
            row = cursor.fetchone()
            conn.close()
            return row[0] if row else None
        except Exception as e:
            self.logger.warn("idempotency_check_failed", error=str(e))
            return None

    def create_task(
        self,
        title: str,
        body: str,
        assignee: str,
        project: str,
        branch_name: str,
        runtime_seconds: int = DEFAULT_RUNTIME_SECONDS,
        idempotency_key: str | None = None,
        dry_run: bool = False,
    ) -> dict:
        """Create a Hermes kanban task. Returns creation result dict."""
        if dry_run:
            self.logger.info(
                "dry_run_create",
                title=title,
                assignee=assignee,
                project=project,
                branch=branch_name,
                idempotency_key=idempotency_key,
            )
            return {
                "dry_run": True,
                "task_id": f"dry-run-{idempotency_key}",
                "title": title,
                "assignee": assignee,
                "project": project,
                "branch": branch_name,
            }

        # In real mode, this would call kanban_create via hermes CLI or tool
        # Use the installed Hermes CLI contract: board option before the verb,
        # positional title, and `--workspace worktree`.
        board = os.environ.get("HERMES_KANBAN_BOARD", "brandos")
        cmd = [
            "hermes", "kanban", "--board", board, "create",
            "--assignee", assignee,
            "--project", project,
            "--body", body,
            "--workspace", "worktree",
            "--branch", branch_name,
            "--max-runtime", str(runtime_seconds),
        ]
        if idempotency_key:
            cmd.extend(["--idempotency-key", idempotency_key])
        cmd.extend(["--json", title])

        self.logger.info(
            "create_task_command",
            command=" ".join(cmd[:6]) + "...",
            assignee=assignee,
            project=project,
            idempotency_key=idempotency_key,
        )

        # Execute via subprocess
        import subprocess
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
            if result.returncode != 0:
                raise HermesApiError(f"Task creation failed: {result.stderr}")
            return json.loads(result.stdout) if result.stdout.strip() else {"task_id": "created"}
        except subprocess.TimeoutExpired:
            raise HermesApiError("Task creation timed out after 60s")
        except json.JSONDecodeError:
            return {"task_id": result.stdout.strip(), "raw": True}

    def _find_kanban_db(self) -> str | None:
        """Find the kanban SQLite DB from environment or default paths."""
        db = os.environ.get("HERMES_KANBAN_DB")
        if db and Path(db).exists():
            return db
        # Try default location
        home = Path.home()
        default = home / ".hermes" / "kanban.db"
        if default.exists():
            return str(default)
        return None


class HermesApiError(Exception):
    """Raised on Hermes API failures."""
    pass


# ---------------------------------------------------------------------------
# Dispatcher — the main orchestration logic
# ---------------------------------------------------------------------------


class Dispatcher:
    """Orchestrates the Jira → Hermes task bridge."""

    def __init__(
        self,
        jira: JiraClient,
        hermes: HermesClient,
        logger: StructuredLogger,
        project_key: str = "BOS",
        limit: int = 50,
        dry_run: bool = False,
    ):
        self.jira = jira
        self.hermes = hermes
        self.logger = logger
        self.project_key = project_key
        self.limit = limit
        self.dry_run = dry_run
        self.results: list[dict] = []

    def run(self) -> list[dict]:
        """Execute one bridge cycle: query → filter → dispatch."""
        self.logger.info(
            "bridge_cycle_start",
            project=self.project_key,
            dry_run=self.dry_run,
            limit=self.limit,
        )

        # 1. Query Jira for eligible issues
        jql = (
            f'project = {self.project_key} '
            f'AND labels = "ready-for-dispatch" '
            f'AND status != "In Progress" '
            f'AND status != "Done" '
            f'ORDER BY priority DESC, created ASC'
        )

        try:
            issues = self.jira.search_issues(jql, max_results=self.limit)
        except JiraApiError as e:
            self.logger.error("jira_query_failed", error=str(e))
            raise

        self.logger.info("jira_query_result", count=len(issues))

        # 2. Filter and dispatch each issue
        for issue in issues:
            result = self._process_issue(issue)
            self.results.append(result)

        # 3. Summary
        dispatched = sum(1 for r in self.results if r["status"] == "dispatched")
        skipped = sum(1 for r in self.results if r["status"] == "skipped")
        failed = sum(1 for r in self.results if r["status"] == "failed")

        self.logger.info(
            "bridge_cycle_complete",
            total=len(self.results),
            dispatched=dispatched,
            skipped=skipped,
            failed=failed,
        )

        return self.results

    def _process_issue(self, issue: dict) -> dict:
        """Process a single Jira issue: check eligibility, build context, dispatch."""
        issue_key = issue.get("key", "UNKNOWN")
        fields = issue.get("fields", {})
        summary = fields.get("summary", "No title")

        self.logger.info("processing_issue", issue_key=issue_key, summary=summary)

        # Check eligibility
        eligible, reason, agent_label = check_eligibility(issue)
        if not eligible:
            self.logger.info("issue_skipped", issue_key=issue_key, reason=reason)
            return {
                "issue_key": issue_key,
                "status": "skipped",
                "reason": reason,
            }

        # Map to profile
        assert agent_label is not None
        profile = map_agent_to_profile(agent_label)

        # Check idempotency
        idempotency_key = f"jira:{issue_key}"
        existing_task_id = self.hermes.check_existing_task(idempotency_key)
        if existing_task_id:
            self.logger.info(
                "duplicate_suppressed",
                issue_key=issue_key,
                existing_task_id=existing_task_id,
            )
            return {
                "issue_key": issue_key,
                "status": "skipped",
                "reason": f"Task already exists: {existing_task_id}",
                "existing_task_id": existing_task_id,
            }

        # Build bounded context
        context = build_context_package(issue)
        branch_name = derive_branch_name(issue_key, summary)

        # Build task body
        body = self._build_task_body(issue_key, context)

        # Dispatch to Hermes
        try:
            task_result = self.hermes.create_task(
                title=f"{issue_key} - {summary}",
                body=body,
                assignee=profile,
                project=HERMES_PROJECT,
                branch_name=branch_name,
                idempotency_key=idempotency_key,
                dry_run=self.dry_run,
            )
        except HermesApiError as e:
            self.logger.error("dispatch_failed", issue_key=issue_key, error=str(e))
            # Record failure to Jira (unless dry run)
            if not self.dry_run:
                self._record_failure(issue_key, str(e))
            return {
                "issue_key": issue_key,
                "status": "failed",
                "reason": str(e),
            }

        # Update Jira (unless dry run)
        if not self.dry_run:
            task_id = task_result.get("task_id", "unknown")
            self._update_jira_dispatch(issue_key, task_id, branch_name)

        self.logger.info(
            "issue_dispatched",
            issue_key=issue_key,
            profile=profile,
            branch=branch_name,
            dry_run=self.dry_run,
            task_id=task_result.get("task_id"),
        )

        return {
            "issue_key": issue_key,
            "status": "dispatched",
            "profile": profile,
            "branch": branch_name,
            "task_id": task_result.get("task_id"),
            "dry_run": self.dry_run,
        }

    def _build_task_body(self, issue_key: str, context: dict) -> str:
        """Build a bounded task body for Hermes."""
        parts = [
            f"Implement Jira {issue_key}.",
            "",
            "## Summary",
            context.get("summary", ""),
            "",
            "## Acceptance Criteria",
            context.get("acceptance_criteria", "Not specified"),
            "",
            "## Tests and Evidence",
            context.get("tests_evidence", "Not specified"),
            "",
            "## Security",
            context.get("security", "Not specified"),
            "",
            "## Context",
            context.get("context", "Not specified"),
        ]

        if context.get("scope"):
            parts.extend(["", "## Scope", context["scope"]])

        if context.get("out_of_scope"):
            parts.extend(["", "## Out of Scope", context["out_of_scope"]])

        if context.get("dependencies"):
            parts.extend(["", "## Dependencies"])
            for dep in context["dependencies"]:
                parts.append(f"- {dep['key']} ({dep['status']})")

        return "\n".join(parts)

    def _update_jira_dispatch(self, issue_key: str, task_id: str, branch: str) -> None:
        """Write dispatch evidence to Jira and transition to In Progress."""
        comment = (
            f"[BrandOS Bridge] Dispatched to Hermes.\n"
            f"- Agent Run ID: {task_id}\n"
            f"- Branch: {branch}\n"
            f"- Dispatched at: {datetime.now(timezone.utc).isoformat()}\n"
        )
        try:
            self.jira.add_comment(issue_key, comment)
        except JiraApiError as e:
            self.logger.warn("jira_comment_failed", issue_key=issue_key, error=str(e))

        try:
            self.jira.transition_issue(issue_key, JIRA_TRANSITION_IN_PROGRESS)
        except JiraApiError as e:
            self.logger.warn("jira_transition_failed", issue_key=issue_key, error=str(e))

    def _record_failure(self, issue_key: str, error: str) -> None:
        """Record a dispatch failure to Jira as a comment."""
        comment = (
            f"[BrandOS Bridge] Dispatch FAILED.\n"
            f"- Error: {error}\n"
            f"- Time: {datetime.now(timezone.utc).isoformat()}\n"
            f"- The issue will remain blocked until the failure is resolved."
        )
        try:
            self.jira.add_comment(issue_key, comment)
        except JiraApiError as e:
            self.logger.error("jira_failure_comment_failed", issue_key=issue_key, error=str(e))


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Jira-to-Hermes task bridge for BrandOS",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Simulate dispatch without creating tasks or updating Jira",
    )
    parser.add_argument(
        "--project-key",
        default="BOS",
        help="Jira project key (default: BOS)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum number of issues to process per cycle",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Enable debug logging",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # Set up logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logger = StructuredLogger(level=log_level)

    logger.info(
        "bridge_startup",
        project=args.project_key,
        dry_run=args.dry_run,
        limit=args.limit,
    )

    # Load credentials
    try:
        creds = load_credentials()
    except CredentialError as e:
        logger.error("credential_error", error=str(e))
        return 1

    # Initialize clients
    jira = JiraClient(
        base_url=creds["base_url"],
        user=creds["user"],
        api_token=creds["api_token"],
    )
    hermes = HermesClient(logger=logger)

    # Run dispatcher
    dispatcher = Dispatcher(
        jira=jira,
        hermes=hermes,
        logger=logger,
        project_key=args.project_key,
        limit=args.limit,
        dry_run=args.dry_run,
    )

    try:
        results = dispatcher.run()
    except JiraApiError as e:
        logger.error("bridge_failed", error=str(e))
        return 1
    except Exception as e:
        logger.error("unexpected_error", error=str(e))
        return 1

    # Print results summary
    print("\n--- Bridge Results ---")
    for r in results:
        status = r["status"].upper()
        key = r["issue_key"]
        reason = r.get("reason", "")
        print(f"  [{status}] {key}: {reason or 'OK'}")

    dispatched = sum(1 for r in results if r["status"] == "dispatched")
    print(f"\nTotal: {len(results)} | Dispatched: {dispatched}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
