"""Unit tests for scripts/reconcile.py — the deterministic autopilot loop.

These tests mock the hermes CLI (_run_hermes) and Jira fetch so nothing touches
the network or the real board. Fixtures use the EXACT shape of real output that
was observed on the live board:
  - `hermes kanban list --json` rows (id/title/assignee/status/started_at/result)
  - `hermes kanban show <id>` diagnostics carrying consecutive_failures=N + gave_up

Run:  python -m pytest tests/test_reconcile.py -v
"""
from __future__ import annotations

import json
import os
import sys
import time

import pytest

# Import reconcile regardless of where this test file lives: try ../scripts
# first (repo layout), then the same directory (flat layout, e.g. Downloads).
_here = os.path.dirname(os.path.abspath(__file__))
for _cand in (os.path.join(_here, "..", "scripts"), _here):
    if os.path.exists(os.path.join(_cand, "reconcile.py")):
        sys.path.insert(0, _cand)
        break
import reconcile as R  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures — real-shaped data
# ---------------------------------------------------------------------------

def _blocked_list_rows():
    """Two real blocked rows as returned by `hermes kanban list --json`."""
    return [
        {
            "id": "t_31c05175",
            "title": "BOS-21 - Fresh independent review of closed PR #9",
            "assignee": "brandosquality", "status": "blocked",
            "priority": 160, "started_at": 1785138958, "result": None,
        },
        {
            "id": "t_c51fed14",
            "title": "BOS-21 - Fresh rebase continuation for closed PR #6",
            "assignee": "brandosbackend", "status": "blocked",
            "priority": 150, "started_at": 1785104724, "result": None,
        },
    ]


SHOW_CRASHED = (
    "Task t_31c05175: BOS-21 - Fresh independent review of closed PR #9\n"
    "  status:    blocked\n"
    "  Diagnostics (1):\n"
    "    !! [error] Agent crash x2: pid 2532 not alive\n"
    "       data: consecutive_failures=2 | most_recent_outcome=crashed | "
    "last_error=pid 2532 not alive | failure_threshold=2 | failure_limit=2\n"
    "  Events (18):\n"
    "  [2026-07-27 10:04] gave_up {'failures': 2, 'effective_limit': 2}\n"
)

SHOW_REVIEW_READY = (
    "Task t_c51fed14: BOS-21 - Fresh rebase continuation for closed PR #6\n"
    "  status:    blocked\n"
    "  Latest summary:\n"
    "  review-required: PR #9 ready for merge - all quality gates pass.\n"
    "  Events (45):\n"
    "  [2026-07-27 01:04] blocked {'reason': 'review-required: PR #9 ready', "
    "'kind': 'needs_input', 'recurrences': 1}\n"
)

SHOW_CREDIT_402 = (
    "Task t_x: some task\n  status: blocked\n"
    "  Diagnostics (1):\n"
    "    !! [error] provider returned HTTP 402 insufficient credit\n"
    "       data: consecutive_failures=0 | most_recent_outcome=error\n"
)


