#!/usr/bin/env python3
"""BrandOS deterministic reconcile loop.

This REPLACES the old autopilot-dispatcher.py (which only printed a report and
left every real decision to a mid-loop agent). reconcile() is fully
deterministic: no model is in the loop. It is the ONLY thing that polls; the
execution and review agents are passive and act only on tasks assigned to them.

Cron calls `python scripts/reconcile.py` every 15 minutes. One pass does three
things, in this fixed order:

    1. reclaim  - release worker claims on tasks that overran their runtime,
                  so a crashed/stuck worker cannot hold a WIP slot forever.
    2. route    - move terminal tasks to their next deterministic state:
                    done-with-open-PR      -> create a review task for agent-quality
                    blocked/rework-needed  -> re-open the Jira issue for another pass
                  (The review AGENT still does the judgement; routing just hands
                   it the card. It never "watches" the board itself.)
    3. refill   - while WIP < WIP_LIMIT and the credit breaker is closed,
                  promote eligible Jira issues and dispatch them, up to the limit.

Three safety gates (see module constants) make "fully automatic" safe rather
than blind:

    GATE 1 (readiness):     an issue is auto-labelled ready-for-dispatch ONLY if
                            it passes every Definition-of-Ready check. High-risk
                            or human-approval issues are NEVER auto-promoted -
                            they are reported for manual approval instead.
    GATE 2 (WIP ceiling):   at most WIP_LIMIT tasks run at once; refill respects
                            remaining slots even if 50 issues are ready.
    GATE 3 (credit breaker): if any active task is blocked on a credit/quota
                            error (HTTP 402) or has crashed repeatedly, refill is
                            SUSPENDED for the whole pass. reclaim/route still run.
                            This is what stops the loop from burning credit on a
                            dead provider - exactly the OpenRouter 402 situation.

This module shells out to the real `hermes kanban` CLI (verbs confirmed from
`hermes kanban --help`) and to Jira via the existing jira_hermes_bridge module.
Every hermes call goes through _run_hermes() so it is trivially mockable in tests
and every side effect is logged.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Any

# Reuse the already-tested readiness checks and the bridge's dispatch logic.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_readiness as readiness  # noqa: E402
import jira_hermes_bridge as bridge  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

WIP_LIMIT = int(os.environ.get("BRANDOS_WIP_LIMIT", "2"))
BOARD = os.environ.get("HERMES_KANBAN_BOARD", "brandos")
PROJECT_KEY = os.environ.get("BRANDOS_PROJECT_KEY", "BOS")

# A running task older than this (seconds) is considered stale and reclaimed.
# Aligned with the runbook's "4 hours" rule, not the 90-minute max-runtime, so
# reclaim and max-runtime don't fight over the same task. Keep them consistent.
STALE_AFTER_SECONDS = int(os.environ.get("BRANDOS_STALE_SECONDS", str(4 * 3600)))

# A task that has crashed this many times in a row is treated as a hard block
# and trips the credit/error breaker instead of being retried forever.
MAX_CONSECUTIVE_FAILURES = int(os.environ.get("BRANDOS_MAX_FAILURES", "2"))

# Reclaim is OFF by default: hermes already enforces max-runtime and heartbeats,
# so reconcile should not second-guess liveness unless explicitly told to.
RECLAIM_ENABLED = os.environ.get("BRANDOS_RECLAIM_ENABLED", "0") == "1"

# Set by --dry-run: read everything, but perform no create/reclaim/label writes.
DRY_RUN = False

# Side-effecting hermes verbs that dry-run must not actually execute.
_MUTATING_VERBS = {
    "create", "reclaim", "reassign", "complete", "block", "unblock",
    "comment", "archive",
}

# Risk levels that must NEVER be auto-promoted. These always wait for a human.
MANUAL_APPROVAL_RISK = {"risk-high", "risk-critical"}

# HARD readiness checks - a failure here blocks auto-promotion. These are the
# genuine "is this work executable?" checks. The pre-1.0 human_approval rule is
# deliberately NOT here: it's a risk decision (handled below), not a quality
# defect, and keeping it here would block every pre-1.0 issue forever.
HARD_CHECKS = {
    "no_block_labels",
    "description_structure",
    "acceptance_criteria",
    "dependency_links",
    "required_labels",
}
# SOFT checks - logged as warnings but do not block. Missing a "### Security"
# heading or the word "module" shouldn't stop otherwise-ready, low-risk work.
SOFT_CHECKS = {"repository_context", "tests_evidence", "security_privacy", "human_approval"}

# Substrings that identify a credit/quota block in a task's block reason.
CREDIT_BLOCK_MARKERS = ("402", "credit", "quota", "insufficient", "payment required")

REVIEW_PROFILE = "brandosquality"
HERMES_PROJECT = bridge.HERMES_PROJECT  # "ai-marketing-vibe"
GITHUB_REPO = os.environ.get("BRANDOS_GITHUB_REPO", "alimst1996/brandos")


# ---------------------------------------------------------------------------
# Structured logging (JSON lines, one event per line)
# ---------------------------------------------------------------------------

def log(event: str, **kw: Any) -> None:
    print(json.dumps({"ts": int(time.time()), "event": event, **kw}))


def extract_jira_key(title: str) -> str | None:
    """Pull a BOS-NNN key from a task title. Titles look like 'BOS-21 - ...'."""
    m = re.match(r"([A-Z]+-\d+)", title or "")
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Hermes CLI adapter (single choke point - mock this in tests)
# ---------------------------------------------------------------------------

class HermesError(RuntimeError):
    pass


def _run_hermes(args: list[str], *, timeout: int = 60) -> str:
    """Run a `hermes kanban ...` command and return stdout.

    All hermes interaction goes through here so tests can monkeypatch a single
    function and every real invocation is logged. Under DRY_RUN, mutating verbs
    are logged but not executed; read verbs (list/show/runs) still run.
    """
    verb = args[0] if args else ""
    if DRY_RUN and verb in _MUTATING_VERBS:
        log("dry_run_skip", verb=verb, args=" ".join(args))
        return ""
    cmd = ["hermes", "kanban", "--board", BOARD, *args]
    log("hermes_call", cmd=" ".join(cmd))
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as e:
        raise HermesError(f"hermes CLI not found: {e}") from e
    except subprocess.TimeoutExpired as e:
        raise HermesError(f"hermes timed out: {' '.join(cmd)}") from e
    if res.returncode != 0:
        raise HermesError(f"hermes failed ({res.returncode}): {res.stderr.strip()}")
    return res.stdout


def list_tasks(status: str | None = None) -> list[dict]:
    """Return kanban tasks as dicts, optionally filtered by status. Uses --json.

    NOTE: the list row does NOT carry block reason or block_kind - those come
    from enrich_task(). Fields confirmed present on the row: id, title, assignee,
    status, priority, started_at, created_at, completed_at, result, workspace_path.
    """
    args = ["list", "--json"]
    if status:
        args += ["--status", status]
    out = _run_hermes(args)
    if not out.strip():
        return []
    data = json.loads(out)
    # hermes returns a bare JSON list (confirmed). Handle {"tasks": [...]} too.
    return data["tasks"] if isinstance(data, dict) and "tasks" in data else data


def enrich_task(task: dict) -> dict:
    """Attach block reason, kind, failure count, heartbeat age from `show`.

    `hermes kanban list --json` omits WHY a task is blocked. The real detail is
    in `hermes kanban show <id>`. Confirmed shapes from the live board:

      Crash block:
        Diagnostics: consecutive_failures=2 | most_recent_outcome=crashed
        Events: gave_up {'failures': 2, ...}

      Review block:
        Events: blocked {'reason': 'review-required: ...', 'kind': 'needs_input',
                         'recurrences': 1}
        Events also carry per-run `heartbeat` lines and `timed_out {...}`.

    Sets on the task:
        _block_detail : str   full lowercased show text (for credit/402 match)
        _block_kind   : str   'review-required' | 'rework-needed' | '' (from reason)
        _failed_runs  : int   consecutive_failures=N, else 0
        _gave_up      : bool   hermes hit the retry limit
        _last_heartbeat_age : int|None  seconds since last heartbeat, if derivable
    """
    tid = task.get("id")
    detail, kind, failed, gave_up = "", "", 0, False
    hb_ts = None
    try:
        raw = _run_hermes(["show", tid])
        detail = raw.lower()
        m = re.search(r"consecutive_failures=(\d+)", detail)
        if m:
            failed = int(m.group(1))
        # Do not classify from arbitrary historical text. A task can contain an
        # old crash/review event even after a successful later run.
        event_lines = [
            line.lower() for line in raw.splitlines()
            if re.search(r"\]\s+(?:\[[^\]]+\]\s+)?"
                         r"(?:blocked|gave_up|claimed|spawned|completed|unblocked)\b",
                         line, re.IGNORECASE)
        ]
        latest_event = event_lines[-1] if event_lines else ""
        gave_up = "gave_up" in latest_event or "gave up" in latest_event
        blocked_lines = [line for line in event_lines if "blocked" in line]
        latest_block = blocked_lines[-1] if blocked_lines else ""
        if "review-required" in latest_block:
            kind = "review-required"
        elif "rework-needed" in latest_block:
            kind = "rework-needed"
        # Heartbeat: Events look like "[2026-07-27 01:04] [run 36] heartbeat".
        # Take the LAST such timestamp and convert to unix (local time).
        hb_ts = _parse_last_heartbeat(raw)
    except HermesError as e:
        log("enrich_show_failed", task=tid, error=str(e))
    task["_block_detail"] = detail
    task["_block_kind"] = kind
    task["_failed_runs"] = failed
    task["_gave_up"] = gave_up
    task["_last_heartbeat_ts"] = hb_ts
    return task


def _parse_last_heartbeat(show_text: str) -> int | None:
    """Return unix ts of the last `heartbeat` event line, or None.

    Event lines: `[YYYY-MM-DD HH:MM] [run N] heartbeat`. hermes prints local
    time without seconds; we parse the last heartbeat line's timestamp. Any
    parse failure returns None (reclaim treats None as 'do not touch').
    """
    import datetime as _dt
    last = None
    for line in show_text.splitlines():
        if "heartbeat" not in line.lower():
            continue
        m = re.search(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\]", line)
        if not m:
            continue
        try:
            dt = _dt.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M")
            last = int(dt.timestamp())  # local-time interpretation
        except ValueError:
            continue
    return last


# ---------------------------------------------------------------------------
# Task model helpers (defensive against schema drift)
# ---------------------------------------------------------------------------

def _task_age_seconds(task: dict) -> int:
    """Seconds since the worker started. Real field: started_at (unix seconds)."""
    started = task.get("started_at")
    if not started:
        return 0
    try:
        return max(0, int(time.time()) - int(started))
    except (TypeError, ValueError):
        return 0


def _block_reason(task: dict) -> str:
    """Block reason, populated by enrich_task() (list row alone has none)."""
    return str(task.get("_block_detail") or task.get("result") or "").lower()


def _consecutive_failures(task: dict) -> int:
    """Count of crashed runs. Not on the list row - derived via enrich_task()."""
    try:
        return int(task.get("_failed_runs", 0))
    except (TypeError, ValueError):
        return 0


def _last_heartbeat_age(task: dict) -> int | None:
    """Seconds since the task's last heartbeat, or None if unknown.

    Only meaningful after enrich_heartbeat() has populated _last_heartbeat_ts
    from `hermes kanban show` Events. Returns None when we cannot confirm - and
    the reclaim logic treats None as "do not touch" (fail safe).
    """
    ts = task.get("_last_heartbeat_ts")
    if not ts:
        return None
    try:
        return max(0, int(time.time()) - int(ts))
    except (TypeError, ValueError):
        return None


def is_hard_block(task: dict) -> bool:
    """True if this blocked task must NOT be retried automatically.

    Covers the real failure modes seen on the board:
      - hermes gave up after hitting the retry limit (`gave_up`)
      - the worker crashed >= MAX_CONSECUTIVE_FAILURES times in a row
      - a credit/quota/402 marker appears in the block detail
    """
    if task.get("_gave_up"):
        return True
    if _consecutive_failures(task) >= MAX_CONSECUTIVE_FAILURES:
        return True
    reason = _block_reason(task)
    if any(m in reason for m in CREDIT_BLOCK_MARKERS):
        return True
    return False


def is_credit_related(task: dict) -> bool:
    """A credit/quota/402 block. These are account-wide, so they suspend ALL
    refill (global breaker). Crash/gave-up blocks are per-profile instead."""
    return any(m in _block_reason(task) for m in CREDIT_BLOCK_MARKERS)


def blocked_profiles(active: list[dict]) -> set[str]:
    """Profiles that are hard-blocked by a crash/gave-up (NOT credit).

    refill must skip dispatching to these profiles, but other profiles keep
    flowing - a stuck brandosquality review must not halt brandosbackend work.
    """
    out = set()
    for t in active:
        if t.get("status") == "blocked" and is_hard_block(t) and not is_credit_related(t):
            if t.get("assignee"):
                out.add(t["assignee"])
    return out


# Backwards-compatible alias (older tests may import is_credit_block).
is_credit_block = is_hard_block


# ---------------------------------------------------------------------------
# Readiness gate (GATE 1) - reuse check_readiness, minus the label-presence check
# ---------------------------------------------------------------------------

@dataclass
class Classification:
    ready_auto: list[dict] = field(default_factory=list)      # promote + dispatch
    needs_human: list[dict] = field(default_factory=list)     # report only
    not_ready: list[dict] = field(default_factory=list)       # skip silently


def classify_issue(issue: dict) -> tuple[str, list[str]]:
    """Return (bucket, reasons). bucket in {ready_auto, needs_human, not_ready}.

    Only HARD_CHECKS block auto-promotion. Soft checks are logged but tolerated.
    The ready-for-dispatch check is ignored - reconcile is what SETS that label.
    High-risk / human-approval issues that otherwise pass go to needs_human.
    """
    report = readiness.validate_issue(issue)
    hard_fail = [
        c for c in report["checks"]
        if not c["passed"] and c["name"] in HARD_CHECKS
    ]
    soft_fail = [
        c["name"] for c in report["checks"]
        if not c["passed"] and c["name"] in SOFT_CHECKS
    ]

    labels = issue.get("fields", {}).get("labels", [])

    if hard_fail:
        return "not_ready", [f"{c['name']}: {c['detail']}" for c in hard_fail]

    # Passes every hard quality check. Split on risk / human approval.
    if "human-approval-required" in labels or (MANUAL_APPROVAL_RISK & set(labels)):
        reasons = ["passes quality gates; high-risk/human-approval -> manual"]
        if soft_fail:
            reasons.append("soft warnings: " + ", ".join(soft_fail))
        return "needs_human", reasons

    reasons = ["passes hard readiness checks"]
    if soft_fail:
        reasons.append("soft warnings (non-blocking): " + ", ".join(soft_fail))
    return "ready_auto", reasons


def classify_all(issues: list[dict]) -> Classification:
    c = Classification()
    for issue in issues:
        bucket, reasons = classify_issue(issue)
        key = issue.get("key", "?")
        if bucket == "ready_auto":
            c.ready_auto.append(issue)
            log("classify", issue=key, bucket=bucket)
        elif bucket == "needs_human":
            c.needs_human.append(issue)
            log("classify", issue=key, bucket=bucket, reasons=reasons)
        else:
            c.not_ready.append(issue)
            log("classify", issue=key, bucket=bucket, reasons=reasons[:3])
    return c


# ---------------------------------------------------------------------------
# The three reconcile phases
# ---------------------------------------------------------------------------

def phase_reclaim(active: list[dict]) -> int:
    """Release worker claims ONLY on tasks that are both stale AND silent.

    hermes already enforces per-task max-runtime (it SIGTERMs and re-queues an
    overrunning worker) and emits heartbeats for live workers. So reclaiming on
    age alone would re-run healthy long tasks - exactly the risk review item 8
    flagged. We therefore reclaim only when RECLAIM_ENABLED is on AND the task
    has had no heartbeat within STALE_AFTER_SECONDS. Default OFF: let hermes own
    liveness unless you explicitly opt in.
    """
    if not RECLAIM_ENABLED:
        return 0
    reclaimed = 0
    for t in active:
        if t.get("status") != "running":
            continue
        hb_age = _last_heartbeat_age(t)
        # Only reclaim when we can POSITIVELY confirm silence past the threshold.
        if hb_age is not None and hb_age > STALE_AFTER_SECONDS:
            tid = t.get("id")
            try:
                _run_hermes(["reclaim", tid])
                log("reclaimed_silent", task=tid, heartbeat_age_s=hb_age)
                reclaimed += 1
            except HermesError as e:
                log("reclaim_failed", task=tid, error=str(e))
    return reclaimed


def phase_route(active: list[dict]) -> int:
    """Hand terminal tasks to their next state. Deterministic, no judgement.

    Reads _block_kind set by enrich_task (the list row has no block kind).
    - review-required -> create a review card for the review profile
    - rework-needed   -> left for the impl agent on next refill (no-op here)
    Hard-blocked tasks (gave-up / crash / credit) are skipped - the breaker owns
    them. Title is POSITIONAL for `hermes kanban create` (not --title).
    """
    routed = 0
    for t in active:
        if t.get("status") != "blocked":
            continue
        # REVIEW cards are finalized by phase_finalize. Routing them here as
        # implementation work causes duplicate demotion/archive attempts.
        if t.get("title", "").startswith("REVIEW "):
            continue
        if is_hard_block(t):
            continue  # gave-up / crash-loop / credit: never respawn into a wall
        kind = (t.get("_block_kind") or "").lower()
        tid = t.get("id")

        if kind == "review-required":
            title = f"REVIEW {t.get('title','')}"
            body = (
                f"Quality review for {t.get('title','')}.\n\n"
                f"Original task: {tid}\n"
                "Inspect the PR, run quality gates, then call kanban complete "
                "(approve) or kanban block with rework-needed (reject)."
            )
            try:
                # title is POSITIONAL and comes last; idempotency-key prevents
                # a duplicate review card if this pass runs twice.
                _run_hermes([
                    "create",
                    "--assignee", REVIEW_PROFILE,
                    "--project", HERMES_PROJECT,
                    "--body", body,
                    "--idempotency-key", f"review:{tid}",
                    title,
                ])
                log("routed_to_review", task=tid, reviewer=REVIEW_PROFILE)
                routed += 1
            except HermesError as e:
                log("route_review_failed", task=tid, error=str(e))
        elif kind == "rework-needed":
            # Item 3: send the work back. Remove the dispatch label so refill
            # re-queues the Jira issue, then archive the stuck card so it stops
            # holding board state. The impl agent picks it up fresh next pass.
            jira_key = extract_jira_key(t.get("title", ""))
            if not jira_key:
                log("rework_requeue_failed", task=tid, error="missing Jira key")
                continue
            try:
                demote_issue(jira_key)
                log("rework_requeued", task=tid, issue=jira_key)
            except Exception as e:  # noqa: BLE001
                # Never archive the only recovery signal when Jira requeue
                # failed. A later pass can safely retry.
                log("rework_requeue_failed", task=tid, issue=jira_key, error=str(e))
                continue
            try:
                _run_hermes(["archive", tid])
                routed += 1
            except HermesError as e:
                log("archive_failed", task=tid, error=str(e))
        else:
            log("route_noop", task=tid, block_kind=kind)
    return routed


def _issue_profile(issue: dict) -> str | None:
    """Map an issue's agent-* label to its hermes profile (via the bridge map)."""
    labels = issue.get("fields", {}).get("labels", [])
    for l in labels:
        if l in bridge.AGENT_LABEL_TO_PROFILE:
            return bridge.AGENT_LABEL_TO_PROFILE[l]
    return None


