# Brand Store API and Versioning

**Task:** BOS-73 / BRAND-006
**Status:** Complete
**Last Updated:** 2026-07-27

## Purpose

Provides CRUD operations, full version history, diff, and rollback for brand
profiles in BrandOS. Every update creates an immutable version snapshot,
enabling complete audit trail and time-travel queries.

Each brand is workspace-scoped and audit-logged with redaction of sensitive
fields.

## Architecture

```
CLI / Python import
       |
       v
  BrandStore  (data access layer, workspace-scoped)
       |
       v
  SQLite (WAL mode, foreign keys)
       |
  +---------+-----------+
  | brands  | brand_versions |
  +---------+-----------+
```

## Data Model

| Field             | Type     | Required | Max Len | Notes                          |
|-------------------|----------|----------|---------|--------------------------------|
| id                | UUID     | auto     | —       | Deterministic v5 (ws + name)   |
| name              | string   | yes      | 200     | Brand name                     |
| industry          | string   | no       | 100     | Industry or vertical           |
| tagline           | string   | no       | 300     | Short brand tagline            |
| description       | string   | no       | 5000    | Free-text description          |
| tone              | string   | no       | 100     | Brand tone of voice            |
| personality       | string   | no       | —       | Comma-separated traits         |
| values            | string   | no       | —       | Comma-separated values         |
| target_audience   | string   | no       | —       | Target audience description    |
| website           | string   | no       | —       | Must start with http(s)://     |
| logo_url          | string   | no       | —       | URL to brand logo              |
| color_primary     | hex      | no       | 7       | e.g. `#FF0000`                 |
| color_secondary   | hex      | no       | 7       | e.g. `#00FF00`                 |
| prohibited_terms  | string   | no       | —       | Comma-separated banned words   |
| workspace_id      | string   | yes      | —       | Owning workspace               |
| status            | enum     | auto     | —       | `active` or `archived`         |
| version           | integer  | auto     | —       | Current version (1-based)      |
| internal_notes    | string   | no       | —       | Redacted from logs/exports     |
| internal_tags     | string   | no       | —       | Redacted from logs/exports     |
| created_at        | ISO8601  | auto     | —       | UTC creation timestamp         |
| updated_at        | ISO8601  | auto     | —       | UTC last-update timestamp      |

## Version History

Every update creates an immutable version snapshot in `brand_versions`:

| Field           | Type    | Notes                                |
|-----------------|---------|--------------------------------------|
| id              | integer | Auto-increment                       |
| brand_id        | UUID    | FK to brands                         |
| version         | integer | Sequential (1, 2, 3, ...)            |
| snapshot        | JSON    | Full brand state at this version     |
| changed_fields  | string  | Comma-separated list of changes      |
| created_at      | ISO8601 | When this version was created        |

### Versioned Fields

Only these fields are tracked for change detection:
`name`, `industry`, `tagline`, `description`, `tone`, `personality`,
`values`, `target_audience`, `website`, `logo_url`, `color_primary`,
`color_secondary`, `prohibited_terms`

## API (Python)

```python
from brand_store import BrandStore

store = BrandStore(db_path="brandos.db", workspace_id="my-ws")

# Create (idempotent — same name returns existing brand)
brand = store.create(name="Acme Corp", industry="Tech", tagline="We build")

# Read
brand = store.get(brand_id)
brand = store.get_by_name("Acme Corp")
brands = store.list(status="active", limit=50, offset=0)
results = store.search("Acme", limit=20)
count = store.count(status="active")

# Update (creates new version snapshot)
updated = store.update(brand_id, tagline="New tagline", tone="casual")

# Archive / Restore (soft-delete)
store.archive(brand_id)
store.restore(brand_id)

# Export (sensitive fields redacted)
json_str = store.export_json(status="active")

# Versioning
versions = store.list_versions(brand_id)
version = store.get_version(brand_id, 2)
total = store.get_version_count(brand_id)
diff = store.diff_versions(brand_id, from_version=1, to_version=3)

# Rollback (creates new version with target version's data)
rolled = store.rollback(brand_id, to_version=1)
```

## CLI

```bash
# Create
python scripts/brand_store.py --db brandos.db create --name "Acme" --industry "Tech"

# List
python scripts/brand_store.py --db brandos.db list --status active --limit 50

# Get
python scripts/brand_store.py --db brandos.db get <id>

# Update
python scripts/brand_store.py --db brandos.db update <id> --tagline "New"

# Archive / Restore
python scripts/brand_store.py --db brandos.db archive <id>
python scripts/brand_store.py --db brandos.db restore <id>

# Search
python scripts/brand_store.py --db brandos.db search "Acme"

# Export
python scripts/brand_store.py --db brandos.db export

# Versions
python scripts/brand_store.py --db brandos.db versions <id>
python scripts/brand_store.py --db brandos.db get-version <id> --version 2
python scripts/brand_store.py --db brandos.db diff <id> --from 1 --to 3
python scripts/brand_store.py --db brandos.db rollback <id> --version 1
```

## Security

- **Workspace isolation:** All CRUD operations are scoped to the store's
  `workspace_id`. Cross-workspace reads return `None`, writes return `False`.
- **Sensitive field redaction:** `internal_notes` and `internal_tags` are
  redacted in logs and exports (`[REDACTED]`).
- **Log redaction:** `_RedactingFilter` strips API keys, tokens, passwords,
  and Bearer tokens from log messages.
- **Input validation:** Name, industry, tagline, description, tone, website,
  colors, and status are validated on create and update.
- **SQL injection prevention:** All queries use parameterized statements.
  Reserved SQLite column names (`values`) are quoted.

## Idempotency

Creating a brand with the same (workspace_id, name) pair returns the existing
brand without creating a duplicate. Name matching is case-insensitive.

Creating a brand with the same name as an archived brand reactivates it
(resets to version 1 with the new data).

## Test Categories (109 tests)

| Category            | Count | Coverage                                              |
|---------------------|-------|-------------------------------------------------------|
| ID Generation       | 5     | Deterministic, case-insensitive, workspace-scoped     |
| Validation          | 19    | All field constraints, edge cases                     |
| Create              | 9     | Basic, all fields, idempotency, timestamps            |
| Read                | 10    | Get by ID/name, list, pagination                      |
| Update              | 9     | Single/multi field, validation, versioning            |
| Archive/Restore     | 6     | Soft-delete, restore, double-archive                  |
| Count               | 3     | Active, archived, empty                               |
| Search              | 7     | Name, industry, tagline, description, limits          |
| Export              | 3     | JSON export, sensitive redaction                       |
| Workspace Isolation | 4     | Cross-workspace read/update/archive/search blocked    |
| Redaction           | 3     | Dict redaction, name redaction                         |
| Versioning          | 8     | List, get, count, snapshots, diff                     |
| Rollback            | 5     | Basic, nonexistent, creates version, then-update      |
| Changed Fields      | 4     | No change, single, multiple, non-versioned ignored    |
| Edge Cases          | 14    | Unicode, long text, special chars, concurrent, schema |
