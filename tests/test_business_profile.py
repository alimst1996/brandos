#!/usr/bin/env python3
"""Tests for business profile storage and API.

Run: python -m pytest tests/test_business_profile.py -v
"""

import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_SCRIPT_DIR = _HERE.parent / "scripts"
sys.path.insert(0, str(_SCRIPT_DIR))

from business_profile import (
    BusinessProfile,
    BusinessProfileStore,
    ValidationError,
    _generate_id,
    _redact_dict,
    _redact_name,
    validate_profile,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path):
    """Return a temporary database path."""
    return str(tmp_path / "test_profiles.db")


@pytest.fixture
def store(tmp_db):
    """Return a BusinessProfileStore bound to workspace 'ws1'."""
    return BusinessProfileStore(tmp_db, "ws1")


@pytest.fixture
def store_ws2(tmp_db):
    """Return a BusinessProfileStore bound to workspace 'ws2'."""
    return BusinessProfileStore(tmp_db, "ws2")


# ---------------------------------------------------------------------------
# ID generation
# ---------------------------------------------------------------------------

class TestIdGeneration:
    def test_deterministic(self):
        """Same (workspace, name) always produces the same ID."""
        id1 = _generate_id("ws1", "Acme Corp")
        id2 = _generate_id("ws1", "Acme Corp")
        assert id1 == id2

    def test_case_insensitive_name(self):
        """ID is the same regardless of name casing."""
        id1 = _generate_id("ws1", "Acme Corp")
        id2 = _generate_id("ws1", "acme corp")
        assert id1 == id2

    def test_different_workspace_different_id(self):
        """Same name in different workspaces produces different IDs."""
        id1 = _generate_id("ws1", "Acme")
        id2 = _generate_id("ws2", "Acme")
        assert id1 != id2

    def test_different_name_different_id(self):
        """Different names in same workspace produce different IDs."""
        id1 = _generate_id("ws1", "Acme")
        id2 = _generate_id("ws1", "Beta")
        assert id1 != id2

    def test_uuid_format(self):
        """Generated ID is a valid UUID string."""
        import uuid
        uid = _generate_id("ws1", "Test")
        uuid.UUID(uid)  # raises if invalid


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_valid_profile(self, store):
        errors = validate_profile(BusinessProfile(
            id="test", name="Acme", workspace_id="ws1",
        ))
        assert errors == []

    def test_empty_name(self):
        errors = validate_profile(BusinessProfile(
            id="test", name="", workspace_id="ws1",
        ))
        assert any(e.field_name == "name" for e in errors)

    def test_whitespace_only_name(self):
        errors = validate_profile(BusinessProfile(
            id="test", name="   ", workspace_id="ws1",
        ))
        assert any(e.field_name == "name" for e in errors)

    def test_name_too_long(self):
        errors = validate_profile(BusinessProfile(
            id="test", name="x" * 201, workspace_id="ws1",
        ))
        assert any(e.field_name == "name" for e in errors)

    def test_industry_too_long(self):
        errors = validate_profile(BusinessProfile(
            id="test", name="Acme", industry="x" * 101, workspace_id="ws1",
        ))
        assert any(e.field_name == "industry" for e in errors)

    def test_description_too_long(self):
        errors = validate_profile(BusinessProfile(
            id="test", name="Acme", description="x" * 2001, workspace_id="ws1",
        ))
        assert any(e.field_name == "description" for e in errors)

    def test_bad_website(self):
        errors = validate_profile(BusinessProfile(
            id="test", name="Acme", website="ftp://bad", workspace_id="ws1",
        ))
        assert any(e.field_name == "website" for e in errors)

    def test_good_website_http(self):
        errors = validate_profile(BusinessProfile(
            id="test", name="Acme", website="http://example.com", workspace_id="ws1",
        ))
        assert not any(e.field_name == "website" for e in errors)

    def test_good_website_https(self):
        errors = validate_profile(BusinessProfile(
            id="test", name="Acme", website="https://example.com", workspace_id="ws1",
        ))
        assert not any(e.field_name == "website" for e in errors)

    def test_invalid_status(self):
        errors = validate_profile(BusinessProfile(
            id="test", name="Acme", workspace_id="ws1", status="deleted",
        ))
        assert any(e.field_name == "status" for e in errors)

    def test_missing_workspace(self):
        errors = validate_profile(BusinessProfile(
            id="test", name="Acme", workspace_id="",
        ))
        assert any(e.field_name == "workspace_id" for e in errors)


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

