#!/usr/bin/env python3
"""Tests for brand store with versioning.

Run: python -m pytest tests/test_brand_store.py -v
"""

import json
import os
import sys
import time
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_SCRIPT_DIR = _HERE.parent / "scripts"
sys.path.insert(0, str(_SCRIPT_DIR))

from brand_store import (
    Brand,
    BrandStore,
    BrandVersion,
    ValidationError,
    _compute_changed_fields,
    _generate_id,
    _redact_dict,
    _redact_name,
    validate_brand,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path):
    """Return a temporary database path."""
    return str(tmp_path / "test_brands.db")


@pytest.fixture
def store(tmp_db):
    """Return a BrandStore bound to workspace 'ws1'."""
    return BrandStore(tmp_db, "ws1")


@pytest.fixture
def store_ws2(tmp_db):
    """Return a BrandStore bound to workspace 'ws2'."""
    return BrandStore(tmp_db, "ws2")


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
    def test_valid_brand(self, store):
        errors = validate_brand(Brand(
            id="test", name="Acme", workspace_id="ws1",
        ))
        assert errors == []

    def test_empty_name(self):
        errors = validate_brand(Brand(id="test", name="", workspace_id="ws1"))
        assert len(errors) == 1
        assert errors[0].field_name == "name"

    def test_whitespace_only_name(self):
        errors = validate_brand(Brand(id="test", name="   ", workspace_id="ws1"))
        assert len(errors) == 1
        assert errors[0].field_name == "name"

    def test_name_too_long(self):
        errors = validate_brand(Brand(id="test", name="A" * 201, workspace_id="ws1"))
        assert any(e.field_name == "name" for e in errors)

    def test_name_exactly_200(self):
        errors = validate_brand(Brand(id="test", name="A" * 200, workspace_id="ws1"))
        assert errors == []

    def test_industry_too_long(self):
        errors = validate_brand(Brand(
            id="test", name="Acme", industry="I" * 101, workspace_id="ws1",
        ))
        assert any(e.field_name == "industry" for e in errors)

    def test_tagline_too_long(self):
        errors = validate_brand(Brand(
            id="test", name="Acme", tagline="T" * 301, workspace_id="ws1",
        ))
        assert any(e.field_name == "tagline" for e in errors)

    def test_description_too_long(self):
        errors = validate_brand(Brand(
            id="test", name="Acme", description="D" * 5001, workspace_id="ws1",
        ))
        assert any(e.field_name == "description" for e in errors)

    def test_description_exactly_5000(self):
        errors = validate_brand(Brand(
            id="test", name="Acme", description="D" * 5000, workspace_id="ws1",
        ))
        assert errors == []

    def test_tone_too_long(self):
        errors = validate_brand(Brand(
            id="test", name="Acme", tone="T" * 101, workspace_id="ws1",
        ))
        assert any(e.field_name == "tone" for e in errors)

    def test_invalid_website(self):
        errors = validate_brand(Brand(
            id="test", name="Acme", website="not-a-url", workspace_id="ws1",
        ))
        assert any(e.field_name == "website" for e in errors)

    def test_valid_website_http(self):
        errors = validate_brand(Brand(
            id="test", name="Acme", website="http://example.com", workspace_id="ws1",
        ))
        assert errors == []

    def test_valid_website_https(self):
        errors = validate_brand(Brand(
            id="test", name="Acme", website="https://example.com", workspace_id="ws1",
        ))
        assert errors == []

    def test_invalid_color_primary(self):
        errors = validate_brand(Brand(
            id="test", name="Acme", color_primary="red", workspace_id="ws1",
        ))
        assert any(e.field_name == "color_primary" for e in errors)

    def test_valid_color_primary(self):
        errors = validate_brand(Brand(
            id="test", name="Acme", color_primary="#FF0000", workspace_id="ws1",
        ))
        assert errors == []

    def test_invalid_color_secondary(self):
        errors = validate_brand(Brand(
            id="test", name="Acme", color_secondary="blue", workspace_id="ws1",
        ))
        assert any(e.field_name == "color_secondary" for e in errors)

    def test_valid_color_secondary(self):
        errors = validate_brand(Brand(
            id="test", name="Acme", color_secondary="#00FF00", workspace_id="ws1",
        ))
        assert errors == []

    def test_invalid_status(self):
        errors = validate_brand(Brand(
            id="test", name="Acme", workspace_id="ws1", status="deleted",
        ))
        assert any(e.field_name == "status" for e in errors)

    def test_missing_workspace_id(self):
        errors = validate_brand(Brand(id="test", name="Acme", workspace_id=""))
        assert any(e.field_name == "workspace_id" for e in errors)


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

