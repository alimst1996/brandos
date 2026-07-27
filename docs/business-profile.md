# Business Profile API and Storage

## Purpose

Provides CRUD operations and persistent storage for business profiles in
BrandOS. Each profile represents a brand or company and is scoped to a
workspace for multi-tenant isolation.

## Architecture

```
CLI / Python import
       |
       v
BusinessProfileStore  (data access layer)
       |
       v
SQLite (WAL mode, workspace-scoped)
       |
business_profiles table
```

## Data Model

| Field            | Type   | Required | Max Len | Notes                          |
|-----------------|--------|----------|---------|--------------------------------|
| id              | UUID   | auto     | —       | Deterministic v5 (ws + name)   |
| name            | string | yes      | 200     | Brand / company name           |
| industry        | string | no       | 100     | Industry or vertical           |
| description     | string | no       | 2000    | Free-text description          |
| target_audience | string | no       | —       | Target audience description    |
| website         | string | no       | —       | Must start with http(s)://     |
| logo_url        | string | no       | —       | URL to brand logo              |
| workspace_id    | string | yes      | —       | Owning workspace               |
| status          | enum   | auto     | —       | `active` or `archived`         |
| notes           | string | no       | —       | Internal (redacted from logs)  |
| internal_tags   | string | no       | —       | Internal (redacted from logs)  |
| created_at      | ISO8601| auto     | —       | UTC creation timestamp         |
| updated_at      | ISO8601| auto     | —       | UTC last-update timestamp      |

## API (Python)

```python
from business_profile import BusinessProfileStore

store = BusinessProfileStore(db_path="brandos.db", workspace_id="my-ws")

# Create
profile = store.create(name="Acme Corp", industry="Tech")

# Read
profile = store.get(profile_id)
profile = store.get_by_name("Acme Corp")
profiles = store.list(status="active", limit=50, offset=0)

# Update
updated = store.update(profile_id, name="New Name", industry="AI")

# Archive / Restore (soft-delete)
store.archive(profile_id)
store.restore(profile_id)

# Count
count = store.count(status="active")

# Search (LIKE across name, industry, description)
results = store.search("tech", limit=20)

# Export (redacted)
json_str = store.export_json()
```

## CLI

```bash
# Create
python scripts/business_profile.py create --name "Acme" --industry "Tech"

# List
python scripts/business_profile.py list

# Get
python scripts/business_profile.py get <id>

# Update
python scripts/business_profile.py update <id> --name "New Name"

# Archive
python scripts/business_profile.py archive <id>

# Search
python scripts/business_profile.py search "tech"

# Export
python scripts/business_profile.py export
```

CLI flags:
- `--db PATH` — SQLite database path (default: `$BRANDOS_DB_PATH` or `brandos.db`)
- `--workspace ID` — Workspace ID (default: `$BRANDOS_WORKSPACE_ID` or `default`)

## Security

- **Workspace isolation**: All CRUD operations are scoped to the store's
  `workspace_id`. A store for workspace A cannot read, update, or delete
  profiles belonging to workspace B.
- **Redaction**: Sensitive fields (`notes`, `internal_tags`) are redacted in
  log output and JSON exports. The `_RedactingFilter` strips Bearer tokens,
  API keys, and password patterns from all log messages.
- **No credentials in storage**: The module does not store or handle API
  tokens. Credentials belong in environment variables or the Hermes secret
  store, never in the profiles database.

## Idempotency

- **Deterministic IDs**: Profile IDs are UUID v5 derived from
  `(workspace_id, name)`. Creating a profile with the same workspace+name
  twice returns the existing profile without error.
- **Reactivation**: If a profile was archived and a new create is issued
  with the same workspace+name, the archived profile is reactivated rather
  than a new one being inserted.

## Validation

Validation runs on every create and update. Errors are raised as
`ValidationError(field_name, message)`:

- Name: required, 1–200 characters
- Industry: max 100 characters
- Description: max 2000 characters
- Website: must start with `http://` or `https://`
- Status: must be `active` or `archived`
- Workspace ID: required

## Tests

```bash
python -m pytest tests/test_business_profile.py -v
```

Test categories (75 tests):
- **ID generation** (5): determinism, case-insensitive, workspace isolation, format
- **Validation** (11): name, industry, description, website, status, workspace
- **Create** (7): basic, all fields, whitespace, idempotency, validation errors, per-workspace uniqueness
- **Read** (10): get, get_by_name, list active/archived, limit, offset, empty
- **Update** (7): name, multiple fields, nonexistent, invalid field, validation, preserves ID, no-op
- **Archive/Restore** (6): archive, nonexistent, double archive, restore, nonexistent restore, already active
- **Count** (3): active, archived, empty
- **Search** (6): name, industry, description, no results, limit, excludes archived
- **Export** (3): valid JSON, redaction, empty
- **Workspace isolation** (4): cross-workspace read/get/update/archive blocked
- **Redaction** (3): dict redaction, name redaction
- **Edge cases** (7): Unicode, long description, empty DB, concurrent workspaces, special chars, cycle, schema idempotent

## Files

| File                                  | Purpose                          |
|---------------------------------------|----------------------------------|
| `scripts/business_profile.py`         | Store, model, validation, CLI    |
| `tests/test_business_profile.py`      | Test suite (75 tests)            |
| `docs/business-profile.md`            | This documentation               |
