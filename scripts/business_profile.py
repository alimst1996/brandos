#!/usr/bin/env python3
"""Business profile storage and API for BrandOS.

Provides CRUD operations for business profiles stored in a SQLite database.
Each profile is workspace-scoped and audit-logged with redaction of sensitive
fields.

Usage (import):
    from business_profile import BusinessProfileStore, BusinessProfile

Usage (CLI):
    python scripts/business_profile.py --db brandos.db create --name "Acme Corp" --industry "Tech"
    python scripts/business_profile.py --db brandos.db list
    python scripts/business_profile.py --db brandos.db get <id>
    python scripts/business_profile.py --db brandos.db update <id> --name "New Name"
    python scripts/business_profile.py --db brandos.db delete <id>

Environment variables:
    BRANDOS_DB_PATH — default database path (overridden by --db flag)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Logging with redaction
# ---------------------------------------------------------------------------

_REDACTED = "[REDACTED]"

# Fields whose values must never appear in logs
_SENSITIVE_FIELDS = {"notes", "internal_tags"}

_SENSITIVE_VALUE_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*\S+"),
    re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE),
]


class _RedactingFilter(logging.Filter):
    """Redacts sensitive values from log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            for pat in _SENSITIVE_VALUE_PATTERNS:
                record.msg = pat.sub(_REDACTED, record.msg)
        return True


logger = logging.getLogger("brandos.business_profile")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.addFilter(_RedactingFilter())
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)


def _redact_dict(d: dict) -> dict:
    """Return a shallow copy of *d* with sensitive keys redacted."""
    return {k: (_REDACTED if k in _SENSITIVE_FIELDS else v) for k, v in d.items()}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class BusinessProfile:
    """A business profile represents a brand or company in BrandOS.

    Attributes:
        id:         Deterministic UUID v5 derived from (workspace_id, name).
        name:       Business / brand name (required, 1–200 chars).
        industry:   Industry or vertical (optional, max 100 chars).
        description: Free-text description (optional, max 2000 chars).
        target_audience: Description of the target audience (optional).
        website:    Business website URL (optional).
        logo_url:   URL to the brand logo (optional).
        workspace_id: Owning workspace identifier (required).
        status:     Profile status — 'active' or 'archived'.
        notes:      Internal notes (redacted from logs).
        internal_tags: Comma-separated internal tags (redacted from logs).
        created_at: ISO 8601 creation timestamp (UTC).
        updated_at: ISO 8601 last-update timestamp (UTC).
    """

    id: str
    name: str
    industry: str = ""
    description: str = ""
    target_audience: str = ""
    website: str = ""
    logo_url: str = ""
    workspace_id: str = ""
    status: str = "active"
    notes: str = ""
    internal_tags: str = ""
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "BusinessProfile":
        return cls(**{k: row[k] for k in row.keys()})


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class ValidationError(Exception):
    """Raised when a profile field fails validation."""

    def __init__(self, field_name: str, message: str):
        self.field_name = field_name
        super().__init__(f"{field_name}: {message}")


def validate_profile(profile: BusinessProfile) -> List[ValidationError]:
    """Validate a BusinessProfile, returning a list of errors (empty = valid)."""
    errors: List[ValidationError] = []

    if not profile.name or not profile.name.strip():
        errors.append(ValidationError("name", "Name is required"))
    elif len(profile.name) > 200:
        errors.append(ValidationError("name", "Name must be at most 200 characters"))

    if len(profile.industry) > 100:
        errors.append(ValidationError("industry", "Industry must be at most 100 characters"))

    if len(profile.description) > 2000:
        errors.append(ValidationError("description", "Description must be at most 2000 characters"))

    if profile.website and not re.match(r"https?://", profile.website):
        errors.append(ValidationError("website", "Website must start with http:// or https://"))

    if profile.status not in ("active", "archived"):
        errors.append(ValidationError("status", "Status must be 'active' or 'archived'"))

    if not profile.workspace_id:
        errors.append(ValidationError("workspace_id", "Workspace ID is required"))

    return errors


# ---------------------------------------------------------------------------
# Deterministic ID generation
# ---------------------------------------------------------------------------

_NAMESPACE = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")