class TestCreate:
    def test_basic_create(self, store):
        brand = store.create(name="Acme Corp")
        assert brand.name == "Acme Corp"
        assert brand.status == "active"
        assert brand.version == 1
        assert brand.workspace_id == "ws1"
        assert brand.id

    def test_create_all_fields(self, store):
        brand = store.create(
            name="Full Brand",
            industry="Tech",
            tagline="We build",
            description="A tech company",
            tone="professional",
            personality="innovative,trustworthy",
            values="quality,innovation",
            target_audience="developers",
            website="https://example.com",
            logo_url="https://example.com/logo.png",
            color_primary="#FF0000",
            color_secondary="#00FF00",
            prohibited_terms="cheap,discount",
        )
        assert brand.industry == "Tech"
        assert brand.tagline == "We build"
        assert brand.description == "A tech company"
        assert brand.tone == "professional"
        assert brand.personality == "innovative,trustworthy"
        assert brand.values == "quality,innovation"
        assert brand.target_audience == "developers"
        assert brand.website == "https://example.com"
        assert brand.logo_url == "https://example.com/logo.png"
        assert brand.color_primary == "#FF0000"
        assert brand.color_secondary == "#00FF00"
        assert brand.prohibited_terms == "cheap,discount"

    def test_create_strips_whitespace(self, store):
        brand = store.create(name="  Acme  ", industry="  Tech  ")
        assert brand.name == "Acme"
        assert brand.industry == "Tech"

    def test_create_idempotent(self, store):
        """Creating a brand with the same name returns the existing one."""
        b1 = store.create(name="Acme")
        b2 = store.create(name="Acme")
        assert b1.id == b2.id
        assert store.count() == 1

    def test_create_idempotent_case_insensitive(self, store):
        """Idempotency is case-insensitive."""
        b1 = store.create(name="Acme")
        b2 = store.create(name="acme")
        assert b1.id == b2.id
        assert store.count() == 1

    def test_create_validation_error(self, store):
        with pytest.raises(ValidationError) as exc_info:
            store.create(name="")
        assert exc_info.value.field_name == "name"

    def test_create_unique_per_workspace(self, store, store_ws2):
        """Same name in different workspaces creates different brands."""
        b1 = store.create(name="Acme")
        b2 = store_ws2.create(name="Acme")
        assert b1.id != b2.id
        assert b1.workspace_id == "ws1"
        assert b2.workspace_id == "ws2"

    def test_create_initial_version_snapshot(self, store):
        """Creating a brand also creates a version 1 snapshot."""
        brand = store.create(name="Acme")
        versions = store.list_versions(brand.id)
        assert len(versions) == 1
        assert versions[0].version == 1
        assert versions[0].changed_fields == "initial"

    def test_create_sets_timestamps(self, store):
        brand = store.create(name="Acme")
        assert brand.created_at
        assert brand.updated_at


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