def _review_context(review_task: dict) -> str:
    """Return enough review-card text to recover its PR and original card."""
    parts = [
        str(review_task.get("title") or ""),
        str(review_task.get("result") or ""),
        str(review_task.get("_block_detail") or ""),
    ]
    rid = review_task.get("id")
    if rid:
        try:
            parts.append(_run_hermes(["show", rid]))
        except HermesError as e:
            log("review_show_failed", task=rid, error=str(e))
    return "\n".join(parts)


def _extract_pr_number(text: str) -> int | None:
    """Extract a GitHub PR number from a URL or explicit `PR #N` reference."""
    patterns = (
        r"github\.com/[^/\s]+/[^/\s]+/pull/(\d+)",
        r"\bPR\s*#\s*(\d+)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text or "", re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def _extract_original_task_id(text: str) -> str | None:
    match = re.search(r"\bOriginal task:\s*(t_[a-z0-9]+)\b", text or "", re.IGNORECASE)
    return match.group(1) if match else None


def _run_gh(args: list[str], *, timeout: int = 60) -> str:
    """Run a read-only GitHub CLI command used by the manual-merge gate."""
    cmd = ["gh", *args]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as e:
        raise RuntimeError(f"gh CLI not found: {e}") from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError("gh CLI timed out") from e
    if result.returncode != 0:
        raise RuntimeError(f"gh failed ({result.returncode}): {result.stderr.strip()}")
    return result.stdout


def _pr_is_merged(pr_number: int) -> bool:
    """True only after GitHub confirms the reviewed PR is actually merged."""
    output = _run_gh([
        "pr", "view", str(pr_number), "--repo", GITHUB_REPO,
        "--json", "state,mergedAt",
    ])
    data = json.loads(output)
    return data.get("state") == "MERGED" and bool(data.get("mergedAt"))


def _pr_is_safe_to_merge(pr_number: int) -> bool:
    """Require GitHub mergeability and no pending/failing status checks."""
    output = _run_gh([
        "pr", "view", str(pr_number), "--repo", GITHUB_REPO,
        "--json", "state,mergeable,statusCheckRollup",
    ])
    data = json.loads(output)
    if data.get("state") != "OPEN" or data.get("mergeable") != "MERGEABLE":
        return False
    for check in data.get("statusCheckRollup") or []:
        conclusion = str(check.get("conclusion") or "").upper()
        status = str(check.get("status") or "").upper()
        if status and status != "COMPLETED":
            return False
        if conclusion and conclusion not in {"SUCCESS", "NEUTRAL", "SKIPPED"}:
            return False
    return True


def _jira_issue_labels(issue_key: str) -> set[str]:
    """Read current Jira labels without exposing credential values."""
    import urllib.request
    import urllib.error

    creds = bridge.load_credentials()
    url = f"{creds['base_url']}/rest/api/3/issue/{issue_key}?fields=labels"
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Basic {bridge._basic_auth(creds['user'], creds['api_token'])}",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(
            f"Jira label check failed for {issue_key}: {e.code} {e.reason}"
        ) from e
    return set(body.get("fields", {}).get("labels") or [])


