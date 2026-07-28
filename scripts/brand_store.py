#!/usr/bin/env python3
"""Brand storage and API with versioning for BrandOS.

Provides CRUD operations for brand profiles stored in a SQLite database.
Every update creates an immutable version snapshot, enabling full history,
version comparison, and rollback.

Each brand is workspace-scoped and audit-logged with redaction of sensitive
fields.

Usage (import):
    from brand_store import BrandStore, Brand

    store = BrandStore(db_path="brandos.db", workspace_id="my-ws")
    brand = store.create(name="Acme", industry="Tech")
    store.update(brand.id, tagline="We build things")
    versions = store.list_versions(brand.id)

Usage (CLI):
    python scripts/brand_store.py --db brandos.db create --name "Acme" --industry "Tech"
    python scripts/brand_store.py --db brandos.db list
    python scripts/brand_store.py --db brandos.db get <id>
    python scripts/brand_store.py --db brand_store.py update <id> --tagline "New tagline"
    python scripts/brand_store.py --db brandos.db versions <id>
    python scripts/brand_store.py --db brandos.db rollback <id> --version 1
    python scripts/brand_store.py --db brandos.db diff <id> --from 1 --to 3

Environment variables:
    BRANDOS_DB_PATH — default database path (overridden by --db flag)
    BRANDOS_WORKSPACE_ID — default workspace ID (overridden by --workspace flag)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sqlite3
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Logging with redaction
# ---------------------------------------------------------------------------

_REDACTED = "[REDACTED]"

_SENSITIVE_FIELDS = {"internal_notes", "internal_tags"}

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


logger = logging.getLogger("brandos.brand_store")
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
class Brand:
    """A brand profile with versioning support.

    Attributes:
        id:              Deterministic UUID v5 derived from (workspace_id, name).
        name:            Brand name (required, 1–200 chars).
        industry:        Industry or vertical (optional, max 100 chars).
        tagline:         Short brand tagline (optional, max 300 chars).
        description:     Free-text description (optional, max 5000 chars).
        tone:            Brand tone of voice (optional, max 100 chars).
        personality:     Comma-separated personality traits (optional).
        values:          Comma-separated brand values (optional).
        target_audience: Description of the target audience (optional).
        website:         Brand website URL (optional).
        logo_url:        URL to brand logo (optional).
        color_primary:   Primary brand color hex code (optional).
        color_secondary: Secondary brand color hex code (optional).
        prohibited_terms: Comma-separated words that must never appear (optional).
        workspace_id:    Owning workspace identifier (required).
        status:          Brand status — 'active' or 'archived'.
        version:         Current version number (auto-incremented on updates).
        internal_notes:  Internal notes (redacted from logs/exports).
        internal_tags:   Comma-separated internal tags (redacted from logs/exports).
        created_at:      ISO 8601 creation timestamp (UTC).
        updated_at:      ISO 8601 last-update timestamp (UTC).
    """

    id: str
    name: str
    industry: str = ""
    tagline: str = ""
    description: str = ""
    tone: str = ""
    personality: str = ""
    values: str = ""
    target_audience: str = ""
    website: str = ""
    logo_url: str = ""
    color_primary: str = ""
    color_secondary: str = ""
    prohibited_terms: str = ""
    workspace_id: str = ""
    status: str = "active"
    version: int = 1
    internal_notes: str = ""
    internal_tags: str = ""
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Brand":
        return cls(**{k: row[k] for k in row.keys()})


# ---------------------------------------------------------------------------
# Version snapshot (immutable historical record)
# ---------------------------------------------------------------------------

@dataclass
class BrandVersion:
    """An immutable snapshot of a brand at a specific version.

    Attributes:
        id:              Auto-increment row ID.
        brand_id:        The brand this version belongs to.
        version:         Version number (1, 2, 3, ...).
        snapshot:        Full JSON snapshot of the brand at this version.
        changed_fields:  Comma-separated list of fields that changed.
        created_at:      ISO 8601 timestamp when this version was created.
    """

    id: int
    brand_id: str
    version: int
    snapshot: str
    changed_fields: str
    created_at: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def get_snapshot_dict(self) -> Dict[str, Any]:
        """Parse the JSON snapshot into a dict."""
        return json.loads(self.snapshot)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "BrandVersion":
        return cls(**{k: row[k] for k in row.keys()})


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class ValidationError(Exception):
    """Raised when a brand field fails validation."""

    def __init__(self, field_name: str, message: str):
        self.field_name = field_name
        super().__init__(f"{field_name}: {message}")


def validate_brand(brand: Brand) -> List[ValidationError]:
    """Validate a Brand, returning a list of errors (empty = valid)."""
    errors: List[ValidationError] = []

    if not brand.name or not brand.name.strip():
        errors.append(ValidationError("name", "Name is required"))
    elif len(brand.name) > 200:
        errors.append(ValidationError("name", "Name must be at most 200 characters"))

    if len(brand.industry) > 100:
        errors.append(ValidationError("industry", "Industry must be at most 100 characters"))

    if len(brand.tagline) > 300:
        errors.append(ValidationError("tagline", "Tagline must be at most 300 characters"))

    if len(brand.description) > 5000:
        errors.append(ValidationError("description", "Description must be at most 5000 characters"))

    if len(brand.tone) > 100:
        errors.append(ValidationError("tone", "Tone must be at most 100 characters"))

    if brand.website and not re.match(r"https?://", brand.website):
        errors.append(ValidationError("website", "Website must start with http:// or https://"))

    if brand.color_primary and not re.match(r"^#[0-9a-fA-F]{6}$", brand.color_primary):
        errors.append(ValidationError("color_primary", "Must be a hex color code (e.g. #FF0000)"))

    if brand.color_secondary and not re.match(r"^#[0-9a-fA-F]{6}$", brand.color_secondary):
        errors.append(ValidationError("color_secondary", "Must be a hex color code (e.g. #00FF00)"))

    if brand.status not in ("active", "archived"):
        errors.append(ValidationError("status", "Status must be 'active' or 'archived'"))

    if not brand.workspace_id:
        errors.append(ValidationError("workspace_id", "Workspace ID is required"))

    return errors


# ---------------------------------------------------------------------------
# Deterministic ID generation
# ---------------------------------------------------------------------------

_NAMESPACE = uuid.UUID("b2c3d4e5-f6a7-8901-bcde-f12345678901")

# SQLite reserved words that need quoting when used as column names
_SQLITE_RESERVED = {"values", "order", "group", "select", "table", "index", "key"}


def _quote_col(name: str) -> str:
    """Quote a column name if it's a SQLite reserved word."""
    if name.lower() in _SQLITE_RESERVED:
        return f'"{name}"'
    return name