def make_hermes(list_payload, show_map=None):
    """Build a fake _run_hermes returning canned list/show output."""
    show_map = show_map or {}

    def fake(args, timeout=60):
        if args[:2] == ["list", "--json"]:
            return json.dumps(list_payload)
        if args and args[0] == "show":
            return show_map.get(args[1], "status: blocked")
        if args and args[0] in ("reclaim", "create", "comment"):
            return ""  # side-effect commands succeed silently
        return "[]"

    return fake


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Never hit Jira in these tests unless a test opts in."""
    monkeypatch.setattr(R, "fetch_backlog_issues", lambda: [])
    yield


# ---------------------------------------------------------------------------
# GATE 3 — hard-block breaker
# ---------------------------------------------------------------------------

def test_gave_up_is_hard_block():
    t = {"_gave_up": True, "_failed_runs": 2}
    assert R.is_hard_block(t) is True


def test_crash_loop_is_hard_block():
    t = {"_gave_up": False, "_failed_runs": R.MAX_CONSECUTIVE_FAILURES}
    assert R.is_hard_block(t) is True


def test_credit_402_is_hard_block():
    t = {"_gave_up": False, "_failed_runs": 0, "_block_detail": "http 402 insufficient credit"}
    assert R.is_hard_block(t) is True
    assert R.is_credit_related(t) is True


def test_single_failure_is_not_hard_block():
    t = {"_gave_up": False, "_failed_runs": 1, "_block_detail": "transient timeout"}
    assert R.is_hard_block(t) is False


def test_crash_block_is_per_profile_not_credit():
    """A crash on brandosquality blocks only that profile, not all refill."""
    t = {"status": "blocked", "assignee": "brandosquality",
         "_gave_up": True, "_failed_runs": 2, "_block_detail": "crash x2 pid not alive"}
    assert R.is_credit_related(t) is False
    assert R.blocked_profiles([t]) == {"brandosquality"}


def test_credit_block_does_not_appear_in_blocked_profiles():
    """Credit blocks are global (handled by credit_breaker), not per-profile."""
    t = {"status": "blocked", "assignee": "brandosbackend",
         "_gave_up": False, "_failed_runs": 0, "_block_detail": "402 insufficient credit"}
    assert R.blocked_profiles([t]) == set()


def test_review_block_creates_card_with_positional_title(monkeypatch):
    """Regression: create takes title POSITIONALLY, not via --title."""
    captured = {}
    def fake(args, timeout=60):
        if args and args[0] == "create":
            captured["args"] = args
        return ""
    monkeypatch.setattr(R, "_run_hermes", fake)
    t = {"id": "t_c5", "status": "blocked", "assignee": "brandosbackend",
         "title": "BOS-21 - work", "_block_kind": "review-required",
         "_gave_up": False, "_failed_runs": 0, "_block_detail": "review-required: ready"}
    n = R.phase_route([t])
    assert n == 1
    args = captured["args"]
    assert "--title" not in args              # title must NOT be a flag
    assert args[-1].startswith("REVIEW ")     # title is the last positional arg
    assert "--idempotency-key" in args        # dedup guard present


def test_breaker_suspends_refill(monkeypatch):
    """A credit block must open the credit breaker and stop refill."""
    rows = _blocked_list_rows()
    monkeypatch.setattr(R, "_run_hermes", make_hermes(
        rows, {"t_31c05175": SHOW_CREDIT_402, "t_c51fed14": SHOW_REVIEW_READY}))
    monkeypatch.setattr(R, "fetch_backlog_issues",
                        lambda: (_ for _ in ()).throw(AssertionError("refill ran!")))
    summary = R.reconcile()
    assert summary["credit_breaker_open"] is True
    assert summary["dispatched"] == 0


# ---------------------------------------------------------------------------
# enrich_task — parsing the real show output
# ---------------------------------------------------------------------------

def test_enrich_parses_consecutive_failures(monkeypatch):
    monkeypatch.setattr(R, "_run_hermes", make_hermes([], {"t_31c05175": SHOW_CRASHED}))
    t = {"id": "t_31c05175", "status": "blocked"}
    R.enrich_task(t)
    assert t["_failed_runs"] == 2
    assert t["_gave_up"] is True


def test_enrich_parses_review_block_kind(monkeypatch):
    monkeypatch.setattr(R, "_run_hermes", make_hermes([], {"t_c51fed14": SHOW_REVIEW_READY}))
    t = {"id": "t_c51fed14", "status": "blocked"}
    R.enrich_task(t)
    assert t["_block_kind"] == "review-required"
    assert t["_failed_runs"] == 0
    assert t["_gave_up"] is False
    assert R.is_hard_block(t) is False


# ---------------------------------------------------------------------------
# GATE 1 — readiness classification
# ---------------------------------------------------------------------------

def _issue(key, labels, desc, links=None):
    return {"key": key, "fields": {"labels": labels, "description": desc,
                                    "issuelinks": links or [], "status": {"name": "Backlog"}}}


GOOD_DESC = (
    "### Goal\nBuild it.\n### Acceptance Criteria\n* works\n"
    "### Required Tests\nunit tests\n### Security\nnone\nbackend module service\n"
)
REQUIRED_LABELS = ["role-backend", "review-by-agent-quality", "risk-low",
                   "phase-x", "points-3", "ver-0.2-x"]


def test_low_risk_complete_issue_is_auto():
    issue = _issue("BOS-1", ["agent-backend", *REQUIRED_LABELS], GOOD_DESC)
    bucket, _ = R.classify_issue(issue)
    assert bucket == "ready_auto"


def test_high_risk_goes_to_human():
    labels = ["agent-backend", "role-backend", "review-by-agent-quality",
              "risk-high", "phase-x", "points-3", "ver-0.2-x", "human-approval-required"]
    issue = _issue("BOS-2", labels, GOOD_DESC)
    bucket, _ = R.classify_issue(issue)
    assert bucket == "needs_human"


def test_missing_acceptance_criteria_is_not_ready():
    issue = _issue("BOS-3", ["agent-backend", *REQUIRED_LABELS],
                   "### Goal\nno criteria here\n")
    bucket, reasons = R.classify_issue(issue)
    assert bucket == "not_ready"
    assert any("acceptance_criteria" in r for r in reasons)


def test_unresolved_blocker_is_not_ready():
    links = [{"type": {"inward": "is blocked by"},
              "inwardIssue": {"key": "BOS-99", "fields": {"status": {"name": "Backlog"}}}}]
    issue = _issue("BOS-4", ["agent-backend", *REQUIRED_LABELS], GOOD_DESC, links)
    bucket, reasons = R.classify_issue(issue)
    assert bucket == "not_ready"
    assert any("dependency_links" in r for r in reasons)


def test_outward_blocks_link_does_not_crash():
    """Regression: outward-only Blocks links used to KeyError in readiness."""
    links = [{"type": {"inward": "is blocked by"},
              "outwardIssue": {"key": "BOS-88", "fields": {"status": {"name": "Backlog"}}}}]
    issue = _issue("BOS-5", ["agent-backend", *REQUIRED_LABELS], GOOD_DESC, links)
    bucket, _ = R.classify_issue(issue)  # must not raise
    assert bucket == "ready_auto"


# ---------------------------------------------------------------------------
# GATE 2 — WIP ceiling
# ---------------------------------------------------------------------------

def test_refill_ignores_blocked_in_wip(monkeypatch):
    """Blocked/review tasks hold no worker, so they must NOT consume a slot."""
    monkeypatch.setattr(R, "_run_hermes", make_hermes([]))
    ready = [_issue(f"BOS-{i}", ["agent-backend", *REQUIRED_LABELS], GOOD_DESC)
             for i in range(10)]
    monkeypatch.setattr(R, "fetch_backlog_issues", lambda: ready)
    monkeypatch.setattr(R, "promote_issue", lambda k: None)
    disp = []
    monkeypatch.setattr(R, "dispatch_issue", lambda i: disp.append(i["key"]))
    # 2 blocked + 0 running: capacity should be full WIP_LIMIT (blocked ignored)
    active = [{"id": "b1", "status": "blocked"}, {"id": "b2", "status": "blocked"}]
    dispatched = R.phase_refill(active, credit_breaker_open=False)
    assert dispatched == R.WIP_LIMIT


def test_refill_respects_running_wip_when_full(monkeypatch):
    monkeypatch.setattr(R, "_run_hermes", make_hermes([]))
    active = [{"id": "a", "status": "running"}, {"id": "b", "status": "running"}]
    dispatched = R.phase_refill(active, credit_breaker_open=False)
    assert dispatched == 0


def test_refill_skips_blocked_profile(monkeypatch):
    """Issues routed to a crash-blocked profile are skipped; others flow."""
    monkeypatch.setattr(R, "_run_hermes", make_hermes([]))
    ready = [
        _issue("BOS-1", ["agent-quality", *REQUIRED_LABELS], GOOD_DESC),   # blocked profile
        _issue("BOS-2", ["agent-backend", *REQUIRED_LABELS], GOOD_DESC),   # ok
    ]
    monkeypatch.setattr(R, "fetch_backlog_issues", lambda: ready)
    monkeypatch.setattr(R, "promote_issue", lambda k: None)
    disp = []
    monkeypatch.setattr(R, "dispatch_issue", lambda i: disp.append(i["key"]))
    R.phase_refill(active=[], credit_breaker_open=False,
                   skip_profiles={"brandosquality"})
    assert "BOS-2" in disp
    assert "BOS-1" not in disp  # agent-quality -> brandosquality is skipped


# ---------------------------------------------------------------------------
# phase_reclaim — stale running tasks
# ---------------------------------------------------------------------------

def test_reclaim_disabled_by_default(monkeypatch):
    """With RECLAIM_ENABLED off, reconcile never reclaims - hermes owns liveness."""
    monkeypatch.setattr(R, "RECLAIM_ENABLED", False)
    called = []
    monkeypatch.setattr(R, "_run_hermes", lambda a, timeout=60: called.append(a) or "[]")
    old = {"id": "x", "status": "running", "_last_heartbeat_ts": int(time.time()) - 99999}
    assert R.phase_reclaim([old]) == 0
    assert not any(a and a[0] == "reclaim" for a in called)


def test_reclaim_only_silent_when_enabled(monkeypatch):
    """When enabled, reclaim only fires on tasks silent past the threshold."""
    monkeypatch.setattr(R, "RECLAIM_ENABLED", True)
    reclaimed = []
    def fake(args, timeout=60):
        if args and args[0] == "reclaim":
            reclaimed.append(args[1])
        return "[]"
    monkeypatch.setattr(R, "_run_hermes", fake)
    silent = {"id": "silent", "status": "running",
              "_last_heartbeat_ts": int(time.time()) - (R.STALE_AFTER_SECONDS + 60)}
    alive = {"id": "alive", "status": "running",
             "_last_heartbeat_ts": int(time.time()) - 30}
    unknown = {"id": "unknown", "status": "running"}  # no heartbeat info -> skip
    n = R.phase_reclaim([silent, alive, unknown])
    assert n == 1
    assert reclaimed == ["silent"]


def test_promote_runs_before_dispatch(monkeypatch):
    """Item 4: label must be written BEFORE dispatch so a crash between the two
    can't cause a re-dispatch on the next cron pass."""
    monkeypatch.setattr(R, "_run_hermes", make_hermes([]))
    order = []
    monkeypatch.setattr(R, "promote_issue", lambda k: order.append(f"promote:{k}"))
    monkeypatch.setattr(R, "dispatch_issue", lambda i: order.append(f"dispatch:{i['key']}"))
    monkeypatch.setattr(R, "fetch_backlog_issues",
                        lambda: [_issue("BOS-1", ["agent-backend", *REQUIRED_LABELS], GOOD_DESC)])
    R.phase_refill(active=[], credit_breaker_open=False)
    assert order == ["promote:BOS-1", "dispatch:BOS-1"]


