#!/usr/bin/env python3
"""BrandOS Persona Engine — versioned CRUD storage with audit trail.

Provides persona management with immutable version history, rollback,
diff queries, and a full audit trail. All writes are append-only;
every mutation creates a new version row.

Storage: SQLite (one file per workspace). Schema is created on first use.

Usage:
    from persona_engine import PersonaEngine
    engine = PersonaEngine("/path/to/persona.db")
    persona = engine.create_persona("luxury-brand", {"tone": "refined"}, actor="system")
    versions = engine.list_versions(persona["id"])
    diff = engine.diff_versions(persona["id"], 1, 2)
    engine.rollback(persona["id"], target_version=1, actor="admin")

CLI:
    python scripts/persona_engine.py --db persona.db create --name test --data '{"k":"v"}'
    python scripts/persona_engine.py --db persona.db get <id>
    python scripts/persona_engine.py --db persona.db list
    python scripts/persona_engine.py --db persona_engine.py --db persona.db update <id> --data '{"k":"v2"}'
    python scripts/persona_engine.py --db persona.db versions <id>
    python scripts/persona_engine.py --db persona.db diff <id> --v1 1 --v2 2
    python scripts/persona_engine.py --db persona.db rollback <id> --target-version 1
    python scripts/persona_engine.py --db persona.db audit <id>
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Persona name validation: alphanumeric, hyphens, underscores, 1-128 chars.
_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,127}$")

# Maximum data payload size (1 MB JSON).
_MAX_DATA_BYTES = 1_048_576

# Maximum change_reason length.
_MAX_REASON_LEN = 1024

# Sensitive keys that must not appear in persona data (security gate).
_SENSITIVE_KEY_PATTERNS = re.compile(
    r"(token|api[_-]?key|password|passwd|secret|authorization|credential|bearer|private[_-]?key)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class PersonaError(Exception):
    """Base error for persona operations."""


class PersonaNotFoundError(PersonaError):
    """Raised when a persona ID does not exist."""


class VersionNotFoundError(PersonaError):
    """Raised when a version number does not exist for a persona."""


class ValidationError(PersonaError):
    """Raised when input validation fails."""


class DuplicateNameError(PersonaError):
    """Raised when creating a persona with a name that already exists."""


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS personas (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    current_version INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    created_by TEXT NOT NULL DEFAULT 'system',
    is_deleted INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS persona_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    persona_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    data TEXT NOT NULL,
    data_hash TEXT NOT NULL,
    created_at TEXT NOT NULL NOT NULL,
    created_by TEXT NOT NULL DEFAULT 'system',
    change_reason TEXT DEFAULT '',
    FOREIGN KEY (persona_id) REFERENCES personas(id),
    UNIQUE(persona_id, version)
);

CREATE TABLE IF NOT EXISTS persona_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    persona_id TEXT NOT NULL,
    action TEXT NOT NULL,
    actor TEXT NOT NULL DEFAULT 'system',
    timestamp TEXT NOT NULL,
    details TEXT DEFAULT '{}',
    FOREIGN KEY (persona_id) REFERENCES personas(id)
);

CREATE INDEX IF NOT EXISTS idx_versions_persona ON persona_versions(persona_id);
CREATE INDEX IF NOT EXISTS idx_audit_persona ON persona_audit(persona_id);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON persona_audit(timestamp);
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    """Current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


def _validate_name(name: str) -> None:
    """Validate persona name format."""
    if not name or not isinstance(name, str):
        raise ValidationError("Persona name must be a non-empty string")
    if not _NAME_RE.match(name):
        raise ValidationError(
            f"Invalid persona name '{name}': must start with alphanumeric, "
            "contain only [a-zA-Z0-9_-], and be 1-128 characters"
        )