class TestCreate:
    def test_create_basic(self, store):
        p = store.create(name="Acme Corp", industry="Tech")
        assert p.name == "Acme Corp"
        assert p.industry == "Tech"
        assert p.status == "active"
        assert p.workspace_id == "ws1"
        assert p.id
        assert p.created_at

    def test_create_with_all_fields(self, store):
        p = store.create(
            name="Full Co",
            industry="Finance",
            description="A finance company",
            target_audience="Enterprises",
            website="https://full.co",
            logo_url="https://full.co/logo.png",
            notes="Internal note",
            internal_tags="tag1,tag2",
        )
        assert p.name == "Full Co"
        assert p.website == "https://full.co"
        assert p.notes == "Internal note"

    def test_create_strips_whitespace(self, store):
        p = store.create(name="  Trimmed  ", industry="  Tech  ")
        assert p.name == "Trimmed"
        assert p.industry == "Tech"

    def test_create_idempotent(self, store):
        """Creating the same (workspace, name) twice returns the existing profile."""
        p1 = store.create(name="Idem Corp")
        p2 = store.create(name="Idem Corp")
        assert p1.id == p2.id

    def test_create_validation_error(self, store):
        with pytest.raises(ValidationError) as exc_info:
            store.create(name="")
        assert exc_info.value.field_name == "name"

    def test_create_bad_website(self, store):
        with pytest.raises(ValidationError) as exc_info:
            store.create(name="Bad Web", website="not-a-url")
        assert exc_info.value.field_name == "website"

    def test_create_unique_per_workspace(self, store, store_ws2):
        """Same name in different workspaces creates separate profiles."""
        p1 = store.create(name="Global")
        p2 = store_ws2.create(name="Global")
        assert p1.id != p2.id
        assert store.count() == 1
        assert store_ws2.count() == 1


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

class TestRead:
    def test_get_existing(self, store):
        created = store.create(name="Readable")
        fetched = store.get(created.id)
        assert fetched is not None
        assert fetched.name == "Readable"

    def test_get_nonexistent(self, store):
        assert store.get("nonexistent-id") is None

    def test_get_by_name(self, store):
        store.create(name="Lookup Corp")
        p = store.get_by_name("Lookup Corp")
        assert p is not None
        assert p.name == "Lookup Corp"

    def test_get_by_name_case_insensitive(self, store):
        store.create(name="Case Corp")
        p = store.get_by_name("case corp")
        assert p is not None

    def test_get_by_name_nonexistent(self, store):
        assert store.get_by_name("No Such") is None

    def test_list_default_active(self, store):
        store.create(name="Active1")
        store.create(name="Active2")
        p = store.create(name="To Archive")
        store.archive(p.id)
        profiles = store.list()
        assert len(profiles) == 2
        names = {p.name for p in profiles}
        assert names == {"Active1", "Active2"}

    def test_list_archived(self, store):
        p = store.create(name="Old")
        store.archive(p.id)
        profiles = store.list(status="archived")
        assert len(profiles) == 1
        assert profiles[0].name == "Old"

    def test_list_limit(self, store):
        for i in range(10):
            store.create(name=f"Co{i}")
        profiles = store.list(limit=3)
        assert len(profiles) == 3

    def test_list_offset(self, store):
        for i in range(5):
            store.create(name=f"Offset{i}")
        page1 = store.list(limit=2, offset=0)
        page2 = store.list(limit=2, offset=2)
        assert page1[0].id != page2[0].id

    def test_list_empty_workspace(self, store):
        assert store.list() == []


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