def test_full_cycle_blocked_review_then_refill(monkeypatch):
    """End-to-end: a review-blocked task is routed to a review card, and refill
    still dispatches new backend work (blocked task doesn't consume a slot)."""
    rows = [{"id": "t_rev", "title": "BOS-21 - work", "assignee": "brandosbackend",
             "status": "blocked", "priority": 150, "started_at": 1785104724, "result": None}]
    created = []
    def fake(args, timeout=60):
        if args[:2] == ["list", "--json"]:
            return json.dumps(rows)
        if args and args[0] == "show":
            return SHOW_REVIEW_READY
        if args and args[0] == "create":
            created.append(args)
        return "[]"
    monkeypatch.setattr(R, "_run_hermes", fake)
    disp = []
    monkeypatch.setattr(R, "promote_issue", lambda k: None)
    monkeypatch.setattr(R, "dispatch_issue", lambda i: disp.append(i["key"]))
    monkeypatch.setattr(R, "fetch_backlog_issues",
                        lambda: [_issue("BOS-2", ["agent-backend", *REQUIRED_LABELS], GOOD_DESC)])
    summary = R.reconcile()
    # review card created, no breaker, backend work dispatched
    assert summary["credit_breaker_open"] is False
    assert summary["routed"] == 1
    assert any(a[0] == "create" for a in created)
    assert "BOS-2" in disp