def _validate_data(data: Any) -> str:
    """Validate and serialize persona data to JSON string.

    Returns the JSON string.
    Raises ValidationError on invalid data.
    """
    if data is None:
        raise ValidationError("Persona data must not be null")
    if not isinstance(data, dict):
        raise ValidationError("Persona data must be a JSON object (dict)")

    # Check for sensitive keys
    for key in data:
        if _SENSITIVE_KEY_PATTERNS.search(str(key)):
            raise ValidationError(
                f"Persona data contains sensitive key '{key}': "
                "persona data must not store tokens, keys, passwords, or secrets"
            )

    try:
        json_str = json.dumps(data, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError) as e:
        raise ValidationError(f"Persona data is not JSON-serializable: {e}")

    if len(json_str.encode("utf-8")) > _MAX_DATA_BYTES:
        raise ValidationError(
            f"Persona data exceeds {_MAX_DATA_BYTES} bytes when serialized"
        )

    return json_str


def _compute_hash(data_json: str) -> str:
    """SHA-256 hash of serialized data for change detection."""
    import hashlib
    return hashlib.sha256(data_json.encode("utf-8")).hexdigest()


def _row_to_persona(row: sqlite3.Row) -> dict:
    """Convert a personas table row to a dict."""
    return {
        "id": row["id"],
        "name": row["name"],
        "current_version": row["current_version"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "created_by": row["created_by"],
        "is_deleted": bool(row["is_deleted"]),
    }


def _row_to_version(row: sqlite3.Row) -> dict:
    """Convert a persona_versions row to a dict."""
    return {
        "id": row["id"],
        "persona_id": row["persona_id"],
        "version": row["version"],
        "data": json.loads(row["data"]),
        "data_hash": row["data_hash"],
        "created_at": row["created_at"],
        "created_by": row["created_by"],
        "change_reason": row["change_reason"],
    }


def _row_to_audit(row: sqlite3.Row) -> dict:
    """Convert a persona_audit row to a dict."""
    return {
        "id": row["id"],
        "persona_id": row["persona_id"],
        "action": row["action"],
        "actor": row["actor"],
        "timestamp": row["timestamp"],
        "details": json.loads(row["details"]),
    }


def _generate_id() -> str:
    """Generate a unique persona ID (UUID4 without hyphens)."""
    import uuid
    return uuid.uuid4().hex


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class PersonaEngine:
    """Versioned persona storage with audit trail.

    All public methods are safe for concurrent use (SQLite WAL mode).
    Every write creates an immutable version snapshot.
    """

    def __init__(self, db_path: str) -> None:
        """Initialize the engine with a SQLite database path.

        Creates the database and schema if they don't exist.

        Args:
            db_path: Path to the SQLite database file.
        """
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA_SQL)
        self._conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "PersonaEngine":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # ---- Audit helper ----

    def _audit(
        self, persona_id: str, action: str, actor: str, details: dict | None = None
    ) -> None:
        """Write an audit log entry."""
        self._conn.execute(
            "INSERT INTO persona_audit (persona_id, action, actor, timestamp, details) "
            "VALUES (?, ?, ?, ?, ?)",
            (persona_id, action, actor, _now_iso(), json.dumps(details or {})),
        )

    # ---- CRUD ----

    def create_persona(
        self,
        name: str,
        data: dict,
        *,
        actor: str = "system",
        persona_id: str | None = None,
        change_reason: str = "initial creation",
    ) -> dict:
        """Create a new persona with version 1.

        Args:
            name: Unique persona name (alphanumeric, hyphens, underscores).
            data: Initial persona data (JSON-serializable dict, no sensitive keys).
            actor: Who is creating this persona.
            persona_id: Optional custom ID (default: auto-generated UUID).
            change_reason: Reason for creation.

        Returns:
            Dict with persona metadata including id, name, version info.

        Raises:
            ValidationError: On invalid name or data.
            DuplicateNameError: If name already exists.
        """
        _validate_name(name)
        data_json = _validate_data(data)
        data_hash = _compute_hash(data_json)

        pid = persona_id or _generate_id()
        now = _now_iso()

        try:
            self._conn.execute(
                "INSERT INTO personas (id, name, current_version, created_at, updated_at, created_by) "
                "VALUES (?, ?, 1, ?, ?, ?)",
                (pid, name, now, now, actor),
            )
        except sqlite3.IntegrityError as e:
            if "UNIQUE constraint failed: personas.name" in str(e):
                raise DuplicateNameError(f"Persona with name '{name}' already exists")
            raise

        self._conn.execute(
            "INSERT INTO persona_versions (persona_id, version, data, data_hash, created_at, created_by, change_reason) "
            "VALUES (?, 1, ?, ?, ?, ?, ?)",
            (pid, data_json, data_hash, now, actor, change_reason),
        )

        self._audit(pid, "create", actor, {"name": name, "version": 1})
        self._conn.commit()

        return self.get_persona(pid)

    def get_persona(self, persona_id: str, *, include_deleted: bool = False) -> dict:
        """Get persona metadata (not version data).

        Args:
            persona_id: The persona ID.
            include_deleted: If True, include soft-deleted personas.

        Returns:
            Dict with persona metadata.

        Raises:
            PersonaNotFoundError: If persona doesn't exist.
        """
        row = self._conn.execute(
            "SELECT * FROM personas WHERE id = ?", (persona_id,)
        ).fetchone()

        if not row:
            raise PersonaNotFoundError(f"Persona '{persona_id}' not found")

        persona = _row_to_persona(row)

        if persona["is_deleted"] and not include_deleted:
            raise PersonaNotFoundError(f"Persona '{persona_id}' has been deleted")

        return persona

    def get_persona_by_name(self, name: str, *, include_deleted: bool = False) -> dict:
        """Get persona metadata by name.

        Args:
            name: The persona name.
            include_deleted: If True, include soft-deleted personas.

        Returns:
            Dict with persona metadata.

        Raises:
            PersonaNotFoundError: If persona doesn't exist.
        """
        row = self._conn.execute(
            "SELECT * FROM personas WHERE name = ?", (name,)
        ).fetchone()

        if not row:
            raise PersonaNotFoundError(f"Persona with name '{name}' not found")

        persona = _row_to_persona(row)

        if persona["is_deleted"] and not include_deleted:
            raise PersonaNotFoundError(f"Persona '{name}' has been deleted")

        return persona

    def list_personas(
        self, *, include_deleted: bool = False, limit: int = 100, offset: int = 0
    ) -> List[dict]:
        """List all personas.

        Args:
            include_deleted: If True, include soft-deleted personas.
            limit: Maximum number of results.
            offset: Skip first N results.

        Returns:
            List of persona metadata dicts.
        """
        query = "SELECT * FROM personas"
        params: list = []

        if not include_deleted:
            query += " WHERE is_deleted = 0"

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = self._conn.execute(query, params).fetchall()
        return [_row_to_persona(r) for r in rows]

    def update_persona(
        self,
        persona_id: str,
        data: dict,
        *,
        actor: str = "system",
        change_reason: str = "",
    ) -> dict:
        """Update persona data, creating a new version.

        The persona's current_version is incremented and a new immutable
        version row is inserted. If data is identical to the current version,
        the write is skipped (idempotent).

        Args:
            persona_id: The persona ID.
            data: New persona data (full replacement).
            actor: Who is performing the update.
            change_reason: Reason for the update.

        Returns:
            Updated persona metadata dict.

        Raises:
            PersonaNotFoundError: If persona doesn't exist.
            ValidationError: On invalid data.
        """
        persona = self.get_persona(persona_id)  # also checks is_deleted
        data_json = _validate_data(data)
        data_hash = _compute_hash(data_json)

        # Get current version to check for no-op
        current = self._conn.execute(
            "SELECT data_hash FROM persona_versions WHERE persona_id = ? AND version = ?",
            (persona_id, persona["current_version"]),
        ).fetchone()

        if current and current["data_hash"] == data_hash:
            # No-op: data hasn't changed. Return current state without creating version.
            return persona

        new_version = persona["current_version"] + 1
        now = _now_iso()

        self._conn.execute(
            "UPDATE personas SET current_version = ?, updated_at = ? WHERE id = ?",
            (new_version, now, persona_id),
        )

        self._conn.execute(
            "INSERT INTO persona_versions (persona_id, version, data, data_hash, created_at, created_by, change_reason) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (persona_id, new_version, data_json, data_hash, now, actor, change_reason),
        )

        self._audit(persona_id, "update", actor, {
            "new_version": new_version,
            "change_reason": change_reason,
        })
        self._conn.commit()

        return self.get_persona(persona_id)

    def delete_persona(
        self, persona_id: str, *, actor: str = "system", reason: str = ""
    ) -> dict:
        """Soft-delete a persona. Data is preserved for audit.

        Args:
            persona_id: The persona ID.
            actor: Who is deleting.
            reason: Reason for deletion.

        Returns:
            The deleted persona metadata.

        Raises:
            PersonaNotFoundError: If persona doesn't exist or already deleted.
        """
        persona = self.get_persona(persona_id)  # raises if already deleted
        now = _now_iso()

        self._conn.execute(
            "UPDATE personas SET is_deleted = 1, updated_at = ? WHERE id = ?",
            (now, persona_id),
        )

        self._audit(persona_id, "delete", actor, {"reason": reason})
        self._conn.commit()

        return self.get_persona(persona_id, include_deleted=True)

    # ---- Versioning ----

    def get_version(self, persona_id: str, version: int) -> dict:
        """Get a specific version of a persona.

        Args:
            persona_id: The persona ID.
            version: Version number (1-based).

        Returns:
            Version dict including data.

        Raises:
            PersonaNotFoundError: If persona doesn't exist.
            VersionNotFoundError: If version doesn't exist.
        """
        self.get_persona(persona_id)  # validate persona exists and not deleted

        row = self._conn.execute(
            "SELECT * FROM persona_versions WHERE persona_id = ? AND version = ?",
            (persona_id, version),
        ).fetchone()

        if not row:
            raise VersionNotFoundError(
                f"Version {version} not found for persona '{persona_id}'"
            )

        return _row_to_version(row)

    def get_current_version(self, persona_id: str) -> dict:
        """Get the current (latest) version of a persona.

        Args:
            persona_id: The persona ID.

        Returns:
            Version dict including data.

        Raises:
            PersonaNotFoundError: If persona doesn't exist.
        """
        persona = self.get_persona(persona_id)
        return self.get_version(persona_id, persona["current_version"])

    def list_versions(
        self, persona_id: str, *, limit: int = 100, offset: int = 0
    ) -> List[dict]:
        """List all versions of a persona, newest first.

        Args:
            persona_id: The persona ID.
            limit: Maximum results.
            offset: Skip first N.

        Returns:
            List of version dicts (without data payload for efficiency).

        Raises:
            PersonaNotFoundError: If persona doesn't exist.
        """
        self.get_persona(persona_id)

        rows = self._conn.execute(
            "SELECT id, persona_id, version, data_hash, created_at, created_by, change_reason "
            "FROM persona_versions WHERE persona_id = ? ORDER BY version DESC LIMIT ? OFFSET ?",
            (persona_id, limit, offset),
        ).fetchall()

        return [
            {
                "id": r["id"],
                "persona_id": r["persona_id"],
                "version": r["version"],
                "data_hash": r["data_hash"],
                "created_at": r["created_at"],
                "created_by": r["created_by"],
                "change_reason": r["change_reason"],
            }
            for r in rows
        ]

    def diff_versions(
        self, persona_id: str, version_a: int, version_b: int
    ) -> dict:
        """Compute the diff between two versions of a persona.

        Returns a structured diff showing added, removed, and changed keys.

        Args:
            persona_id: The persona ID.
            version_a: First version (base).
            version_b: Second version (target).

        Returns:
            Dict with 'added', 'removed', 'changed', 'unchanged' keys.

        Raises:
            PersonaNotFoundError: If persona doesn't exist.
            VersionNotFoundError: If either version doesn't exist.
        """
        va = self.get_version(persona_id, version_a)
        vb = self.get_version(persona_id, version_b)

        data_a = va["data"]
        data_b = vb["data"]

        return _compute_diff(data_a, data_b)

    # ---- Rollback ----

    def rollback(
        self,
        persona_id: str,
        target_version: int,
        *,
        actor: str = "system",
        change_reason: str = "",
    ) -> dict:
        """Rollback a persona to a previous version.

        Creates a new version with the target version's data. The target
        version's data becomes the new current state.

        Args:
            persona_id: The persona ID.
            target_version: Version to rollback to.
            actor: Who is performing the rollback.
            change_reason: Reason for rollback.

        Returns:
            Updated persona metadata.

        Raises:
            PersonaNotFoundError: If persona doesn't exist.
            VersionNotFoundError: If target version doesn't exist.
            ValidationError: If already at target version (no-op).
        """
        persona = self.get_persona(persona_id)
        target = self.get_version(persona_id, target_version)

        if persona["current_version"] == target_version:
            raise ValidationError(
                f"Persona '{persona_id}' is already at version {target_version}"
            )

        reason = change_reason or f"rollback to version {target_version}"

        return self.update_persona(
            persona_id,
            target["data"],
            actor=actor,
            change_reason=reason,
        )

    # ---- Audit trail ----

    def get_audit_trail(
        self, persona_id: str, *, limit: int = 100, offset: int = 0
    ) -> List[dict]:
        """Get the audit trail for a persona.

        Args:
            persona_id: The persona ID.
            limit: Maximum results.
            offset: Skip first N.

        Returns:
            List of audit entry dicts, newest first.

        Raises:
            PersonaNotFoundError: If persona doesn't exist (including deleted).
        """
        # Allow audit trail access for deleted personas — the audit trail itself
        # must be accessible after deletion for compliance.
        self.get_persona(persona_id, include_deleted=True)

        rows = self._conn.execute(
            "SELECT * FROM persona_audit WHERE persona_id = ? ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            (persona_id, limit, offset),
        ).fetchall()

        return [_row_to_audit(r) for r in rows]


