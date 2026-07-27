"""
Brand Knowledge Layer — Schema validation tests

Tests that the JSON Schema correctly validates brand knowledge documents.
Uses Python's jsonschema library for validation.

Run: python -m pytest src/brand-knowledge/__tests__/schema.test.py -v
"""

import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
SCHEMA_PATH = BASE_DIR / "schema.json"
MINIMAL_EXAMPLE = BASE_DIR / "examples" / "minimal.json"
COMPLETE_EXAMPLE = BASE_DIR / "examples" / "complete.json"


def load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Basic structural tests (no jsonschema dependency required)
# ---------------------------------------------------------------------------


def test_schema_file_exists():
    """Schema file must exist."""
    assert SCHEMA_PATH.exists(), f"Schema not found at {SCHEMA_PATH}"


def test_schema_is_valid_json():
    """Schema itself must be valid JSON."""
    schema = load_json(SCHEMA_PATH)
    assert isinstance(schema, dict)
    assert "$schema" in schema
    assert "$defs" in schema


def test_schema_has_all_layer_defs():
    """Schema $defs must define all 6 layers."""
    schema = load_json(SCHEMA_PATH)
    defs = schema["$defs"]
    required_types = [
        "BrandIdentity",
        "BrandVoice",
        "BrandValues",
        "BrandPositioning",
        "BrandVisual",
        "AudienceSegment",
        "CompetitiveLandscape",
        "ContentPillars",
        "MessagingHierarchy",
        "ProductMarketFit",
    ]
    for t in required_types:
        assert t in defs, f"Missing $defs entry: {t}"


def test_schema_root_requires_all_layers():
    """Root schema must require all 6 layer fields."""
    schema = load_json(SCHEMA_PATH)
    required = schema.get("required", [])
    layer_fields = [
        "brandIdentity",
        "audienceSegments",
        "competitiveLandscape",
        "contentPillars",
        "messagingHierarchy",
        "productMarketFit",
    ]
    for field in layer_fields:
        assert field in required, f"Root schema missing required field: {field}"


def test_schema_root_requires_metadata_fields():
    """Root schema must require schemaVersion, brandId, workspaceId, version."""
    schema = load_json(SCHEMA_PATH)
    required = schema.get("required", [])
    for field in ["schemaVersion", "brandId", "workspaceId", "version", "status", "source"]:
        assert field in required, f"Root schema missing required field: {field}"


def test_data_origin_enum():
    """DataOrigin must be exactly ['user', 'inferred']."""
    schema = load_json(SCHEMA_PATH)
    origin = schema["$defs"]["DataOrigin"]
    assert set(origin["enum"]) == {"user", "inferred"}


def test_minimal_example_exists():
    """Minimal example must exist."""
    assert MINIMAL_EXAMPLE.exists(), f"Minimal example not found at {MINIMAL_EXAMPLE}"


def test_complete_example_exists():
    """Complete example must exist."""
    assert COMPLETE_EXAMPLE.exists(), f"Complete example not found at {COMPLETE_EXAMPLE}"


def test_minimal_example_is_valid_json():
    """Minimal example must parse as JSON."""
    doc = load_json(MINIMAL_EXAMPLE)
    assert doc["schemaVersion"] == "1.0.0"


def test_complete_example_is_valid_json():
    """Complete example must parse as JSON."""
    doc = load_json(COMPLETE_EXAMPLE)
    assert doc["schemaVersion"] == "1.0.0"


def test_minimal_has_all_required_root_fields():
    """Minimal example must have all required root-level fields."""
    doc = load_json(MINIMAL_EXAMPLE)
    required = [
        "schemaVersion", "brandId", "workspaceId", "version",
        "createdAt", "updatedAt", "createdBy", "source", "status",
        "brandIdentity", "audienceSegments", "competitiveLandscape",
        "contentPillars", "messagingHierarchy", "productMarketFit",
    ]
    for field in required:
        assert field in doc, f"Minimal example missing required field: {field}"


def test_complete_has_audience_segments():
    """Complete example should have at least one audience segment."""
    doc = load_json(COMPLETE_EXAMPLE)
    assert len(doc["audienceSegments"]) >= 1


def test_complete_has_competitors():
    """Complete example should list competitors."""
    doc = load_json(COMPLETE_EXAMPLE)
    assert len(doc["competitiveLandscape"]["competitors"]) >= 1


def test_complete_has_content_pillars():
    """Complete example should have content pillars."""
    doc = load_json(COMPLETE_EXAMPLE)
    assert len(doc["contentPillars"]["pillars"]) >= 1


# ---------------------------------------------------------------------------
# Full JSON Schema validation (requires jsonschema)
# ---------------------------------------------------------------------------


def _try_import_jsonschema():
    try:
        import jsonschema
        return jsonschema
    except ImportError:
        return None