# ---------------------------------------------------------------------------
# --dry-run — mutating verbs are skipped
# ---------------------------------------------------------------------------

def test_dry_run_skips_mutating_verbs(monkeypatch):
    """Under DRY_RUN, create/reclaim return '' without touching subprocess."""
    monkeypatch.setattr(R, "DRY_RUN", True)
    ran = []
    monkeypatch.setattr(R.subprocess, "run",
                        lambda *a, **k: ran.append(a) or type("X", (), {"returncode": 0, "stdout": "[]"})())
    # mutating verb -> skipped, subprocess.run never called
    assert R._run_hermes(["create", "x"]) == ""
    assert ran == []
    # read verb -> executes
    R._run_hermes(["list", "--json"])
    assert len(ran) == 1


def test_dry_run_promote_writes_nothing(monkeypatch):
    monkeypatch.setattr(R, "DRY_RUN", True)
    monkeypatch.setattr(R.bridge, "load_credentials",
                        lambda: {"base_url": "https://x", "user": "u", "api_token": "t"})
    # if it tried to open a URL this would raise; dry-run must return early
    R.promote_issue("BOS-1")


def test_dry_run_is_forwarded_to_bridge_dispatcher(monkeypatch):
    seen = {}

    class FakeDispatcher:
        def __init__(self, **kwargs):
            seen["dry_run"] = kwargs["dry_run"]

        def _process_issue(self, issue):
            seen["issue"] = issue["key"]

    monkeypatch.setattr(
        R.bridge, "load_credentials",
        lambda: {"base_url": "https://x", "user": "u", "api_token": "t"},
    )
    monkeypatch.setattr(R.bridge, "JiraClient", lambda *a, **k: object())
    monkeypatch.setattr(R.bridge, "HermesClient", lambda *a, **k: object())
    monkeypatch.setattr(R.bridge, "StructuredLogger", lambda *a, **k: object())
    monkeypatch.setattr(R.bridge, "Dispatcher", FakeDispatcher)
    monkeypatch.setattr(R, "DRY_RUN", True)
    R.dispatch_issue({"key": "BOS-1"})
    assert seen == {"dry_run": True, "issue": "BOS-1"}


