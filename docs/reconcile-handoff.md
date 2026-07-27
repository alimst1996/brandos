# Autopilot Reconcile — Handoff Brief (v3, post second review)

38 reconcile unit tests pass (`python -m pytest tests/test_reconcile.py -v`).
Together with the bridge suite, 140 tests pass. The full
cycle Implement → Review → Rework/Done → Next is now closed. Still: do NOT
switch cron until the acceptance run below passes on the real box.

## Second-review items — status

| # | Item | Status |
|---|------|--------|
| 1 | Pagination re-read page 1 | **Fixed** — `_search_paged` uses the current `/rest/api/3/search/jql` enhanced-search endpoint with guarded `nextPageToken` pagination. The removed `/rest/api/3/search` endpoint is never used. |
| 2 | Issue lost if dispatch fails after label write | **Fixed** — on dispatch failure, `demote_issue` rolls back `ready-for-dispatch` so the issue is re-picked next pass. The create idempotency-key prevents a duplicate if a card was already made. Test `test_dispatch_failure_rolls_back_label`. |
| 3 | Rework cycle incomplete | **Fixed** — `rework-needed` (on the original card OR via a rejected review) removes the dispatch label and archives the stuck card, so refill re-queues the issue. Tests `test_route_rework_requeues_and_archives`, `test_finalize_rejected_review_requeues_issue`. |
| 4 | Review completion unhandled | **Fixed** — `phase_finalize` checks the exact reviewed PR. Low-risk PRs auto-merge only when GitHub reports mergeable and all checks are complete/successful. High-risk, critical, or human-approval work waits for manual merge. Jira moves to Done only after GitHub confirms `MERGED`. |
| 5 | Heartbeat never extracted | **Fixed** — `_parse_last_heartbeat` reads the last `[ts] ... heartbeat` event; running tasks are enriched when reclaim is enabled. Test `test_heartbeat_parsed_from_events`. |
| — | Test import path (`../scripts`) | **Fixed** — tests now try `../scripts` then the flat dir, so they run from `Downloads/files` too. |

## Owner decisions recorded

- **Risk-aware merge.** Low-risk approved/green/mergeable PRs auto-merge.
  High-risk, critical, or human-approval PRs remain manual.
- **Rework is automatic.** A rejected review re-queues the Jira issue.
- **human_approval relaxed** (from v2): low-risk auto-dispatches, high-risk /
  human-approval go to the needs_human report. Owner-approved.

## The full loop (what reconcile() now does each pass)

1. read active (running/blocked), enrich blocked (+running if reclaim on)
2. compute credit breaker (global) + blocked profiles (per-profile)
3. reclaim (off by default; heartbeat-based when on)
4. **finalize** finished review cards: approve→risk/check gate→merge→Jira Done+archive;
   reject→re-queue issue+archive
5. route blocked: review-required→review card; rework-needed→re-queue
6. refill: promote (label) then dispatch, running-only WIP, skip blocked
   profiles, roll back label on dispatch failure

## Still needs YOUR environment to verify (mock-tested only here)

- `hermes kanban create` arg order (assignee/project/body/idempotency-key + positional title)
- `hermes kanban archive <id>` verb behaves as assumed
- Jira PUT label add/remove and transition to "Done" against the live instance
- The exact `blocked {...'reason':'rework-needed'...}` text hermes emits on reject

The reviewed version also fixes two dry-run leaks: `archive` is treated as a
mutating Hermes verb, and `DRY_RUN` is forwarded into the bridge Dispatcher.

## Acceptance before switching cron

1. `python scripts/reconcile.py --dry-run` — confirm intended actions in logs.
2. `BRANDOS_WIP_LIMIT=1 python scripts/reconcile.py` — one live pass, watch a
   review card get created and one issue promote+dispatch.
3. Approve one low-risk review and run once: confirm the PR auto-merges, Jira
   becomes Done, and both original/review cards are archived. Repeat with a
   high-risk fixture and confirm it waits for human approval.
4. Only then: `hermes cron edit f8da63a67f85` → `python scripts/reconcile.py`.

Still a human task: fix why `brandosquality` crashed twice
(`hermes kanban log t_31c05175`).

## Config (env vars)

| Var | Default | Meaning |
|-----|---------|---------|
| `BRANDOS_WIP_LIMIT` | 2 | max concurrent RUNNING tasks |
| `BRANDOS_MAX_FAILURES` | 2 | crash count that hard-blocks a profile |
| `BRANDOS_RECLAIM_ENABLED` | 0 | enable heartbeat-based reclaim (default off) |
| `BRANDOS_STALE_SECONDS` | 14400 | heartbeat-silence threshold when reclaim on |
| `HERMES_KANBAN_BOARD` | brandos | board slug |
| `BRANDOS_PROJECT_KEY` | BOS | Jira project |