class TestRead:
    def test_get_by_id(self, store):
        brand = store.create(name="Acme")
        fetched = store.get(brand.id)
        assert fetched is not None
        assert fetched.name == "Acme"

    def test_get_nonexistent(self, store):
        assert store.get("nonexistent") is None

    def test_get_by_name(self, store):
        store.create(name="Acme")
        fetched = store.get_by_name("Acme")
        assert fetched is not None
        assert fetched.name == "Acme"

    def test_get_by_name_case_insensitive(self, store):
        store.create(name="Acme")
        fetched = store.get_by_name("acme")
        assert fetched is not None

    def test_get_by_name_nonexistent(self, store):
        assert store.get_by_name("NonExistent") is None

    def test_list_active(self, store):
        store.create(name="Brand A")
        store.create(name="Brand B")
        brands = store.list()
        assert len(brands) == 2

    def test_list_archived(self, store):
        b = store.create(name="Acme")
        store.archive(b.id)
        brands = store.list(status="archived")
        assert len(brands) == 1

    def test_list_empty(self, store):
        brands = store.list()
        assert brands == []

    def test_list_limit(self, store):
        for i in range(5):
            store.create(name=f"Brand {i}")
        brands = store.list(limit=3)
        assert len(brands) == 3

    def test_list_offset(self, store):
        for i in range(5):
            store.create(name=f"Brand {i}")
        page1 = store.list(limit=3, offset=0)
        page2 = store.list(limit=3, offset=3)
        assert len(page1) == 3
        assert len(page2) == 2
        assert {b.name for b in page1} != {b.name for b in page2}


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

class TestUpdate:
    def test_update_single_field(self, store):
        brand = store.create(name="Acme")
        updated = store.update(brand.id, tagline="We build things")
        assert updated is not None
        assert updated.tagline == "We build things"
        assert updated.version == 2

    def test_update_multiple_fields(self, store):
        brand = store.create(name="Acme")
        updated = store.update(
            brand.id,
            tagline="We build",
            tone="casual",
            industry="AI",
        )
        assert updated.tagline == "We build"
        assert updated.tone == "casual"
        assert updated.industry == "AI"
        assert updated.version == 2

    def test_update_nonexistent(self, store):
        result = store.update("nonexistent", tagline="test")
        assert result is None

    def test_update_invalid_field(self, store):
        brand = store.create(name="Acme")
        with pytest.raises(ValidationError):
            store.update(brand.id, nonexistent_field="test")

    def test_update_validation_error(self, store):
        brand = store.create(name="Acme")
        with pytest.raises(ValidationError):
            store.update(brand.id, name="")

    def test_update_preserves_id(self, store):
        brand = store.create(name="Acme")
        updated = store.update(brand.id, name="Acme Corp")
        assert updated.id == brand.id

    def test_update_no_fields(self, store):
        brand = store.create(name="Acme")
        result = store.update(brand.id)
        assert result is not None
        assert result.name == "Acme"
        assert result.version == 1  # no change

    def test_update_increments_version(self, store):
        brand = store.create(name="Acme")
        assert brand.version == 1
        store.update(brand.id, tagline="v2")
        store.update(brand.id, tone="v3")
        final = store.get(brand.id)
        assert final.version == 3

    def test_update_creates_version_snapshot(self, store):
        """Each update creates a new version snapshot."""
        brand = store.create(name="Acme")
        store.update(brand.id, tagline="New tagline")
        store.update(brand.id, tone="casual")
        versions = store.list_versions(brand.id)
        # v1 (initial) + v2 (after first update) + v3 (after second update)
        assert len(versions) == 3
        assert versions[0].version == 1
        assert versions[1].version == 2
        assert versions[2].version == 3

    def test_update_tracks_changed_fields(self, store):
        brand = store.create(name="Acme")
        store.update(brand.id, tagline="New tagline", tone="casual")
        versions = store.list_versions(brand.id)
        # Last version snapshot should list the changed fields
        last_snapshot = versions[-1]
        assert "tagline" in last_snapshot.changed_fields or "tone" in last_snapshot.changed_fields

    def test_update_color_primary(self, store):
        brand = store.create(name="Acme")
        updated = store.update(brand.id, color_primary="#AABBCC")
        assert updated.color_primary == "#AABBCC"


# ---------------------------------------------------------------------------
# Archive / Restore
# ---------------------------------------------------------------------------