# ---------------------------------------------------------------------------
# phase_finalize — closing the review loop (items 3 & 4)
# ---------------------------------------------------------------------------

def test_finalize_approved_review_marks_jira_done(monkeypatch):
    """A done REVIEW card closes Jira only after GitHub confirms the merge."""
    calls = []
    def fake_hermes(a, timeout=60):
        calls.append(a)
        if a[0] == "show":
            return "Body:\nOriginal task: t_original\nPR #9\n"
        return ""
    monkeypatch.setattr(R, "_run_hermes", fake_hermes)
    monkeypatch.setattr(R, "_pr_is_merged", lambda n: n == 9)
    monkeypatch.setattr(R, "_jira_transition",
                        lambda k, s: calls.append(("jira", k, s)))
    review = [{"id": "t_rev", "title": "REVIEW BOS-21 - work PR #9",
               "status": "done"}]
    out = R.phase_finalize(review)
    assert out["approved"] == 1
    assert ("jira", "BOS-21", "Done") in calls
    assert ["archive", "t_original"] in calls
    assert ["archive", "t_rev"] in calls


def test_finalize_high_risk_approved_but_unmerged_waits(monkeypatch):
    """High-risk quality approval still waits for a human merge."""
    calls = []
    monkeypatch.setattr(
        R, "_run_hermes",
        lambda a, timeout=60: calls.append(a) or "PR #9\nOriginal task: t_original",
    )
    monkeypatch.setattr(R, "_pr_is_merged", lambda n: False)
    monkeypatch.setattr(R, "_jira_issue_labels", lambda k: {"risk-high"})
    monkeypatch.setattr(
        R, "_jira_transition",
        lambda *a: pytest.fail("must not transition Jira before merge"),
    )
    out = R.phase_finalize([
        {"id": "t_rev", "title": "REVIEW BOS-21 - work PR #9", "status": "done"}
    ])
    assert out == {"approved": 0, "reworked": 0, "awaiting_merge": 1}
    assert not any(a[0] == "archive" for a in calls if isinstance(a, list))