def _generate_id(workspace_id: str, name: str) -> str:
    """Generate a deterministic UUID v5 from workspace_id + name."""
    return str(uuid.uuid5(_NAMESPACE, f"{workspace_id}:{name.lower().strip()}"))


# ---------------------------------------------------------------------------
# Database schema
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS brands (
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    industry         TEXT NOT NULL DEFAULT '',
    tagline          TEXT NOT NULL DEFAULT '',
    description      TEXT NOT NULL DEFAULT '',
    tone             TEXT NOT NULL DEFAULT '',
    personality      TEXT NOT NULL DEFAULT '',
    "values"         TEXT NOT NULL DEFAULT '',
    target_audience  TEXT NOT NULL DEFAULT '',
    website          TEXT NOT NULL DEFAULT '',
    logo_url         TEXT NOT NULL DEFAULT '',
    color_primary    TEXT NOT NULL DEFAULT '',
    color_secondary  TEXT NOT NULL DEFAULT '',
    prohibited_terms TEXT NOT NULL DEFAULT '',
    workspace_id     TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'active',
    version          INTEGER NOT NULL DEFAULT 1,
    internal_notes   TEXT NOT NULL DEFAULT '',
    internal_tags    TEXT NOT NULL DEFAULT '',
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_brands_workspace
    ON brands(workspace_id);

CREATE INDEX IF NOT EXISTS idx_brands_status
    ON brands(workspace_id, status);

CREATE INDEX IF NOT EXISTS idx_brands_name
    ON brands(workspace_id, name);

CREATE TABLE IF NOT EXISTS brand_versions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_id        TEXT NOT NULL,
    version         INTEGER NOT NULL,
    snapshot        TEXT NOT NULL,
    changed_fields  TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL,
    UNIQUE(brand_id, version)
);

CREATE INDEX IF NOT EXISTS idx_bv_brand
    ON brand_versions(brand_id);

CREATE INDEX IF NOT EXISTS idx_bv_brand_version
    ON brand_versions(brand_id, version);