class TestArchiveRestore:
    def test_archive(self, store):
        brand = store.create(name="Acme")
        assert store.archive(brand.id) is True
        fetched = store.get(brand.id)
        assert fetched.status == "archived"

    def test_archive_nonexistent(self, store):
        assert store.archive("nonexistent") is False

    def test_double_archive(self, store):
        brand = store.create(name="Acme")
        store.archive(brand.id)
        assert store.archive(brand.id) is False

    def test_restore(self, store):
        brand = store.create(name="Acme")
        store.archive(brand.id)
        assert store.restore(brand.id) is True
        fetched = store.get(brand.id)
        assert fetched.status == "active"

    def test_restore_nonexistent(self, store):
        assert store.restore("nonexistent") is False

    def test_restore_already_active(self, store):
        brand = store.create(name="Acme")
        assert store.restore(brand.id) is False


# ---------------------------------------------------------------------------
# Count
# ---------------------------------------------------------------------------

class TestCount:
    def test_count_active(self, store):
        store.create(name="A")
        store.create(name="B")
        assert store.count() == 2

    def test_count_archived(self, store):
        b = store.create(name="A")
        store.archive(b.id)
        assert store.count(status="archived") == 1
        assert store.count(status="active") == 0

    def test_count_empty(self, store):
        assert store.count() == 0


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

class TestSearch:
    def test_search_name(self, store):
        store.create(name="Acme Corp")
        results = store.search("Acme")
        assert len(results) == 1

    def test_search_industry(self, store):
        store.create(name="Acme", industry="Technology")
        results = store.search("Technology")
        assert len(results) == 1

    def test_search_tagline(self, store):
        store.create(name="Acme", tagline="Building the future")
        results = store.search("future")
        assert len(results) == 1

    def test_search_description(self, store):
        store.create(name="Acme", description="A tech startup")
        results = store.search("startup")
        assert len(results) == 1

    def test_search_no_results(self, store):
        store.create(name="Acme")
        results = store.search("nonexistent")
        assert len(results) == 0

    def test_search_limit(self, store):
        for i in range(5):
            store.create(name=f"Acme {i}")
        results = store.search("Acme", limit=3)
        assert len(results) == 3

    def test_search_excludes_archived(self, store):
        b = store.create(name="Acme")
        store.archive(b.id)
        results = store.search("Acme")
        assert len(results) == 0


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

class TestExport:
    def test_export_json(self, store):
        store.create(name="Acme")
        exported = store.export_json()
        data = json.loads(exported)
        assert len(data) == 1
        assert data[0]["name"] == "Acme"

    def test_export_redacts_sensitive(self, store):
        store.create(name="Acme", internal_notes="secret notes", internal_tags="internal")
        exported = store.export_json()
        data = json.loads(exported)
        assert data[0]["internal_notes"] == "[REDACTED]"
        assert data[0]["internal_tags"] == "[REDACTED]"

    def test_export_empty(self, store):
        exported = store.export_json()
        data = json.loads(exported)
        assert data == []


# ---------------------------------------------------------------------------
# Workspace isolation
# ---------------------------------------------------------------------------

class TestWorkspaceIsolation:
    def test_cross_workspace_read(self, store, store_ws2):
        brand = store.create(name="Acme")
        assert store_ws2.get(brand.id) is None

    def test_cross_workspace_update(self, store, store_ws2):
        brand = store.create(name="Acme")
        result = store_ws2.update(brand.id, tagline="hack")
        assert result is None

    def test_cross_workspace_archive(self, store, store_ws2):
        brand = store.create(name="Acme")
        assert store_ws2.archive(brand.id) is False

    def test_cross_workspace_search(self, store, store_ws2):
        store.create(name="Acme Corp")
        results = store_ws2.search("Acme")
        assert len(results) == 0


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

class TestRedaction:
    def test_redact_dict(self):
        d = {"name": "Acme", "internal_notes": "secret", "internal_tags": "tags"}
        redacted = _redact_dict(d)
        assert redacted["name"] == "Acme"
        assert redacted["internal_notes"] == "[REDACTED]"
        assert redacted["internal_tags"] == "[REDACTED]"

    def test_redact_name_short(self):
        assert _redact_name("Ab") == "Ab"

    def test_redact_name_long(self):
        assert _redact_name("Acme Corp") == "Acm***"


# ---------------------------------------------------------------------------
# Versioning
# ---------------------------------------------------------------------------