def _merge_pr(pr_number: int) -> None:
    """Squash-merge one low-risk, independently approved PR."""
    if DRY_RUN:
        log("dry_run_skip", verb="github_merge", pr=pr_number)
        return
    _run_gh([
        "pr", "merge", str(pr_number), "--repo", GITHUB_REPO, "--squash",
    ], timeout=180)


def phase_finalize(review_tasks: list[dict]) -> dict:
    """Close the loop on finished REVIEW cards. Deterministic.

    A review card is one whose title starts with 'REVIEW ' (created by
    phase_route). We look at review cards that have reached a terminal state:

      review card == done   -> APPROVED:
          * low-risk + mergeable + green checks: squash-merge automatically
          * high-risk/human-approval: leave state intact for manual merge
          * only after GitHub confirms MERGED: transition Jira to Done and
            archive the original/review cards
      review card == blocked with rework-needed -> REJECTED:
          * remove ready-for-dispatch from the Jira issue so refill re-queues it
          * archive the review card

    Returns counts: {"approved": n, "reworked": n}.
    """
    approved, reworked, awaiting_merge = 0, 0, 0
    for rt in review_tasks:
        title = rt.get("title", "")
        if not title.startswith("REVIEW "):
            continue
        orig_title = title[len("REVIEW "):]
        jira_key = extract_jira_key(orig_title)
        status = rt.get("status")
        rid = rt.get("id")

        if status == "done":
            context = _review_context(rt)
            pr_number = _extract_pr_number(context)
            original_id = _extract_original_task_id(context)
            if not jira_key or not pr_number:
                log("finalize_waiting_for_evidence", issue=jira_key, review=rid,
                    reason="missing Jira key or reviewed PR number")
                awaiting_merge += 1
                continue
            try:
                merged = _pr_is_merged(pr_number)
            except Exception as e:  # noqa: BLE001
                log("github_merge_check_failed", issue=jira_key, review=rid,
                    pr=pr_number, error=str(e))
                awaiting_merge += 1
                continue
            if not merged:
                try:
                    labels = _jira_issue_labels(jira_key)
                except Exception as e:  # noqa: BLE001
                    log("jira_label_check_failed", issue=jira_key, review=rid,
                        error=str(e))
                    awaiting_merge += 1
                    continue
                manual = bool(
                    MANUAL_APPROVAL_RISK & labels
                    or "human-approval-required" in labels
                )
                if manual:
                    log("merge_ready_manual", issue=jira_key, review=rid,
                        pr=pr_number, reason="high-risk/human-approval")
                    awaiting_merge += 1
                    continue
                try:
                    if not _pr_is_safe_to_merge(pr_number):
                        log("merge_waiting_for_checks", issue=jira_key,
                            review=rid, pr=pr_number)
                        awaiting_merge += 1
                        continue
                    _merge_pr(pr_number)
                    if DRY_RUN:
                        awaiting_merge += 1
                        continue
                    merged = _pr_is_merged(pr_number)
                except Exception as e:  # noqa: BLE001
                    log("github_auto_merge_failed", issue=jira_key, review=rid,
                        pr=pr_number, error=str(e))
                    awaiting_merge += 1
                    continue
                if not merged:
                    log("github_merge_not_confirmed", issue=jira_key,
                        review=rid, pr=pr_number)
                    awaiting_merge += 1
                    continue
            try:
                _jira_transition(jira_key, "Done")
                log("review_approved_jira_done", issue=jira_key, review=rid,
                    pr=pr_number)
            except Exception as e:  # noqa: BLE001
                log("jira_done_failed", issue=jira_key, review=rid, error=str(e))
                continue
            # Keep the review card if cleanup is incomplete, so the next pass
            # still has a deterministic recovery signal.
            if original_id:
                try:
                    _run_hermes(["archive", original_id])
                except HermesError as e:
                    log("archive_original_failed", task=original_id, error=str(e))
                    continue
            try:
                _run_hermes(["archive", rid])
            except HermesError as e:
                log("archive_review_failed", task=rid, error=str(e))
                continue
            approved += 1

        elif status == "blocked" and (rt.get("_block_kind") == "rework-needed"):
            # REJECTED. Re-queue the Jira issue by removing the dispatch label.
            if not jira_key:
                log("requeue_failed", review=rid, error="missing Jira key")
                continue
            context = _review_context(rt)
            original_id = _extract_original_task_id(context)
            try:
                demote_issue(jira_key)
                log("review_rejected_requeued", issue=jira_key, review=rid)
            except Exception as e:  # noqa: BLE001
                log("requeue_failed", issue=jira_key, review=rid, error=str(e))
                continue
            if original_id:
                try:
                    _run_hermes(["archive", original_id])
                except HermesError as e:
                    log("archive_original_failed", task=original_id, error=str(e))
                    continue
            try:
                _run_hermes(["archive", rid])
            except HermesError as e:
                log("archive_review_failed", task=rid, error=str(e))
                continue
            reworked += 1

    return {
        "approved": approved,
        "reworked": reworked,
        "awaiting_merge": awaiting_merge,
    }