class TestUpdate:
    def test_update_name(self, store):
        p = store.create(name="Old Name")
        updated = store.update(p.id, name="New Name")
        assert updated is not None
        assert updated.name == "New Name"

    def test_update_multiple_fields(self, store):
        p = store.create(name="Multi")
        updated = store.update(p.id, industry="AI", description="Updated desc")
        assert updated.industry == "AI"
        assert updated.updated_at > p.updated_at

    def test_update_nonexistent(self, store):
        result = store.update("no-such-id", name="X")
        assert result is None

    def test_update_invalid_field(self, store):
        p = store.create(name="Valid")
        with pytest.raises(ValidationError):
            store.update(p.id, id="hacked")

    def test_update_validation_error(self, store):
        p = store.create(name="Valid")
        with pytest.raises(ValidationError):
            store.update(p.id, name="")

    def test_update_preserves_id(self, store):
        p = store.create(name="Stable")
        updated = store.update(p.id, name="Changed")
        assert updated.id == p.id

    def test_update_no_fields_returns_current(self, store):
        p = store.create(name="NoChange")
        result = store.update(p.id)
        assert result is not None
        assert result.name == "NoChange"


# ---------------------------------------------------------------------------
# Archive / Restore
# ---------------------------------------------------------------------------

class TestArchiveRestore:
    def test_archive(self, store):
        p = store.create(name="To Archive")
        assert store.archive(p.id) is True
        fetched = store.get(p.id)
        assert fetched.status == "archived"

    def test_archive_nonexistent(self, store):
        assert store.archive("no-such") is False

    def test_archive_already_archived(self, store):
        p = store.create(name="Twice")
        store.archive(p.id)
        assert store.archive(p.id) is False  # already archived

    def test_restore(self, store):
        p = store.create(name="Restorable")
        store.archive(p.id)
        assert store.restore(p.id) is True
        fetched = store.get(p.id)
        assert fetched.status == "active"

    def test_restore_nonexistent(self, store):
        assert store.restore("no-such") is False

    def test_restore_already_active(self, store):
        p = store.create(name="Active")
        assert store.restore(p.id) is False


# ---------------------------------------------------------------------------
# Count
# ---------------------------------------------------------------------------

class TestCount:
    def test_count_active(self, store):
        store.create(name="A")
        store.create(name="B")
        assert store.count() == 2

    def test_count_archived(self, store):
        p = store.create(name="A")
        store.archive(p.id)
        assert store.count("archived") == 1
        assert store.count("active") == 0

    def test_count_empty(self, store):
        assert store.count() == 0


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

class TestSearch:
    def test_search_by_name(self, store):
        store.create(name="Searchable Corp", industry="Tech")
        results = store.search("Searchable")
        assert len(results) == 1
        assert results[0].name == "Searchable Corp"

    def test_search_by_industry(self, store):
        store.create(name="Other", industry="Healthcare")
        results = store.search("Healthcare")
        assert len(results) == 1

    def test_search_by_description(self, store):
        store.create(name="Desc", description="Makes widgets")
        results = store.search("widget")
        assert len(results) == 1

    def test_search_no_results(self, store):
        store.create(name="Here")
        results = store.search("nowhere")
        assert results == []

    def test_search_limit(self, store):
        for i in range(5):
            store.create(name=f"Search{i}", industry="Searchable")
        results = store.search("Searchable", limit=2)
        assert len(results) == 2

    def test_search_excludes_archived(self, store):
        p = store.create(name="Gone", industry="Vanishing")
        store.archive(p.id)
        results = store.search("Vanishing")
        assert results == []


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