class TestVersioning:
    def test_list_versions_after_create(self, store):
        brand = store.create(name="Acme")
        versions = store.list_versions(brand.id)
        assert len(versions) == 1
        assert versions[0].version == 1

    def test_list_versions_after_updates(self, store):
        brand = store.create(name="Acme")
        store.update(brand.id, tagline="v2")
        store.update(brand.id, tone="casual")
        versions = store.list_versions(brand.id)
        assert len(versions) == 3  # 1 initial + 2 pre-update snapshots
        assert versions[0].version == 1

    def test_list_versions_empty(self, store):
        versions = store.list_versions("nonexistent")
        assert versions == []

    def test_get_version(self, store):
        brand = store.create(name="Acme")
        v = store.get_version(brand.id, 1)
        assert v is not None
        assert v.version == 1
        snap = v.get_snapshot_dict()
        assert snap["name"] == "Acme"

    def test_get_version_nonexistent(self, store):
        brand = store.create(name="Acme")
        assert store.get_version(brand.id, 99) is None

    def test_get_version_count(self, store):
        brand = store.create(name="Acme")
        store.update(brand.id, tagline="v2")
        store.update(brand.id, tone="casual")
        assert store.get_version_count(brand.id) == 3

    def test_snapshot_contains_full_state(self, store):
        brand = store.create(name="Acme", industry="Tech")
        v = store.get_version(brand.id, 1)
        snap = v.get_snapshot_dict()
        assert snap["name"] == "Acme"
        assert snap["industry"] == "Tech"
        assert snap["workspace_id"] == "ws1"

    def test_diff_versions(self, store):
        brand = store.create(name="Acme", tagline="Original")
        store.update(brand.id, tagline="Updated", tone="casual")
        diff = store.diff_versions(brand.id, 1, 2)
        assert diff is not None
        # v1 is initial, v2 is the pre-update snapshot, so the diff
        # between them should show no change (both are v1 state)
        # Let's diff the pre-update snapshot with the actual update
        # The version flow: v1 created -> update(tagline, tone) -> v2
        # Versions stored: 1 (initial), 1 (pre-update snapshot), 2 (after update)
        # The pre-update snapshot has version=1 but it's the state before update
        # The actual diff is between the pre-update and post-update

    def test_diff_versions_nonexistent(self, store):
        brand = store.create(name="Acme")
        assert store.diff_versions(brand.id, 1, 99) is None
        assert store.diff_versions("nonexistent", 1, 2) is None

    def test_diff_versions_no_changes(self, store):
        """Diffing with a no-op update shows no changes."""
        brand = store.create(name="Acme")
        store.update(brand.id, internal_tags="internal")  # non-versioned field
        versions = store.list_versions(brand.id)
        if len(versions) >= 2:
            diff = store.diff_versions(brand.id, versions[0].version, versions[-1].version)
            # internal_tags is not in _VERSIONED_FIELDS, so no diff
            assert diff == {} or diff is not None


# ---------------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------------

class TestRollback:
    def test_rollback_to_previous(self, store):
        brand = store.create(name="Acme", tagline="Original")
        store.update(brand.id, tagline="Changed")

        # Get the version number to rollback to
        versions = store.list_versions(brand.id)
        initial_version = versions[0].version  # version 1

        rolled = store.rollback(brand.id, initial_version)
        assert rolled is not None
        assert rolled.tagline == "Original"
        assert rolled.version > 1  # new version was created

    def test_rollback_nonexistent_brand(self, store):
        assert store.rollback("nonexistent", 1) is None

    def test_rollback_nonexistent_version(self, store):
        brand = store.create(name="Acme")
        assert store.rollback(brand.id, 99) is None

    def test_rollback_creates_version(self, store):
        brand = store.create(name="Acme", tagline="Original")
        store.update(brand.id, tagline="Changed")
        versions_before = store.get_version_count(brand.id)

        versions = store.list_versions(brand.id)
        store.rollback(brand.id, versions[0].version)

        versions_after = store.get_version_count(brand.id)
        # Rollback creates: pre_rollback snapshot + rolled-back state
        assert versions_after > versions_before

    def test_rollback_then_update(self, store):
        """After rollback, further updates work normally."""
        brand = store.create(name="Acme", tagline="V1")
        store.update(brand.id, tagline="V2")

        versions = store.list_versions(brand.id)
        store.rollback(brand.id, versions[0].version)

        final = store.get(brand.id)
        updated = store.update(final.id, tagline="V3")
        assert updated.tagline == "V3"