def _jira_transition(issue_key: str, target_status: str) -> None:
    """Idempotently transition a Jira issue via the bridge JiraClient."""
    if DRY_RUN:
        log("dry_run_skip", verb="jira_transition", issue=issue_key, to=target_status)
        return
    import urllib.request
    import urllib.error

    creds = bridge.load_credentials()
    # A previous pass may have completed the transition but failed while
    # archiving Hermes cards. Treat an already-correct Jira state as success.
    url = f"{creds['base_url']}/rest/api/3/issue/{issue_key}?fields=status"
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Basic {bridge._basic_auth(creds['user'], creds['api_token'])}",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            current = json.loads(response.read().decode("utf-8"))
        current_status = (
            current.get("fields", {}).get("status", {}).get("name", "")
        )
        if current_status.lower() == target_status.lower():
            log("jira_transition_noop", issue=issue_key, status=current_status)
            return
    except urllib.error.HTTPError as e:
        raise RuntimeError(
            f"Jira status check failed for {issue_key}: {e.code} {e.reason}"
        ) from e
    jira = bridge.JiraClient(creds["base_url"], creds["user"], creds["api_token"])
    jira.transition_issue(issue_key, target_status)


def phase_refill(active: list[dict], credit_breaker_open: bool,
                 skip_profiles: set[str] | None = None) -> int:
    """Promote + dispatch eligible Jira issues up to the WIP limit.

    GATE 2 (WIP): only RUNNING tasks count toward capacity - a blocked/review
    task holds no worker, so it must not consume a slot (fixes the "one stuck
    review halts everything" bug).
    GATE 3: a credit/402 block suspends ALL refill (account-wide). A crash block
    only skips that profile, via skip_profiles.
    Ordering: promote (Jira label) BEFORE dispatch, so a crash between the two
    leaves the issue promoted+idempotent rather than silently re-dispatched.
    """
    if credit_breaker_open:
        log("refill_suspended", reason="credit_breaker_open")
        return 0

    skip_profiles = skip_profiles or set()
    running = [t for t in active if t.get("status") == "running"]
    slots = max(0, WIP_LIMIT - len(running))
    if slots == 0:
        log("refill_noop", reason="wip_full", running=len(running), limit=WIP_LIMIT)
        return 0

    issues = fetch_backlog_issues()
    classified = classify_all(issues)

    if classified.needs_human:
        log("awaiting_human_approval",
            count=len(classified.needs_human),
            issues=[i.get("key") for i in classified.needs_human])

    dispatched = 0
    for issue in classified.ready_auto:
        if dispatched >= slots:
            break
        key = issue.get("key")
        prof = _issue_profile(issue)
        if prof in skip_profiles:
            log("dispatch_skipped_blocked_profile", issue=key, profile=prof)
            continue
        promoted = False
        try:
            promote_issue(key)   # 1) write Jira label first (auditable)
            promoted = True
            # The issue object came from the pre-promotion search response.
            # Keep its in-memory labels consistent or the bridge eligibility
            # check will reject it as missing ready-for-dispatch.
            fields = issue.setdefault("fields", {})
            labels = fields.setdefault("labels", [])
            if "ready-for-dispatch" not in labels:
                labels.append("ready-for-dispatch")
            result = dispatch_issue(issue)  # bridge dedups via idempotency-key
            if result.get("status") != "dispatched":
                raise RuntimeError(
                    f"bridge did not dispatch {key}: "
                    f"{result.get('status')} {result.get('reason', '')}".strip()
                )
            log("dispatched", issue=key, profile=prof)
            dispatched += 1
        except Exception as e:  # noqa: BLE001 - one bad issue must not kill the pass
            log("dispatch_failed", issue=key, error=str(e))
            # Item 2: if the label was written but dispatch failed, roll it back
            # so the issue is picked up again next pass instead of being lost.
            # The idempotency-key on create prevents a duplicate if a card DID
            # actually get created before the failure.
            if promoted:
                try:
                    demote_issue(key)
                    log("promotion_rolled_back", issue=key)
                except Exception as e2:  # noqa: BLE001
                    log("rollback_failed", issue=key, error=str(e2))
    return dispatched