def test_schema_validates_minimal_example():
    """Minimal example must validate against the JSON Schema."""
    jsonschema = _try_import_jsonschema()
    if jsonschema is None:
        print("SKIP: jsonschema not installed")
        return

    schema = load_json(SCHEMA_PATH)
    doc = load_json(MINIMAL_EXAMPLE)
    jsonschema.validate(instance=doc, schema=schema)


def test_schema_validates_complete_example():
    """Complete example must validate against the JSON Schema."""
    jsonschema = _try_import_jsonschema()
    if jsonschema is None:
        print("SKIP: jsonschema not installed")
        return

    schema = load_json(SCHEMA_PATH)
    doc = load_json(COMPLETE_EXAMPLE)
    jsonschema.validate(instance=doc, schema=schema)


def test_schema_rejects_missing_required_field():
    """Schema must reject documents missing required fields."""
    jsonschema = _try_import_jsonschema()
    if jsonschema is None:
        print("SKIP: jsonschema not installed")
        return

    schema = load_json(SCHEMA_PATH)
    doc = load_json(MINIMAL_EXAMPLE)
    del doc["brandId"]

    try:
        jsonschema.validate(instance=doc, schema=schema)
        assert False, "Should have raised ValidationError"
    except jsonschema.ValidationError:
        pass  # expected


def test_schema_rejects_invalid_status():
    """Schema must reject invalid status values."""
    jsonschema = _try_import_jsonschema()
    if jsonschema is None:
        print("SKIP: jsonschema not installed")
        return

    schema = load_json(SCHEMA_PATH)
    doc = load_json(MINIMAL_EXAMPLE)
    doc["status"] = "invalid-status"

    try:
        jsonschema.validate(instance=doc, schema=schema)
        assert False, "Should have raised ValidationError"
    except jsonschema.ValidationError:
        pass  # expected


def test_schema_rejects_invalid_source():
    """Schema must reject invalid aggregate source values."""
    jsonschema = _try_import_jsonschema()
    if jsonschema is None:
        print("SKIP: jsonschema not installed")
        return

    schema = load_json(SCHEMA_PATH)
    doc = load_json(MINIMAL_EXAMPLE)
    doc["source"] = "machine"

    try:
        jsonschema.validate(instance=doc, schema=schema)
        assert False, "Should have raised ValidationError"
    except jsonschema.ValidationError:
        pass  # expected


def test_schema_rejects_additional_root_properties():
    """Schema must reject documents with unknown root-level properties."""
    jsonschema = _try_import_jsonschema()
    if jsonschema is None:
        print("SKIP: jsonschema not installed")
        return

    schema = load_json(SCHEMA_PATH)
    doc = load_json(MINIMAL_EXAMPLE)
    doc["unknownField"] = "should fail"

    try:
        jsonschema.validate(instance=doc, schema=schema)
        assert False, "Should have raised ValidationError"
    except jsonschema.ValidationError:
        pass  # expected


def test_schema_rejects_invalid_color_hex():
    """Schema must reject invalid hex color values."""
    jsonschema = _try_import_jsonschema()
    if jsonschema is None:
        print("SKIP: jsonschema not installed")
        return

    schema = load_json(SCHEMA_PATH)
    doc = load_json(MINIMAL_EXAMPLE)
    doc["brandIdentity"]["visual"]["primaryColor"] = "not-a-color"

    try:
        jsonschema.validate(instance=doc, schema=schema)
        assert False, "Should have raised ValidationError"
    except jsonschema.ValidationError:
        pass  # expected


def test_schema_requires_version_at_least_1():
    """Schema must reject version < 1."""
    jsonschema = _try_import_jsonschema()
    if jsonschema is None:
        print("SKIP: jsonschema not installed")
        return

    schema = load_json(SCHEMA_PATH)
    doc = load_json(MINIMAL_EXAMPLE)
    doc["version"] = 0

    try:
        jsonschema.validate(instance=doc, schema=schema)
        assert False, "Should have raised ValidationError"
    except jsonschema.ValidationError:
        pass  # expected


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    tests = [
        test_schema_file_exists,
        test_schema_is_valid_json,
        test_schema_has_all_layer_defs,
        test_schema_root_requires_all_layers,
        test_schema_root_requires_metadata_fields,
        test_data_origin_enum,
        test_minimal_example_exists,
        test_complete_example_exists,
        test_minimal_example_is_valid_json,
        test_complete_example_is_valid_json,
        test_minimal_has_all_required_root_fields,
        test_complete_has_audience_segments,
        test_complete_has_competitors,
        test_complete_has_content_pillars,
        test_schema_validates_minimal_example,
        test_schema_validates_complete_example,
        test_schema_rejects_missing_required_field,
        test_schema_rejects_invalid_status,
        test_schema_rejects_invalid_source,
        test_schema_rejects_additional_root_properties,
        test_schema_rejects_invalid_color_hex,
        test_schema_requires_version_at_least_1,
    ]

    passed = 0
    failed = 0
    for test_fn in tests:
        try:
            test_fn()
            print(f"  PASS  {test_fn.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {test_fn.__name__}: {e}")
            failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")

    if failed > 0:
        sys.exit(1)