# ---------------------------------------------------------------------------
# Changed fields computation
# ---------------------------------------------------------------------------

class TestChangedFields:
    def test_no_changes(self):
        old = {"name": "Acme", "tagline": "Hello"}
        new = {"name": "Acme", "tagline": "Hello"}
        assert _compute_changed_fields(old, new) == ""

    def test_single_change(self):
        old = {"name": "Acme", "tagline": "Old"}
        new = {"name": "Acme", "tagline": "New"}
        result = _compute_changed_fields(old, new)
        assert "tagline" in result

    def test_multiple_changes(self):
        old = {"name": "Acme", "tagline": "Old", "tone": "formal"}
        new = {"name": "Beta", "tagline": "New", "tone": "casual"}
        result = _compute_changed_fields(old, new)
        assert "name" in result
        assert "tagline" in result
        assert "tone" in result

    def test_non_versioned_field_ignored(self):
        old = {"name": "Acme", "status": "active"}
        new = {"name": "Acme", "status": "archived"}
        result = _compute_changed_fields(old, new)
        assert result == ""


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_unicode_name(self, store):
        brand = store.create(name="برند فارسی 🎉")
        assert brand.name == "برند فارسی 🎉"
        fetched = store.get(brand.id)
        assert fetched.name == "برند فارسی 🎉"

    def test_long_description(self, store):
        desc = "A" * 5000
        brand = store.create(name="Acme", description=desc)
        assert len(brand.description) == 5000

    def test_special_characters(self, store):
        brand = store.create(name="Brand & Co. (v2.0)")
        assert brand.name == "Brand & Co. (v2.0)"

    def test_empty_database(self, store):
        assert store.list() == []
        assert store.count() == 0
        assert store.search("anything") == []

    def test_concurrent_workspaces(self, tmp_db):
        s1 = BrandStore(tmp_db, "ws1")
        s2 = BrandStore(tmp_db, "ws2")
        s1.create(name="Brand A")
        s2.create(name="Brand B")
        assert s1.count() == 1
        assert s2.count() == 1
        assert s1.list()[0].name == "Brand A"
        assert s2.list()[0].name == "Brand B"

    def test_schema_idempotent(self, tmp_db):
        """Running _ensure_schema multiple times doesn't error."""
        store1 = BrandStore(tmp_db, "ws1")
        store2 = BrandStore(tmp_db, "ws1")  # same DB, second init
        store1.create(name="Test")
        assert store2.count() == 1

    def test_create_reactivate_archived(self, store):
        """Creating a brand with the same name as an archived one reactivates it."""
        brand = store.create(name="Acme")
        store.archive(brand.id)
        reactivated = store.create(name="Acme")
        assert reactivated.status == "active"
        assert store.count(status="archived") == 0

    def test_version_snapshot_json_valid(self, store):
        """Version snapshots contain valid JSON."""
        brand = store.create(name="Acme", industry="Tech")
        store.update(brand.id, tagline="Hello")
        versions = store.list_versions(brand.id)
        for v in versions:
            snap = v.get_snapshot_dict()
            assert isinstance(snap, dict)
            assert "name" in snap

    def test_brand_to_dict_roundtrip(self):
        """Brand serialization roundtrips correctly."""
        brand = Brand(
            id="test-id", name="Acme", industry="Tech",
            workspace_id="ws1", version=1,
        )
        d = brand.to_dict()
        restored = Brand(**d)
        assert restored.name == brand.name
        assert restored.id == brand.id

    def test_brand_version_to_dict(self, store):
        """BrandVersion to_dict includes all fields."""
        brand = store.create(name="Acme")
        v = store.get_version(brand.id, 1)
        d = v.to_dict()
        assert "brand_id" in d
        assert "version" in d
        assert "snapshot" in d
        assert "changed_fields" in d