# ---------------------------------------------------------------------------
# Jira side (thin wrappers; real calls live in jira_hermes_bridge)
# ---------------------------------------------------------------------------

def fetch_backlog_issues() -> list[dict]:
    """Fetch ALL Backlog BOS issues not yet labelled ready-for-dispatch.

    Two fixes over the naive query:
    - `labels != "ready-for-dispatch"` in Jira EXCLUDES issues with no labels at
      all, so we use `(labels is EMPTY OR labels != "ready-for-dispatch")`.
    - Jira Cloud enhanced search pagination via nextPageToken. The removed
      `/rest/api/3/search` endpoint and its startAt/total contract are never used.
    """
    creds = bridge.load_credentials()
    jql = (
        f'project = {PROJECT_KEY} AND statusCategory = "To Do" '
        f'AND (labels is EMPTY OR labels != "ready-for-dispatch") '
        f'ORDER BY priority DESC, created ASC'
    )
    return _search_paged(creds, jql, page_size=100, max_pages=20)


def _search_paged(creds: dict, jql: str, page_size: int = 100,
                  max_pages: int = 20) -> list[dict]:
    """POST enhanced Jira search with guarded nextPageToken pagination."""
    import urllib.request
    import urllib.error

    url = f"{creds['base_url']}/rest/api/3/search/jql"
    auth = bridge._basic_auth(creds["user"], creds["api_token"])
    all_issues: list[dict] = []
    next_token: str | None = None
    seen_tokens: set[str] = set()
    for _ in range(max_pages):
        request_body: dict[str, Any] = {
            "jql": jql,
            "maxResults": page_size,
            "fields": ["summary", "description", "labels", "issuelinks", "status"],
        }
        if next_token:
            request_body["nextPageToken"] = next_token
        payload = json.dumps(request_body).encode()
        req = urllib.request.Request(
            url, data=payload, method="POST",
            headers={"Content-Type": "application/json",
                     "Authorization": f"Basic {auth}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Jira search failed: {e.code} {e.reason}") from e
        issues = body.get("issues", [])
        if not isinstance(issues, list):
            raise RuntimeError("Jira search returned a non-list issues field")
        all_issues.extend(issues)
        token = body.get("nextPageToken")
        if not token:
            break
        if not isinstance(token, str):
            raise RuntimeError("Jira search returned an invalid nextPageToken")
        if token in seen_tokens:
            raise RuntimeError("Jira search repeated nextPageToken; pagination aborted")
        seen_tokens.add(token)
        next_token = token
    else:
        raise RuntimeError(
            f"Jira search exceeded the safety limit of {max_pages} pages"
        )
    return all_issues


def _label_op(issue_key: str, op: str, label: str = "ready-for-dispatch") -> None:
    """Add or remove one label via PUT /rest/api/3/issue/{key}.

    op is "add" or "remove". Uses the update.labels[] form so we touch only this
    one label, never rewriting the whole array. Adding an existing / removing an
    absent label is a no-op in Jira, so this is safe to retry.
    """
    import urllib.request
    import urllib.error

    if DRY_RUN:
        log("dry_run_skip", verb=f"label_{op}", issue=issue_key, label=label)
        return
    creds = bridge.load_credentials()
    url = f"{creds['base_url']}/rest/api/3/issue/{issue_key}"
    payload = json.dumps({"update": {"labels": [{op: label}]}}).encode()
    req = urllib.request.Request(
        url, data=payload, method="PUT",
        headers={"Content-Type": "application/json",
                 "Authorization": f"Basic {bridge._basic_auth(creds['user'], creds['api_token'])}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30):
            pass
        log("label_" + op, issue=issue_key, label=label)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"label {op} failed for {issue_key}: {e.code} {e.reason}") from e


def promote_issue(issue_key: str) -> None:
    """Add ready-for-dispatch (the auto-promotion action)."""
    _label_op(issue_key, "add")


def demote_issue(issue_key: str) -> None:
    """Remove ready-for-dispatch (rollback when dispatch fails, item 2)."""
    _label_op(issue_key, "remove")


def dispatch_issue(issue: dict) -> dict:
    """Dispatch one issue via the existing, tested bridge Dispatcher path."""
    creds = bridge.load_credentials()
    jira = bridge.JiraClient(creds["base_url"], creds["user"], creds["api_token"])
    hermes = bridge.HermesClient(logger=bridge.StructuredLogger())
    disp = bridge.Dispatcher(jira=jira, hermes=hermes, logger=bridge.StructuredLogger(),
                             project_key=PROJECT_KEY, limit=1, dry_run=DRY_RUN)
    return disp._process_issue(issue)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def reconcile() -> dict:
    """One full deterministic pass. Returns a summary dict."""
    log("reconcile_start", wip_limit=WIP_LIMIT, board=BOARD)

    active = [t for t in list_tasks() if t.get("status") in ("running", "blocked")]

    # Blocked tasks need reason/kind/crash-count. Running tasks need heartbeat
    # ONLY if reclaim is enabled (otherwise we skip the extra show call).
    for t in active:
        if t.get("status") == "blocked":
            enrich_task(t)
        elif t.get("status") == "running" and RECLAIM_ENABLED:
            enrich_task(t)

    # GATE 3, split two ways:
    #  - credit/402 blocks are account-wide -> suspend ALL refill (global breaker)
    #  - crash/gave-up blocks are per-profile -> skip only that profile
    credit_breaker = any(
        is_hard_block(t) and is_credit_related(t)
        for t in active if t.get("status") == "blocked"
    )
    skip_profiles = blocked_profiles(active)
    if credit_breaker:
        log("credit_breaker_open",
            tasks=[t.get("id") for t in active
                   if t.get("status") == "blocked" and is_credit_related(t)])
    if skip_profiles:
        log("profiles_blocked", profiles=sorted(skip_profiles))

    reclaimed = phase_reclaim(active)

    # Finalize finished review cards BEFORE routing/refill: approvals free the
    # original card and mark Jira Done; rejections re-queue the issue.
    review_tasks = [t for t in list_tasks(status="done") if t.get("title", "").startswith("REVIEW ")]
    # rejected reviews are blocked, not done - enrich + include them
    for t in list_tasks(status="blocked"):
        if t.get("title", "").startswith("REVIEW "):
            enrich_task(t)
            review_tasks.append(t)
    finalized = phase_finalize(review_tasks)

    routed = phase_route(active)

    # Re-read active after routing so refill sees accurate (running-only) WIP.
    active_after = [t for t in list_tasks() if t.get("status") in ("running", "blocked")]
    dispatched = phase_refill(active_after, credit_breaker, skip_profiles)

    summary = {
        "reclaimed": reclaimed,
        "approved": finalized["approved"],
        "reworked": finalized["reworked"],
        "awaiting_merge": finalized["awaiting_merge"],
        "routed": routed,
        "dispatched": dispatched,
        "credit_breaker_open": credit_breaker,
        "blocked_profiles": sorted(skip_profiles),
        "running": len([t for t in active_after if t.get("status") == "running"]),
    }
    log("reconcile_complete", **summary)
    return summary


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="BrandOS deterministic reconcile loop")
    p.add_argument("--dry-run", action="store_true",
                   help="Read board + Jira and log intended actions without any "
                        "hermes create/reclaim or Jira label writes.")
    args = p.parse_args()
    if args.dry_run:
        global DRY_RUN
        DRY_RUN = True
        log("dry_run_enabled")
    try:
        reconcile()
        return 0
    except HermesError as e:
        log("reconcile_hermes_error", error=str(e))
        return 1
    except Exception as e:  # noqa: BLE001
        log("reconcile_unexpected_error", error=str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