# ---------------------------------------------------------------------------
# Diff computation
# ---------------------------------------------------------------------------


def _compute_diff(data_a: dict, data_b: dict) -> dict:
    """Compute a structured diff between two JSON dicts.

    Handles nested dicts recursively. Lists are compared as atomic values.

    Returns:
        Dict with keys: 'added', 'removed', 'changed', 'unchanged'.
        Each is a list of entries: key paths with old/new values.
    """
    added = []
    removed = []
    changed = []
    unchanged = []

    all_keys = set(data_a.keys()) | set(data_b.keys())

    for key in sorted(all_keys):
        in_a = key in data_a
        in_b = key in data_b

        if in_a and not in_b:
            removed.append({"key": key, "old_value": data_a[key]})
        elif not in_a and in_b:
            added.append({"key": key, "new_value": data_b[key]})
        elif data_a[key] != data_b[key]:
            # Recursive diff for nested dicts
            if isinstance(data_a[key], dict) and isinstance(data_b[key], dict):
                nested = _compute_diff(data_a[key], data_b[key])
                for item in nested["added"]:
                    added.append({"key": f"{key}.{item['key']}", "new_value": item["new_value"]})
                for item in nested["removed"]:
                    removed.append({"key": f"{key}.{item['key']}", "old_value": item["old_value"]})
                for item in nested["changed"]:
                    changed.append({
                        "key": f"{key}.{item['key']}",
                        "old_value": item["old_value"],
                        "new_value": item["new_value"],
                    })
                for item in nested["unchanged"]:
                    unchanged.append({"key": f"{key}.{item['key']}"})
            else:
                changed.append({
                    "key": key,
                    "old_value": data_a[key],
                    "new_value": data_b[key],
                })
        else:
            unchanged.append({"key": key})

    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "unchanged": unchanged,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli() -> None:
    """Command-line interface for persona operations."""
    parser = argparse.ArgumentParser(description="BrandOS Persona Engine CLI")
    parser.add_argument(
        "--db",
        default=os.environ.get("PERSONA_DB", "persona.db"),
        help="SQLite database path (default: persona.db or $PERSONA_DB)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # create
    p_create = sub.add_parser("create", help="Create a new persona")
    p_create.add_argument("--name", required=True, help="Persona name")
    p_create.add_argument("--data", required=True, help="JSON data string")
    p_create.add_argument("--actor", default="cli", help="Actor name")
    p_create.add_argument("--reason", default="initial creation", help="Change reason")

    # get
    p_get = sub.add_parser("get", help="Get persona by ID")
    p_get.add_argument("id", help="Persona ID")

    # get-by-name
    p_gbn = sub.add_parser("get-by-name", help="Get persona by name")
    p_gbn.add_argument("name", help="Persona name")

    # list
    sub.add_parser("list", help="List all personas")

    # update
    p_update = sub.add_parser("update", help="Update persona data")
    p_update.add_argument("id", help="Persona ID")
    p_update.add_argument("--data", required=True, help="New JSON data")
    p_update.add_argument("--actor", default="cli", help="Actor name")
    p_update.add_argument("--reason", default="", help="Change reason")

    # delete
    p_delete = sub.add_parser("delete", help="Soft-delete a persona")
    p_delete.add_argument("id", help="Persona ID")
    p_delete.add_argument("--actor", default="cli", help="Actor name")
    p_delete.add_argument("--reason", default="", help="Reason")

    # versions
    p_versions = sub.add_parser("versions", help="List versions")
    p_versions.add_argument("id", help="Persona ID")

    # get-version
    p_gv = sub.add_parser("get-version", help="Get specific version")
    p_gv.add_argument("id", help="Persona ID")
    p_gv.add_argument("--version", type=int, required=True, help="Version number")

    # diff
    p_diff = sub.add_parser("diff", help="Diff two versions")
    p_diff.add_argument("id", help="Persona ID")
    p_diff.add_argument("--v1", type=int, required=True, help="Base version")
    p_diff.add_argument("--v2", type=int, required=True, help="Target version")

    # rollback
    p_rb = sub.add_parser("rollback", help="Rollback to a previous version")
    p_rb.add_argument("id", help="Persona ID")
    p_rb.add_argument("--target-version", type=int, required=True, help="Target version")
    p_rb.add_argument("--actor", default="cli", help="Actor name")
    p_rb.add_argument("--reason", default="", help="Reason")

    # audit
    p_audit = sub.add_parser("audit", help="Show audit trail")
    p_audit.add_argument("id", help="Persona ID")

    args = parser.parse_args()

    engine = PersonaEngine(args.db)
    try:
        result = None

        if args.command == "create":
            data = json.loads(args.data)
            result = engine.create_persona(
                args.name, data, actor=args.actor, change_reason=args.reason
            )
        elif args.command == "get":
            result = engine.get_persona(args.id)
        elif args.command == "get-by-name":
            result = engine.get_persona_by_name(args.name)
        elif args.command == "list":
            result = engine.list_personas()
        elif args.command == "update":
            data = json.loads(args.data)
            result = engine.update_persona(
                args.id, data, actor=args.actor, change_reason=args.reason
            )
        elif args.command == "delete":
            result = engine.delete_persona(args.id, actor=args.actor, reason=args.reason)
        elif args.command == "versions":
            result = engine.list_versions(args.id)
        elif args.command == "get-version":
            result = engine.get_version(args.id, args.version)
        elif args.command == "diff":
            result = engine.diff_versions(args.id, args.v1, args.v2)
        elif args.command == "rollback":
            result = engine.rollback(
                args.id, args.target_version, actor=args.actor, change_reason=args.reason
            )
        elif args.command == "audit":
            result = engine.get_audit_trail(args.id)

        if result is not None:
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))

    except PersonaError as e:
        print(json.dumps({"error": str(e)}, indent=2), file=sys.stderr)
        sys.exit(1)
    finally:
        engine.close()


if __name__ == "__main__":
    _cli()
