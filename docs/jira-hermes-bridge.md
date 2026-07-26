# Jira-to-Hermes Task Bridge

## Purpose

Automates the dispatch of eligible Jira issues to Hermes Kanban as agent-specific
worktree tasks, with full idempotency, credential safety, and structured logging.

## Architecture

```
Jira (BOS project)
   |
   | REST API v3  ← JQL: ready-for-dispatch AND not In Progress/Done
   v
jira_hermes_bridge.py
   |
   ├── 1. Eligibility filter (labels, block labels, agent labels, blockers)
   ├── 2. Label → profile mapping (agent-backend → brandosbackend, etc.)
   ├── 3. Bounded context builder (description sections, labels, deps)
   ├── 4. Idempotency check (jira:<KEY> → existing Hermes task?)
   ├── 5. Task creation (Hermes kanban create, worktree, project)
   └── 6. Jira update (comment + transition to In Progress)
   |
   v
Hermes Kanban (ai-marketing-vibe project, isolated worktree branch)
```

## Eligibility Rules

An issue is eligible for dispatch when ALL conditions are met:
1. `ready-for-dispatch` label is present
2. No block labels: `do-not-dispatch-yet`, `status-blocked`, `deferred-scope`
3. Exactly one `agent-*` label present
4. Agent label maps to a known Hermes profile
5. All `is blocked by` links are resolved (Done/Resolved/Closed)

## Agent Label → Profile Mapping

| Jira Label        | Hermes Profile      |
|-------------------|---------------------|
| agent-backend     | brandosbackend      |
| agent-frontend    | brandosfrontend     |
| agent-intelligence| brandosintelligence |
| agent-social      | brandossocial       |
| agent-quality     | brandosquality      |
| agent-preview     | brandospreview      |
| agent-orchestrator| brandosorchestrator |

## Usage

```bash
# Dry run (no Jira modifications, no Heremes tasks created)
python scripts/jira_hermes_bridge.py --dry-run

# Production run
python scripts/jira_hermes_bridge.py

# With options
python scripts/jira_hermes_bridge.py --project-key BOS --limit 10 --verbose
```

## Environment Variables

| Variable         | Required | Description                   |
|-----------------|----------|-------------------------------|
| `JIRA_BASE_URL` | Yes      | Jira instance URL             |
| `JIRA_USER`     | Yes      | Jira user email               |
| `JIRA_API_TOKEN`| Yes      | Jira API token (never logged) |
| `HERMES_KANBAN_DB`| No     | Path to kanban SQLite DB      |

**Credentials are loaded ONLY from environment variables.** Never commit tokens,
chat IDs, emails, or local secret files.

## Security

- All log output is filtered through `RedactingFilter` — tokens, API keys,
  passwords, and auth headers are replaced with `[REDACTED]` before printing.
- `redact_dict()` strips sensitive keys from any dict before logging.
- API credentials are loaded from `os.environ` only — no config files, no defaults.
- Failed dispatches record a Jira comment with error details but no credentials.

## Idempotency

The bridge uses `jira:<ISSUE-KEY>` as the idempotency key when creating Hermes
tasks. If a task with that key already exists (status != archived), the issue
is skipped without creating a duplicate. This is checked directly against the
kanban SQLite database.

## Failure Handling

- **Jira API failure**: `JiraApiError` is raised; the cycle aborts.
- **Single issue failure**: Logged and recorded as a Jira comment; other issues
  continue processing.
- **Hermes task creation failure**: A readable comment is written to the Jira
  issue, and the issue remains in its current status (not transitioned).

## Tests

```bash
# Run all bridge tests (72 tests) + readiness tests (41 tests)
python -m pytest tests/ -v

# Run bridge tests only
python -m pytest tests/test_bridge.py -v
```

Test categories:
- **Eligibility** (12 tests): label checks, block labels, agent labels, blockers
- **Label→Profile mapping** (11 tests): all 7 mappings, determinism, uniqueness
- **Branch derivation** (4 tests): determinism, special chars, length
- **Bounded context** (7 tests): sections, ADF, deps, scope, no vision leakage
- **Redaction** (5 tests): tokens, nested dicts, API key variants, auth headers
- **Dispatcher** (8 tests): dispatch, skip, duplicate, failure, dry-run, Jira updates
- **Idempotency** (2 tests): key format, duplicate suppression
- **Dependency resolution** (7 tests): Done/Closed/Resolved pass, To Do/In Progress fail
- **Failure handling** (2 tests): Jira error propagation, resilience across issues
- **Credentials** (3 tests): missing BASE_URL, USER, API_TOKEN
- **Integration boundaries** (4 tests): Jira adapter, Hermes adapter
- **CLI** (4 tests): help, missing env, flags
- **Edge cases** (6 tests): empty, missing keys, None, Unicode, full coverage

## Files

| File | Purpose |
|------|---------|
| `scripts/jira_hermes_bridge.py` | Main bridge script |
| `tests/test_bridge.py` | Comprehensive test suite |
| `tests/fixtures/bridge_test_issue.json` | Safe dry-run E2E fixture |
| `docs/jira-hermes-bridge.md` | This documentation |