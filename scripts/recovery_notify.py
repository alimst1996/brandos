#!/usr/bin/env python3
"""Telegram escalation notifications for BrandOS recovery supervisor.

Sends structured alerts to Telegram when:
- A task is escalated after rework limit exceeded
- A task is stalled for too long (>7 days)
- Circular dependencies are detected
- WIP limit is reached
- A daily digest of board health

Respects the escalation policy: agents route through brandosorchestrator,
not directly to the Product Owner. Critical alerts go to the PO channel.

Usage (import):
    from recovery_notify import notify_escalation, notify_daily_digest
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from recovery_audit import AuditLogger, redact_dict

audit = AuditLogger("recovery_notify")

# Default escalation channel (Product Owner Telegram)
# Set via env var RECOVERY_NOTIFY_CHANNEL or fall back to empty (no-op)
NOTIFY_CHANNEL = os.environ.get("RECOVERY_NOTIFY_CHANNEL", "")

# Telegram message length limit
TELEGRAM_MAX_LENGTH = 4096


def _format_escalation_message(
    action_results: List[dict],
    board_summary: Optional[dict] = None,
) -> str:
    """Format a structured escalation message for Telegram.

    Args:
        action_results: List of ActionResult dicts with escalation/warning info.
        board_summary: Optional board health summary.

    Returns:
        Formatted Markdown message string.
    """
    lines = ["🚨 *BrandOS Recovery Supervisor — Escalation Alert*", ""]

    # Count outcomes
    escalated = [r for r in action_results if r.get("outcome") == "escalated"]
    failed = [r for r in action_results if r.get("outcome") == "failed"]

    lines.append(f"⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"📊 Escalated: {len(escalated)} | Failed: {len(failed)}")
    lines.append("")

    if escalated:
        lines.append("*Escalated Actions:*")
        for r in escalated[:5]:  # Cap at 5 to avoid message overflow
            task_id = r.get("task_id", "global")
            details = r.get("details", "No details")
            action = r.get("action", "unknown")
            lines.append(f"  • `{action}` — `{task_id}`: {details}")
        if len(escalated) > 5:
            lines.append(f"  ... and {len(escalated) - 5} more")
        lines.append("")

    if failed:
        lines.append("*Failed Actions:*")
        for r in failed[:3]:
            task_id = r.get("task_id", "global")
            details = r.get("details", "No details")
            lines.append(f"  • `{task_id}`: {details}")
        if len(failed) > 3:
            lines.append(f"  ... and {len(failed) - 3} more")
        lines.append("")

    if board_summary:
        wip = board_summary.get("wip", {})
        lines.append(f"*Board Health:*")
        lines.append(f"  WIP: {wip.get('current', '?')}/{wip.get('limit', '?')}")
        if board_summary.get("timed_out"):
            lines.append(f"  Timed out: {len(board_summary['timed_out'])}")
        if board_summary.get("stalled"):
            lines.append(f"  Stalled: {len(board_summary['stalled'])}")
        lines.append("")

    lines.append("⚠️ _Action required: review escalated items and take manual action._")

    return "\n".join(lines)


def _format_daily_digest(plan: dict) -> str:
    """Format a daily health digest for Telegram.

    Args:
        plan: Full recovery plan from build_recovery_plan().

    Returns:
        Formatted Markdown message string.
    """
    wip = plan.get("wip", {})
    lines = [
        "📋 *BrandOS Daily Recovery Digest*",
        "",
        f"⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "*Work In Progress:*",
        f"  Active: {wip.get('current', 0)}/{wip.get('limit', 2)} {'🔴 AT LIMIT' if wip.get('at_limit') else '🟢'}",
        "",
        "*Board Status:*",
        f"  🟢 Healthy running: {len(plan.get('healthy_running', []))}",
        f"  🔵 Ready for dispatch: {len(plan.get('ready_for_dispatch', []))}",
        f"  🟡 Needs review: {len(plan.get('needs_review', []))}",
        f"  🟠 Needs rework: {len(plan.get('needs_rework', [])) + len(plan.get('needs_rework_escalate', []))}",
        f"  🔴 Timed out: {len(plan.get('timed_out_tasks', []))}",
        f"  ⏸️ Stalled: {len(plan.get('stalled_tasks', []))}",
        f"  🚫 Blocked (human): {len(plan.get('blocked_human', []))}",
        f"  🔗 Blocked (dependency): {len(plan.get('blocked_dependency', []))}",
        f"  ⚠️ Stranded: {len(plan.get('stranded', []))}",
    ]

    circular = plan.get("circular_links", [])
    if circular:
        lines.append(f"  🔄 Circular deps: {len(circular)}")

    actions = plan.get("actions_recommended", [])
    if actions:
        lines.append("")
        lines.append(f"*Recommended Actions: {len(actions)}*")
        by_priority = {}
        for a in actions:
            p = a.get("priority", "medium")
            by_priority.setdefault(p, []).append(a)

        if "high" in by_priority:
            lines.append(f"  🔴 High priority: {len(by_priority['high'])}")
            for a in by_priority["high"][:3]:
                lines.append(f"    • {a['action']}: {a.get('reason', '')[:60]}")
        if "medium" in by_priority:
            lines.append(f"  🟡 Medium: {len(by_priority['medium'])}")
    else:
        lines.append("")
        lines.append("✅ No actions recommended — all clear!")

    return "\n".join(lines)


def _send_telegram(message: str, channel: str = "") -> bool:
    """Send a message to Telegram via the Hermes gateway.

    Uses the `hermes send` CLI command if available, otherwise logs
    the message to stdout for manual forwarding.

    Args:
        message: The message text (Markdown formatted).
        channel: Target channel/chat ID. Falls back to NOTIFY_CHANNEL.

    Returns:
        True if sent successfully, False otherwise.
    """
    target = channel or NOTIFY_CHANNEL
    if not target:
        audit.warn("no_notify_channel", message_preview=message[:100])
        return False

    # Truncate if needed
    if len(message) > TELEGRAM_MAX_LENGTH:
        message = message[:TELEGRAM_MAX_LENGTH - 20] + "\n\n_(truncated)_"

    try:
        # Try using hermes send command
        result = subprocess.run(
            ["hermes", "send", "--channel", target, "--message", message],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            audit.info("telegram_sent", channel=target, length=len(message))
            return True
        else:
            audit.warn("telegram_send_failed", error=result.stderr[:200])
            # Fall through to log-only
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        audit.warn("telegram_unavailable", error=str(e))

    # Fallback: log the message for manual forwarding
    audit.info("telegram_message_logged", channel=target, length=len(message))
    return False


def notify_escalation(
    action_results: List[dict],
    board_summary: Optional[dict] = None,
    channel: str = "",
) -> bool:
    """Send escalation notification to Telegram.

    Only sends if there are escalated or failed actions.

    Args:
        action_results: List of ActionResult-like dicts.
        board_summary: Optional board health data.
        channel: Override target channel.

    Returns:
        True if notification was sent/logged.
    """
    escalated = [r for r in action_results if r.get("outcome") in ("escalated", "failed")]
    if not escalated:
        return False

    message = _format_escalation_message(action_results, board_summary)
    return _send_telegram(message, channel=channel)


def notify_daily_digest(plan: dict, channel: str = "") -> bool:
    """Send daily health digest to Telegram.

    Args:
        plan: Full recovery plan from build_recovery_plan().
        channel: Override target channel.

    Returns:
        True if notification was sent/logged.
    """
    message = _format_daily_digest(plan)
    return _send_telegram(message, channel=channel)


if __name__ == "__main__":
    # Demo: format and print a sample escalation message
    sample_results = [
        {"action": "escalate_rework", "task_id": "t_abc123", "outcome": "escalated",
         "details": "Rework limit exceeded (3 cycles)"},
        {"action": "restart_task", "task_id": "t_def456", "outcome": "failed",
         "details": "Task not found in DB"},
    ]
    sample_summary = {"wip": {"current": 2, "limit": 2, "at_limit": True},
                      "timed_out": ["t_abc"], "stalled": ["t_xyz"]}

    print("=== Escalation Message ===")
    print(_format_escalation_message(sample_results, sample_summary))
    print()

    sample_plan = {
        "wip": {"current": 1, "limit": 2, "at_limit": False},
        "healthy_running": ["a", "b"],
        "ready_for_dispatch": ["c"],
        "needs_review": [],
        "needs_rework": ["d"],
        "needs_rework_escalate": [],
        "timed_out_tasks": [],
        "stalled_tasks": [],
        "blocked_human": [],
        "blocked_dependency": ["e"],
        "stranded": [],
        "circular_links": [],
        "actions_recommended": [
            {"action": "promote_stranded", "task_id": "t_xyz", "priority": "medium", "reason": "All parents done"},
        ],
    }
    print("=== Daily Digest ===")
    print(_format_daily_digest(sample_plan))