class TestExport:
    def test_export_json_valid(self, store):
        store.create(name="Exportable")
        data = store.export_json()
        parsed = json.loads(data)
        assert len(parsed) == 1
        assert parsed[0]["name"] == "Exportable"

    def test_export_redacts_sensitive(self, store):
        store.create(name="Sensitive", notes="secret note", internal_tags="secret-tag")
        data = store.export_json()
        parsed = json.loads(data)
        assert parsed[0]["notes"] == "[REDACTED]"
        assert parsed[0]["internal_tags"] == "[REDACTED]"

    def test_export_empty(self, store):
        data = store.export_json()
        assert json.loads(data) == []


# ---------------------------------------------------------------------------
# Workspace isolation
# ---------------------------------------------------------------------------

class TestWorkspaceIsolation:
    def test_cannot_see_other_workspace(self, store, store_ws2):
        store.create(name="WS1 Only")
        assert store_ws2.list() == []
        assert store_ws2.count() == 0

    def test_cannot_get_other_workspace(self, store, store_ws2):
        p = store.create(name="Isolated")
        assert store_ws2.get(p.id) is None

    def test_cannot_update_other_workspace(self, store, store_ws2):
        p = store.create(name="Locked")
        result = store_ws2.update(p.id, name="Hacked")
        assert result is None

    def test_cannot_archive_other_workspace(self, store, store_ws2):
        p = store.create(name="Protected")
        assert store_ws2.archive(p.id) is False


# ---------------------------------------------------------------------------
# Redaction helpers
# ---------------------------------------------------------------------------

class TestRedaction:
    def test_redact_dict_hides_notes(self):
        d = {"name": "Acme", "notes": "secret", "internal_tags": "x"}
        redacted = _redact_dict(d)
        assert redacted["name"] == "Acme"
        assert redacted["notes"] == "[REDACTED]"
        assert redacted["internal_tags"] == "[REDACTED]"

    def test_redact_name_short(self):
        assert _redact_name("Ab") == "Ab"

    def test_redact_name_long(self):
        assert _redact_name("Acme Corp") == "Acm***"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_unicode_name(self, store):
        p = store.create(name="مهدی‌پور", industry="پارسی")
        assert p.name == "مهدی‌پور"
        fetched = store.get(p.id)
        assert fetched.name == "مهدی‌پور"

    def test_very_long_description(self, store):
        with pytest.raises(ValidationError):
            store.create(name="Long", description="x" * 2001)

    def test_empty_database(self, store):
        assert store.list() == []
        assert store.count() == 0
        assert store.search("anything") == []

    def test_concurrent_workspaces(self, tmp_db):
        """Multiple store instances on same DB, different workspaces."""
        s1 = BusinessProfileStore(tmp_db, "alpha")
        s2 = BusinessProfileStore(tmp_db, "beta")
        s1.create(name="Alpha Co")
        s2.create(name="Beta Co")
        assert s1.count() == 1
        assert s2.count() == 1
        assert s1.list()[0].name == "Alpha Co"
        assert s2.list()[0].name == "Beta Co"

    def test_special_characters_in_name(self, store):
        p = store.create(name="O'Brien & Sons (v2.0)")
        assert p.name == "O'Brien & Sons (v2.0)"
        assert store.get(p.id).name == "O'Brien & Sons (v2.0)"

    def test_create_then_archive_then_create_again(self, store):
        """Reactivating an archived profile with the same name."""
        p1 = store.create(name="Cycle")
        store.archive(p1.id)
        p2 = store.create(name="Cycle")
        assert p2.status == "active"
        assert p2.id == p1.id  # same deterministic ID

    def test_schema_idempotent(self, tmp_db):
        """Creating the store twice doesn't break anything."""
        s1 = BusinessProfileStore(tmp_db, "ws")
        s1.create(name="First")
        s2 = BusinessProfileStore(tmp_db, "ws")
        assert s2.count() == 1