"""


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


# Fields tracked for versioning (excludes metadata fields)
_VERSIONED_FIELDS = {
    "name", "industry", "tagline", "description", "tone", "personality",
    "values", "target_audience", "website", "logo_url", "color_primary",
    "color_secondary", "prohibited_terms",
}


def _compute_changed_fields(old: Dict[str, Any], new: Dict[str, Any]) -> str:
    """Compute which versioned fields changed between two brand dicts."""
    changed = []
    for f in _VERSIONED_FIELDS:
        if old.get(f, "") != new.get(f, ""):
            changed.append(f)
    return ",".join(sorted(changed))


# ---------------------------------------------------------------------------
# Store (data access layer)
# ---------------------------------------------------------------------------

class BrandStore:
    """SQLite-backed CRUD store for brands with full version history.

    All operations are workspace-scoped — a store instance is bound to a
    workspace_id and can only read/write brands within that workspace.

    Every update to a brand creates an immutable version snapshot, enabling:
    - Full audit trail of all changes
    - Version comparison (diff)
    - Rollback to any previous version

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

    def _snapshot_version(
        self, conn: sqlite3.Connection, brand: Brand, changed_fields: str = ""
    ) -> None:
        """Insert an immutable version snapshot into brand_versions.

        Uses INSERT OR REPLACE so that reactivating an archived brand
        (which resets to version 1) replaces the old version 1 snapshot.
        """
        snapshot = json.dumps(brand.to_dict(), ensure_ascii=False)
        conn.execute(
            """INSERT OR REPLACE INTO brand_versions
               (brand_id, version, snapshot, changed_fields, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (brand.id, brand.version, snapshot, changed_fields, _now_iso()),
        )

    # -- CRUD -----------------------------------------------------------------

    def create(
        self,
        name: str,
        industry: str = "",
        tagline: str = "",
        description: str = "",
        tone: str = "",
        personality: str = "",
        values: str = "",
        target_audience: str = "",
        website: str = "",
        logo_url: str = "",
        color_primary: str = "",
        color_secondary: str = "",
        prohibited_terms: str = "",
        internal_notes: str = "",
        internal_tags: str = "",
    ) -> Brand:
        """Create a new brand. Raises ValidationError on bad input.

        Idempotent: if an active brand with the same (workspace, name) already
        exists, returns it without creating a duplicate.
        """
        now = _now_iso()
        brand = Brand(
            id=_generate_id(self.workspace_id, name),
            name=name.strip(),
            industry=industry.strip(),
            tagline=tagline.strip(),
            description=description.strip(),
            tone=tone.strip(),
            personality=personality.strip(),
            values=values.strip(),
            target_audience=target_audience.strip(),
            website=website.strip(),
            logo_url=logo_url.strip(),
            color_primary=color_primary.strip(),
            color_secondary=color_secondary.strip(),
            prohibited_terms=prohibited_terms.strip(),
            workspace_id=self.workspace_id,
            status="active",
            version=1,
            internal_notes=internal_notes,
            internal_tags=internal_tags,
            created_at=now,
            updated_at=now,
        )

        errors = validate_brand(brand)
        if errors:
            raise errors[0]

        # Idempotency
        existing = self.get_by_name(name)
        if existing and existing.status == "active":
            logger.info(
                "brand_already_exists id=%s name=%s workspace=%s",
                existing.id, _redact_name(name), self.workspace_id,
            )
            return existing

        conn = self._connect()
        try:
            # Reactivate archived brand with same ID
            row = conn.execute(
                "SELECT id, status FROM brands WHERE id = ? AND workspace_id = ?",
                (brand.id, self.workspace_id),
            ).fetchone()

            if row and row["status"] == "archived":
                conn.execute(
                    """UPDATE brands
                       SET name=?, industry=?, tagline=?, description=?,
                           tone=?, personality=?, "values"=?, target_audience=?,
                           website=?, logo_url=?, color_primary=?,
                           color_secondary=?, prohibited_terms=?,
                           status='active', version=1, internal_notes=?,
                           internal_tags=?, updated_at=?
                       WHERE id=? AND workspace_id=?""",
                    (
                        brand.name, brand.industry, brand.tagline,
                        brand.description, brand.tone, brand.personality,
                        brand.values, brand.target_audience, brand.website,
                        brand.logo_url, brand.color_primary,
                        brand.color_secondary, brand.prohibited_terms,
                        internal_notes, internal_tags, now,
                        brand.id, self.workspace_id,
                    ),
                )
                logger.info(
                    "brand_reactivated id=%s workspace=%s",
                    brand.id, self.workspace_id,
                )
            else:
                conn.execute(
                    """INSERT INTO brands
                       (id, name, industry, tagline, description, tone,
                        personality, "values", target_audience, website,
                        logo_url, color_primary, color_secondary,
                        prohibited_terms, workspace_id, status, version,
                        internal_notes, internal_tags, created_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        brand.id, brand.name, brand.industry, brand.tagline,
                        brand.description, brand.tone, brand.personality,
                        brand.values, brand.target_audience, brand.website,
                        brand.logo_url, brand.color_primary,
                        brand.color_secondary, brand.prohibited_terms,
                        self.workspace_id, "active", 1,
                        internal_notes, internal_tags, now, now,
                    ),
                )
                logger.info(
                    "brand_created id=%s workspace=%s",
                    brand.id, self.workspace_id,
                )

            # Create initial version snapshot
            self._snapshot_version(conn, brand, "initial")
            conn.commit()
        finally:
            conn.close()

        return brand

    def get(self, brand_id: str) -> Optional[Brand]:
        """Get a brand by ID (workspace-scoped)."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM brands WHERE id = ? AND workspace_id = ?",
                (brand_id, self.workspace_id),
            ).fetchone()
            return Brand.from_row(row) if row else None
        finally:
            conn.close()

    def get_by_name(self, name: str) -> Optional[Brand]:
        """Get a brand by exact name (workspace-scoped, case-insensitive)."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM brands WHERE LOWER(name) = LOWER(?) AND workspace_id = ?",
                (name.strip(), self.workspace_id),
            ).fetchone()
            return Brand.from_row(row) if row else None
        finally:
            conn.close()

    def list(
        self,
        status: str = "active",
        limit: int = 50,
        offset: int = 0,
    ) -> List[Brand]:
        """List brands in this workspace, optionally filtered by status."""
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT * FROM brands
                   WHERE workspace_id = ? AND status = ?
                   ORDER BY created_at DESC LIMIT ? OFFSET ?""",
                (self.workspace_id, status, limit, offset),
            ).fetchall()
            return [Brand.from_row(r) for r in rows]
        finally:
            conn.close()

    def update(self, brand_id: str, **fields: Any) -> Optional[Brand]:
        """Update fields on a brand. Returns updated brand or None.

        Creates a new version snapshot before applying the update.

        Acceptable fields: name, industry, tagline, description, tone,
        personality, values, target_audience, website, logo_url,
        color_primary, color_secondary, prohibited_terms, internal_notes,
        internal_tags, status.
        """
        ALLOWED = {
            "name", "industry", "tagline", "description", "tone",
            "personality", "values", "target_audience", "website",
            "logo_url", "color_primary", "color_secondary",
            "prohibited_terms", "internal_notes", "internal_tags", "status",
        }
        invalid = set(fields) - ALLOWED
        if invalid:
            raise ValidationError(str(invalid), f"Cannot update fields: {invalid}")

        if not fields:
            return self.get(brand_id)

        existing = self.get(brand_id)
        if not existing:
            return None

        # Merge and validate
        merged = {**existing.to_dict(), **fields, "updated_at": _now_iso()}
        merged["version"] = existing.version + 1
        temp = Brand(**merged)
        errors = validate_brand(temp)
        if errors:
            raise errors[0]

        # Compute changed fields for version snapshot
        changed = _compute_changed_fields(existing.to_dict(), temp.to_dict())

        conn = self._connect()
        try:
            # Apply the update
            set_parts = []
            values_list = []
            for k in fields:
                set_parts.append(f"{_quote_col(k)}=?")
                values_list.append(fields[k])

            new_version = existing.version + 1
            values_list.extend([_now_iso(), new_version, brand_id, self.workspace_id])
            set_clause = ", ".join(set_parts)

            conn.execute(
                f"UPDATE brands SET {set_clause}, updated_at=?, version=? "
                f"WHERE id=? AND workspace_id=?",
                values_list,
            )

            # Snapshot the new state after updating (read from same conn
            # so we see the uncommitted version bump).
            updated_row = conn.execute(
                "SELECT * FROM brands WHERE id = ? AND workspace_id = ?",
                (brand_id, self.workspace_id),
            ).fetchone()
            if updated_row:
                updated_brand = Brand.from_row(updated_row)
                self._snapshot_version(
                    conn, updated_brand,
                    changed if changed else "status_change",
                )

            conn.commit()

            logger.info(
                "brand_updated id=%s fields=%s version=%d workspace=%s",
                brand_id, list(fields.keys()), existing.version + 1, self.workspace_id,
            )
            return self.get(brand_id)
        finally:
            conn.close()

    def archive(self, brand_id: str) -> bool:
        """Soft-delete a brand by setting status to 'archived'."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                """UPDATE brands SET status='archived', updated_at=?
                   WHERE id=? AND workspace_id=? AND status='active'""",
                (_now_iso(), brand_id, self.workspace_id),
            )
            conn.commit()
            if cursor.rowcount > 0:
                logger.info(
                    "brand_archived id=%s workspace=%s",
                    brand_id, self.workspace_id,
                )
                return True
            return False
        finally:
            conn.close()

    def restore(self, brand_id: str) -> bool:
        """Restore an archived brand to active."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                """UPDATE brands SET status='active', updated_at=?
                   WHERE id=? AND workspace_id=? AND status='archived'""",
                (_now_iso(), brand_id, self.workspace_id),
            )
            conn.commit()
            if cursor.rowcount > 0:
                logger.info(
                    "brand_restored id=%s workspace=%s",
                    brand_id, self.workspace_id,
                )
                return True
            return False
        finally:
            conn.close()

    def count(self, status: str = "active") -> int:
        """Count brands in this workspace by status."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM brands "
                "WHERE workspace_id=? AND status=?",
                (self.workspace_id, status),
            ).fetchone()
            return row["cnt"] if row else 0
        finally:
            conn.close()

    def search(self, query: str, limit: int = 20) -> List[Brand]:
        """Full-text search across name, industry, tagline, and description."""
        pattern = f"%{query.strip()}%"
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT * FROM brands
                   WHERE workspace_id = ?
                     AND status = 'active'
                     AND (name LIKE ? OR industry LIKE ? OR tagline LIKE ?
                          OR description LIKE ?)
                   ORDER BY name LIMIT ?""",
                (self.workspace_id, pattern, pattern, pattern, pattern, limit),
            ).fetchall()
            return [Brand.from_row(r) for r in rows]
        finally:
            conn.close()

    def export_json(self, status: str = "active") -> str:
        """Export all brands as JSON (sensitive fields redacted)."""
        brands = self.list(status=status, limit=10000)
        data = []
        for b in brands:
            d = b.to_dict()
            d["internal_notes"] = _REDACTED
            d["internal_tags"] = _REDACTED
            data.append(d)
        return json.dumps(data, indent=2, ensure_ascii=False)

    # -- Versioning -----------------------------------------------------------

    def list_versions(self, brand_id: str) -> List[BrandVersion]:
        """List all version snapshots for a brand, ordered by version number."""
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT * FROM brand_versions
                   WHERE brand_id = ?
                   ORDER BY version ASC""",
                (brand_id,),
            ).fetchall()
            return [BrandVersion.from_row(r) for r in rows]
        finally:
            conn.close()

    def get_version(self, brand_id: str, version: int) -> Optional[BrandVersion]:
        """Get a specific version snapshot of a brand."""
        conn = self._connect()
        try:
            row = conn.execute(
                """SELECT * FROM brand_versions
                   WHERE brand_id = ? AND version = ?""",
                (brand_id, version),
            ).fetchone()
            return BrandVersion.from_row(row) if row else None
        finally:
            conn.close()

    def get_version_count(self, brand_id: str) -> int:
        """Count the total number of versions for a brand."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM brand_versions WHERE brand_id = ?",
                (brand_id,),
            ).fetchone()
            return row["cnt"] if row else 0
        finally:
            conn.close()

    def diff_versions(
        self, brand_id: str, from_version: int, to_version: int
    ) -> Optional[Dict[str, Dict[str, Any]]]:
        """Compare two versions and return field-level differences.

        Returns a dict like:
            {
                "tagline": {"from": "Old tagline", "to": "New tagline"},
                "tone": {"from": "formal", "to": "casual"},
            }

        Returns None if either version doesn't exist.
        """
        v_from = self.get_version(brand_id, from_version)
        v_to = self.get_version(brand_id, to_version)
        if not v_from or not v_to:
            return None

        snap_from = v_from.get_snapshot_dict()
        snap_to = v_to.get_snapshot_dict()

        diff = {}
        for f in sorted(_VERSIONED_FIELDS):
            val_from = snap_from.get(f, "")
            val_to = snap_to.get(f, "")
            if val_from != val_to:
                diff[f] = {"from": val_from, "to": val_to}

        return diff

    def rollback(self, brand_id: str, to_version: int) -> Optional[Brand]:
        """Rollback a brand to a previous version.

        Creates a new version with the target version's data. The current
        state becomes a version snapshot before rollback is applied.

        Returns the updated brand, or None if the brand or version
        doesn't exist.
        """
        current = self.get(brand_id)
        if not current:
            return None

        target_version = self.get_version(brand_id, to_version)
        if not target_version:
            return None

        target_data = target_version.get_snapshot_dict()

        # Fields to restore from the target version (versioned fields only)
        restore_fields = {f: target_data.get(f, "") for f in _VERSIONED_FIELDS}

        conn = self._connect()
        try:
            # Apply rollback
            new_version = current.version + 1
            set_parts = []
            values_list = []
            for k, v in restore_fields.items():
                set_parts.append(f"{_quote_col(k)}=?")
                values_list.append(v)

            values_list.extend([_now_iso(), new_version, brand_id, self.workspace_id])
            set_clause = ", ".join(set_parts)

            conn.execute(
                f"UPDATE brands SET {set_clause}, updated_at=?, version=? "
                f"WHERE id=? AND workspace_id=?",
                values_list,
            )

            # Snapshot the rolled-back state
            updated_row = conn.execute(
                "SELECT * FROM brands WHERE id = ? AND workspace_id = ?",
                (brand_id, self.workspace_id),
            ).fetchone()
            if updated_row:
                updated_brand = Brand.from_row(updated_row)
                self._snapshot_version(
                    conn, updated_brand,
                    f"rollback_to_v{to_version}",
                )

            conn.commit()

            logger.info(
                "brand_rollback id=%s to_version=%d new_version=%d workspace=%s",
                brand_id, to_version, new_version, self.workspace_id,
            )
            return self.get(brand_id)
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli() -> None:
    parser = argparse.ArgumentParser(description="BrandOS Brand Store CLI")
    parser.add_argument(
        "--db", default=os.environ.get("BRANDOS_DB_PATH", "brandos.db"),
        help="SQLite database path",
    )
    parser.add_argument(
        "--workspace", default=os.environ.get("BRANDOS_WORKSPACE_ID", "default"),
        help="Workspace ID",
    )

    sub = parser.add_subparsers(dest="command")

    # create
    p_create = sub.add_parser("create", help="Create a new brand")
    p_create.add_argument("--name", required=True)
    p_create.add_argument("--industry", default="")
    p_create.add_argument("--tagline", default="")
    p_create.add_argument("--description", default="")
    p_create.add_argument("--tone", default="")
    p_create.add_argument("--personality", default="")
    p_create.add_argument("--values", default="")
    p_create.add_argument("--target-audience", default="")
    p_create.add_argument("--website", default="")
    p_create.add_argument("--logo-url", default="")
    p_create.add_argument("--color-primary", default="")
    p_create.add_argument("--color-secondary", default="")
    p_create.add_argument("--prohibited-terms", default="")

    # list
    p_list = sub.add_parser("list", help="List brands")
    p_list.add_argument("--status", default="active")
    p_list.add_argument("--limit", type=int, default=50)

    # get
    p_get = sub.add_parser("get", help="Get a brand by ID")
    p_get.add_argument("id")

    # update
    p_update = sub.add_parser("update", help="Update a brand")
    p_update.add_argument("id")
    p_update.add_argument("--name")
    p_update.add_argument("--industry")
    p_update.add_argument("--tagline")
    p_update.add_argument("--description")
    p_update.add_argument("--tone")
    p_update.add_argument("--personality")
    p_update.add_argument("--values")
    p_update.add_argument("--target-audience")
    p_update.add_argument("--website")
    p_update.add_argument("--logo-url")
    p_update.add_argument("--color-primary")
    p_update.add_argument("--color-secondary")
    p_update.add_argument("--prohibited-terms")

    # archive
    p_archive = sub.add_parser("archive", help="Archive a brand")
    p_archive.add_argument("id")

    # restore
    p_restore = sub.add_parser("restore", help="Restore an archived brand")
    p_restore.add_argument("id")

    # search
    p_search = sub.add_parser("search", help="Search brands")
    p_search.add_argument("query")
    p_search.add_argument("--limit", type=int, default=20)

    # export
    p_export = sub.add_parser("export", help="Export brands as JSON")

    # versions
    p_versions = sub.add_parser("versions", help="List all versions of a brand")
    p_versions.add_argument("id")

    # get-version
    p_gv = sub.add_parser("get-version", help="Get a specific version of a brand")
    p_gv.add_argument("id")
    p_gv.add_argument("--version", type=int, required=True)

    # diff
    p_diff = sub.add_parser("diff", help="Diff two versions of a brand")
    p_diff.add_argument("id")
    p_diff.add_argument("--from", dest="from_version", type=int, required=True)
    p_diff.add_argument("--to", dest="to_version", type=int, required=True)

    # rollback
    p_rb = sub.add_parser("rollback", help="Rollback a brand to a previous version")
    p_rb.add_argument("id")
    p_rb.add_argument("--version", type=int, required=True)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    store = BrandStore(args.db, args.workspace)

    if args.command == "create":
        b = store.create(
            name=args.name,
            industry=args.industry,
            tagline=args.tagline,
            description=args.description,
            tone=args.tone,
            personality=args.personality,
            values=args.values,
            target_audience=args.target_audience,
            website=args.website,
            logo_url=args.logo_url,
            color_primary=args.color_primary,
            color_secondary=args.color_secondary,
            prohibited_terms=args.prohibited_terms,
        )
        print(json.dumps(b.to_dict(), indent=2, ensure_ascii=False))

    elif args.command == "list":
        brands = store.list(status=args.status, limit=args.limit)
        for b in brands:
            print(f"  {b.id[:8]}  v{b.version}  {b.name:<30}  {b.industry:<20}  {b.status}")
        if not brands:
            print("  (no brands)")

    elif args.command == "get":
        b = store.get(args.id)
        if b:
            print(json.dumps(b.to_dict(), indent=2, ensure_ascii=False))
        else:
            print(f"Brand {args.id} not found")
            raise SystemExit(1)

    elif args.command == "update":
        fields = {
            k: v for k, v in vars(args).items()
            if k not in ("id", "command", "db", "workspace") and v is not None
        }
        b = store.update(args.id, **fields)
        if b:
            print(json.dumps(b.to_dict(), indent=2, ensure_ascii=False))
        else:
            print(f"Brand {args.id} not found")
            raise SystemExit(1)

    elif args.command == "archive":
        if store.archive(args.id):
            print(f"Brand {args.id} archived")
        else:
            print(f"Brand {args.id} not found or already archived")
            raise SystemExit(1)

    elif args.command == "restore":
        if store.restore(args.id):
            print(f"Brand {args.id} restored")
        else:
            print(f"Brand {args.id} not found or already active")
            raise SystemExit(1)

    elif args.command == "search":
        brands = store.search(args.query, limit=args.limit)
        for b in brands:
            print(f"  {b.id[:8]}  v{b.version}  {b.name:<30}  {b.industry:<20}")
        if not brands:
            print("  (no matches)")

    elif args.command == "export":
        print(store.export_json())

    elif args.command == "versions":
        versions = store.list_versions(args.id)
        for v in versions:
            print(f"  v{v.version:<3}  {v.created_at}  changed: {v.changed_fields}")
        if not versions:
            print("  (no versions)")

    elif args.command == "get-version":
        v = store.get_version(args.id, args.version)
        if v:
            snap = v.get_snapshot_dict()
            print(json.dumps(snap, indent=2, ensure_ascii=False))
        else:
            print(f"Version {args.version} not found for brand {args.id}")
            raise SystemExit(1)

    elif args.command == "diff":
        diff = store.diff_versions(args.id, args.from_version, args.to_version)
        if diff is not None:
            if diff:
                print(json.dumps(diff, indent=2, ensure_ascii=False))
            else:
                print(f"  No differences between v{args.from_version} and v{args.to_version}")
        else:
            print(f"Could not compare versions (check brand ID and version numbers)")
            raise SystemExit(1)

    elif args.command == "rollback":
        b = store.rollback(args.id, args.version)
        if b:
            print(json.dumps(b.to_dict(), indent=2, ensure_ascii=False))
        else:
            print(f"Rollback failed (check brand ID and version number)")
            raise SystemExit(1)


if __name__ == "__main__":
    _cli()