def test_finalize_low_risk_auto_merges_then_closes(monkeypatch):
    calls = []
    merge_checks = iter([False, True])
    monkeypatch.setattr(
        R, "_run_hermes",
        lambda a, timeout=60: calls.append(a) or "PR #9\nOriginal task: t_original",
    )
    monkeypatch.setattr(R, "_pr_is_merged", lambda n: next(merge_checks))
    monkeypatch.setattr(R, "_jira_issue_labels", lambda k: {"risk-low"})
    monkeypatch.setattr(R, "_pr_is_safe_to_merge", lambda n: True)
    monkeypatch.setattr(R, "_merge_pr", lambda n: calls.append(("merge", n)))
    monkeypatch.setattr(
        R, "_jira_transition",
        lambda k, s: calls.append(("jira", k, s)),
    )
    out = R.phase_finalize([
        {"id": "t_rev", "title": "REVIEW BOS-21 - work PR #9", "status": "done"}
    ])
    assert out["approved"] == 1
    assert ("merge", 9) in calls
    assert ("jira", "BOS-21", "Done") in calls


def test_finalize_rejected_review_requeues_issue(monkeypatch):
    """A rework-needed REVIEW card -> remove dispatch label + archive card."""
    demoted = []
    monkeypatch.setattr(R, "demote_issue", lambda k: demoted.append(k))
    monkeypatch.setattr(R, "_run_hermes", lambda a, timeout=60: "")
    review = [{"id": "t_rev", "title": "REVIEW BOS-21 - work",
               "status": "blocked", "_block_kind": "rework-needed"}]
    out = R.phase_finalize(review)
    assert out["reworked"] == 1
    assert demoted == ["BOS-21"]


def test_finalize_ignores_non_review_cards(monkeypatch):
    monkeypatch.setattr(R, "_run_hermes", lambda a, timeout=60: "")
    out = R.phase_finalize([{"id": "x", "title": "BOS-9 - normal", "status": "done"}])
    assert out == {"approved": 0, "reworked": 0, "awaiting_merge": 0}


def test_route_rework_requeues_and_archives(monkeypatch):
    """Item 3: a rework-needed block on the ORIGINAL card re-queues the issue."""
    demoted, archived = [], []
    monkeypatch.setattr(R, "demote_issue", lambda k: demoted.append(k))
    def fake(a, timeout=60):
        if a and a[0] == "archive":
            archived.append(a[1])
        return ""
    monkeypatch.setattr(R, "_run_hermes", fake)
    t = {"id": "t1", "status": "blocked", "title": "BOS-30 - x",
         "_block_kind": "rework-needed", "_gave_up": False, "_failed_runs": 0,
         "_block_detail": "rework-needed: fix tests"}
    R.phase_route([t])
    assert demoted == ["BOS-30"]
    assert archived == ["t1"]