def _generate_id(workspace_id: str, name: str) -> str:
    """Generate a deterministic UUID v5 from workspace_id + name."""
    return str(uuid.uuid5(_NAMESPACE, f"{workspace_id}:{name.lower().strip()}"))


# ---------------------------------------------------------------------------
# Database schema
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS business_profiles (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    industry        TEXT NOT NULL DEFAULT '',
    description     TEXT NOT NULL DEFAULT '',
    target_audience TEXT NOT NULL DEFAULT '',
    website         TEXT NOT NULL DEFAULT '',
    logo_url        TEXT NOT NULL DEFAULT '',
    workspace_id    TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active',
    notes           TEXT NOT NULL DEFAULT '',
    internal_tags   TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_bp_workspace
    ON business_profiles(workspace_id);

CREATE INDEX IF NOT EXISTS idx_bp_status
    ON business_profiles(workspace_id, status);
"""


# ---------------------------------------------------------------------------
# Store (data access layer)
# ---------------------------------------------------------------------------

class BusinessProfileStore:
    """SQLite-backed CRUD store for business profiles.

    All operations are workspace-scoped — a store instance is bound to a
    workspace_id and can only read/write profiles within that workspace.

    Args:
        db_path: Path to SQLite database file.
        workspace_id: Workspace scope for all operations.
    """

    def __init__(self, db_path: str, workspace_id: str):
        if not workspace_id:
            raise ValueError("workspace_id is required")
        self.db_path = db_path
        self.workspace_id = workspace_id
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _ensure_schema(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(_SCHEMA_SQL)
            conn.commit()
        finally:
            conn.close()

    # -- CRUD -----------------------------------------------------------------

    def create(
        self,
        name: str,
        industry: str = "",
        description: str = "",
        target_audience: str = "",
        website: str = "",
        logo_url: str = "",
        notes: str = "",
        internal_tags: str = "",
    ) -> BusinessProfile:
        """Create a new business profile. Raises ValidationError on bad input."""
        now = _now_iso()
        profile = BusinessProfile(
            id=_generate_id(self.workspace_id, name),
            name=name.strip(),
            industry=industry.strip(),
            description=description.strip(),
            target_audience=target_audience.strip(),
            website=website.strip(),
            logo_url=logo_url.strip(),
            workspace_id=self.workspace_id,
            status="active",
            notes=notes,
            internal_tags=internal_tags,
            created_at=now,
            updated_at=now,
        )

        errors = validate_profile(profile)
        if errors:
            raise errors[0]

        # Idempotency: if a profile with the same (workspace, name) already
        # exists and is active, return it instead of creating a duplicate.
        existing = self.get_by_name(name)
        if existing and existing.status == "active":
            logger.info(
                "profile_already_exists id=%s name=%s workspace=%s",
                existing.id, _redact_name(name), self.workspace_id,
            )
            return existing

        conn = self._connect()
        try:
            # If a soft-deleted profile exists with the same ID, reactivate it.
            row = conn.execute(
                "SELECT id, status FROM business_profiles WHERE id = ? AND workspace_id = ?",
                (profile.id, self.workspace_id),
            ).fetchone()

            if row and row["status"] == "archived":
                conn.execute(
                    """UPDATE business_profiles
                       SET name=?, industry=?, description=?, target_audience=?,
                           website=?, logo_url=?, status='active', notes=?,
                           internal_tags=?, updated_at=?
                       WHERE id=? AND workspace_id=?""",
                    (
                        profile.name, profile.industry, profile.description,
                        profile.target_audience, profile.website, profile.logo_url,
                        notes, internal_tags, now, profile.id, self.workspace_id,
                    ),
                )
                logger.info(
                    "profile_reactivated id=%s workspace=%s",
                    profile.id, self.workspace_id,
                )
            else:
                conn.execute(
                    """INSERT INTO business_profiles
                       (id, name, industry, description, target_audience,
                        website, logo_url, workspace_id, status, notes,
                        internal_tags, created_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        profile.id, profile.name, profile.industry,
                        profile.description, profile.target_audience,
                        profile.website, profile.logo_url,
                        self.workspace_id, "active",
                        notes, internal_tags, now, now,
                    ),
                )
                logger.info(
                    "profile_created id=%s workspace=%s",
                    profile.id, self.workspace_id,
                )
            conn.commit()
        finally:
            conn.close()

        return profile

    def get(self, profile_id: str) -> Optional[BusinessProfile]:
        """Get a profile by ID (workspace-scoped)."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM business_profiles WHERE id = ? AND workspace_id = ?",
                (profile_id, self.workspace_id),
            ).fetchone()
            return BusinessProfile.from_row(row) if row else None
        finally:
            conn.close()

    def get_by_name(self, name: str) -> Optional[BusinessProfile]:
        """Get a profile by exact name (workspace-scoped, case-insensitive)."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM business_profiles WHERE LOWER(name) = LOWER(?) AND workspace_id = ?",
                (name.strip(), self.workspace_id),
            ).fetchone()
            return BusinessProfile.from_row(row) if row else None
        finally:
            conn.close()

    def list(
        self,
        status: str = "active",
        limit: int = 50,
        offset: int = 0,
    ) -> List[BusinessProfile]:
        """List profiles in this workspace, optionally filtered by status."""
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT * FROM business_profiles
                   WHERE workspace_id = ? AND status = ?
                   ORDER BY created_at DESC LIMIT ? OFFSET ?""",
                (self.workspace_id, status, limit, offset),
            ).fetchall()
            return [BusinessProfile.from_row(r) for r in rows]
        finally:
            conn.close()

    def update(self, profile_id: str, **fields: Any) -> Optional[BusinessProfile]:
        """Update fields on an existing profile. Returns updated profile or None.

        Only these fields are accepted: name, industry, description,
        target_audience, website, logo_url, notes, internal_tags, status.
        """
        ALLOWED = {
            "name", "industry", "description", "target_audience",
            "website", "logo_url", "notes", "internal_tags", "status",
        }
        invalid = set(fields) - ALLOWED
        if invalid:
            raise ValidationError(str(invalid), f"Cannot update fields: {invalid}")

        if not fields:
            return self.get(profile_id)

        # Build a temporary profile for validation
        existing = self.get(profile_id)
        if not existing:
            return None

        merged = {**existing.to_dict(), **fields, "updated_at": _now_iso()}
        temp = BusinessProfile(**merged)
        errors = validate_profile(temp)
        if errors:
            raise errors[0]

        set_clause = ", ".join(f"{k}=?" for k in fields)
        values = list(fields.values()) + [_now_iso(), profile_id, self.workspace_id]

        conn = self._connect()
        try:
            conn.execute(
                f"UPDATE business_profiles SET {set_clause}, updated_at=? "
                f"WHERE id=? AND workspace_id=?",
                values,
            )
            conn.commit()
            logger.info(
                "profile_updated id=%s fields=%s workspace=%s",
                profile_id, list(fields.keys()), self.workspace_id,
            )
            return self.get(profile_id)
        finally:
            conn.close()

    def archive(self, profile_id: str) -> bool:
        """Soft-delete a profile by setting status to 'archived'."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                """UPDATE business_profiles SET status='archived', updated_at=?
                   WHERE id=? AND workspace_id=? AND status='active'""",
                (_now_iso(), profile_id, self.workspace_id),
            )
            conn.commit()
            if cursor.rowcount > 0:
                logger.info(
                    "profile_archived id=%s workspace=%s",
                    profile_id, self.workspace_id,
                )
                return True
            return False
        finally:
            conn.close()

    def restore(self, profile_id: str) -> bool:
        """Restore an archived profile to active."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                """UPDATE business_profiles SET status='active', updated_at=?
                   WHERE id=? AND workspace_id=? AND status='archived'""",
                (_now_iso(), profile_id, self.workspace_id),
            )
            conn.commit()
            if cursor.rowcount > 0:
                logger.info(
                    "profile_restored id=%s workspace=%s",
                    profile_id, self.workspace_id,
                )
                return True
            return False
        finally:
            conn.close()

    def count(self, status: str = "active") -> int:
        """Count profiles in this workspace by status."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM business_profiles "
                "WHERE workspace_id=? AND status=?",
                (self.workspace_id, status),
            ).fetchone()
            return row["cnt"] if row else 0
        finally:
            conn.close()

    def search(self, query: str, limit: int = 20) -> List[BusinessProfile]:
        """Full-text search across name, industry, and description."""
        pattern = f"%{query.strip()}%"
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT * FROM business_profiles
                   WHERE workspace_id = ?
                     AND status = 'active'
                     AND (name LIKE ? OR industry LIKE ? OR description LIKE ?)
                   ORDER BY name LIMIT ?""",
                (self.workspace_id, pattern, pattern, pattern, limit),
            ).fetchall()
            return [BusinessProfile.from_row(r) for r in rows]
        finally:
            conn.close()

    def export_json(self, status: str = "active") -> str:
        """Export all profiles as JSON (sensitive fields redacted)."""
        profiles = self.list(status=status, limit=10000)
        data = []
        for p in profiles:
            d = p.to_dict()
            d["notes"] = _REDACTED
            d["internal_tags"] = _REDACTED
            data.append(d)
        return json.dumps(data, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _redact_name(name: str) -> str:
    """Partially redact a name for logging (keep first 3 chars)."""
    if len(name) <= 3:
        return name
    return name[:3] + "***"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli() -> None:
    parser = argparse.ArgumentParser(description="BrandOS Business Profile CLI")
    parser.add_argument("--db", default=os.environ.get("BRANDOS_DB_PATH", "brandos.db"),
                        help="SQLite database path")
    parser.add_argument("--workspace", default=os.environ.get("BRANDOS_WORKSPACE_ID", "default"),
                        help="Workspace ID")

    sub = parser.add_subparsers(dest="command")

    # create
    p_create = sub.add_parser("create", help="Create a new profile")
    p_create.add_argument("--name", required=True)
    p_create.add_argument("--industry", default="")
    p_create.add_argument("--description", default="")
    p_create.add_argument("--target-audience", default="")
    p_create.add_argument("--website", default="")
    p_create.add_argument("--logo-url", default="")

    # list
    p_list = sub.add_parser("list", help="List profiles")
    p_list.add_argument("--status", default="active")
    p_list.add_argument("--limit", type=int, default=50)

    # get
    p_get = sub.add_parser("get", help="Get a profile by ID")
    p_get.add_argument("id")

    # update
    p_update = sub.add_parser("update", help="Update a profile")
    p_update.add_argument("id")
    p_update.add_argument("--name")
    p_update.add_argument("--industry")
    p_update.add_argument("--description")
    p_update.add_argument("--website")

    # archive
    p_archive = sub.add_parser("archive", help="Archive a profile")
    p_archive.add_argument("id")

    # search
    p_search = sub.add_parser("search", help="Search profiles")
    p_search.add_argument("query")
    p_search.add_argument("--limit", type=int, default=20)

    # export
    p_export = sub.add_parser("export", help="Export profiles as JSON")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    store = BusinessProfileStore(args.db, args.workspace)

    if args.command == "create":
        p = store.create(
            name=args.name,
            industry=args.industry,
            description=args.description,
            target_audience=args.target_audience,
            website=args.website,
            logo_url=args.logo_url,
        )
        print(json.dumps(p.to_dict(), indent=2, ensure_ascii=False))

    elif args.command == "list":
        profiles = store.list(status=args.status, limit=args.limit)
        for p in profiles:
            print(f"  {p.id[:8]}  {p.name:<30}  {p.industry:<20}  {p.status}")
        if not profiles:
            print("  (no profiles)")

    elif args.command == "get":
        p = store.get(args.id)
        if p:
            print(json.dumps(p.to_dict(), indent=2, ensure_ascii=False))
        else:
            print(f"Profile {args.id} not found")
            raise SystemExit(1)

    elif args.command == "update":
        fields = {k: v for k, v in vars(args).items()
                  if k not in ("id", "command", "db", "workspace") and v is not None}
        p = store.update(args.id, **fields)
        if p:
            print(json.dumps(p.to_dict(), indent=2, ensure_ascii=False))
        else:
            print(f"Profile {args.id} not found")
            raise SystemExit(1)

    elif args.command == "archive":
        if store.archive(args.id):
            print(f"Profile {args.id} archived")
        else:
            print(f"Profile {args.id} not found or already archived")
            raise SystemExit(1)

    elif args.command == "search":
        profiles = store.search(args.query, limit=args.limit)
        for p in profiles:
            print(f"  {p.id[:8]}  {p.name:<30}  {p.industry:<20}")
        if not profiles:
            print("  (no matches)")

    elif args.command == "export":
        print(store.export_json())


if __name__ == "__main__":
    _cli()