def test_route_rework_keeps_card_if_jira_requeue_fails(monkeypatch):
    archived = []
    monkeypatch.setattr(
        R, "demote_issue",
        lambda k: (_ for _ in ()).throw(RuntimeError("Jira unavailable")),
    )
    monkeypatch.setattr(
        R, "_run_hermes",
        lambda a, timeout=60: archived.append(a) or "",
    )
    task = {
        "id": "t1", "status": "blocked", "title": "BOS-30 - x",
        "_block_kind": "rework-needed", "_gave_up": False, "_failed_runs": 0,
        "_block_detail": "rework-needed",
    }
    assert R.phase_route([task]) == 0
    assert ["archive", "t1"] not in archived


# ---------------------------------------------------------------------------
# item 2 — dispatch failure rolls back the promotion
# ---------------------------------------------------------------------------

def test_dispatch_failure_rolls_back_label(monkeypatch):
    monkeypatch.setattr(R, "_run_hermes", make_hermes([]))
    monkeypatch.setattr(R, "promote_issue", lambda k: None)
    demoted = []
    monkeypatch.setattr(R, "demote_issue", lambda k: demoted.append(k))
    def boom(issue):
        raise RuntimeError("dispatch exploded")
    monkeypatch.setattr(R, "dispatch_issue", boom)
    monkeypatch.setattr(R, "fetch_backlog_issues",
                        lambda: [_issue("BOS-1", ["agent-backend", *REQUIRED_LABELS], GOOD_DESC)])
    R.phase_refill(active=[], credit_breaker_open=False)
    assert demoted == ["BOS-1"]  # label rolled back so issue isn't lost


# ---------------------------------------------------------------------------
# item 5 — heartbeat is actually parsed
# ---------------------------------------------------------------------------

def test_heartbeat_parsed_from_events(monkeypatch):
    import datetime
    recent = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    show = f"Task t: x\n  status: running\n  Events (3):\n  [{recent}] [run 5] heartbeat\n"
    monkeypatch.setattr(R, "_run_hermes", make_hermes([], {"t": show}))
    t = {"id": "t", "status": "running"}
    R.enrich_task(t)
    assert t["_last_heartbeat_ts"] is not None
    age = R._last_heartbeat_age(t)
    assert age is not None and age < 120  # within ~2 min


# ---------------------------------------------------------------------------
# Jira Cloud enhanced search contract
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self._payload


def test_search_uses_enhanced_endpoint_and_next_page_token(monkeypatch):
    import urllib.request

    requests = []
    pages = [
        {"issues": [{"key": "BOS-1"}], "nextPageToken": "next-1"},
        {"issues": [{"key": "BOS-2"}]},
    ]

    def fake_open(request, timeout=30):
        requests.append(request)
        return _FakeResponse(pages[len(requests) - 1])

    monkeypatch.setattr(urllib.request, "urlopen", fake_open)
    issues = R._search_paged(
        {"base_url": "https://example.atlassian.net", "user": "u", "api_token": "t"},
        "project = BOS",
    )
    assert [item["key"] for item in issues] == ["BOS-1", "BOS-2"]
    assert all(req.full_url.endswith("/rest/api/3/search/jql") for req in requests)
    first = json.loads(requests[0].data)
    second = json.loads(requests[1].data)
    assert "startAt" not in first
    assert "nextPageToken" not in first
    assert second["nextPageToken"] == "next-1"


def test_search_aborts_on_repeated_next_page_token(monkeypatch):
    import urllib.request

    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda request, timeout=30: _FakeResponse(
            {"issues": [{"key": "BOS-1"}], "nextPageToken": "same"}
        ),
    )
    with pytest.raises(RuntimeError, match="repeated nextPageToken"):
        R._search_paged(
            {"base_url": "https://example.atlassian.net", "user": "u", "api_token": "t"},
            "project = BOS",
        )
