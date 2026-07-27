#!/usr/bin/env python3
"""
Tests for Brand Profile schema.

Run: python -m pytest tests/test_brand_profile.py -v
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from brand_profile import (
    AttributedValue,
    BrandProfile,
    Evidence,
    ToneCategory,
)


class TestEvidence:
    def test_create_evidence(self):
        e = Evidence(
            value="test",
            source_url="https://example.com",
            excerpt="some text",
            confidence=0.8,
        )
        assert e.value == "test"
        assert e.confidence == 0.8

    def test_to_dict_roundtrip(self):
        e = Evidence(value="x", source_url="https://x.com", excerpt="text", confidence=0.5)
        d = e.to_dict()
        e2 = Evidence.from_dict(d)
        assert e2.value == e.value
        assert e2.source_url == e.source_url


class TestAttributedValue:
    def test_confidence_with_no_evidence(self):
        av = AttributedValue(value="test")
        assert av.compute_confidence() == 0.0

    def test_confidence_with_evidence(self):
        av = AttributedValue(
            value="test",
            evidence=[
                Evidence(value="test", source_url="https://a.com", excerpt="x", confidence=0.8),
                Evidence(value="test", source_url="https://b.com", excerpt="y", confidence=0.9),
            ],
        )
        conf = av.compute_confidence()
        assert conf > 0.8  # Should be above base average due to 2 sources
        assert conf <= 1.0

    def test_to_dict_roundtrip(self):
        av = AttributedValue(
            value="hello",
            evidence=[
                Evidence(value="hello", source_url="https://x.com", excerpt="hi", confidence=0.7),
            ],
        )
        d = av.to_dict()
        av2 = AttributedValue.from_dict(d)
        assert av2.value == "hello"
        assert len(av2.evidence) == 1


class TestBrandProfile:
    def test_empty_profile(self):
        bp = BrandProfile()
        assert bp.brand_name.value == ""
        assert bp.compute_overall_confidence() == 0.0

    def test_profile_with_data(self):
        bp = BrandProfile()
        bp.brand_name = AttributedValue(
            value="Acme",
            evidence=[
                Evidence(value="Acme", source_url="https://acme.com", excerpt="Acme Corp", confidence=0.9),
            ],
        )
        bp.industry = AttributedValue(
            value="technology",
            evidence=[
                Evidence(value="technology", source_url="https://acme.com", excerpt="tech company", confidence=0.8),
            ],
        )
        conf = bp.compute_overall_confidence()
        assert conf > 0.0
        assert bp.count_evidence() == 2

    def test_to_dict_roundtrip(self):
        bp = BrandProfile()
        bp.brand_name = AttributedValue(
            value="TestBrand",
            evidence=[
                Evidence(value="TestBrand", source_url="https://test.com", excerpt="title", confidence=0.9),
            ],
        )
        d = bp.to_dict()
        bp2 = BrandProfile.from_dict(d)
        assert bp2.brand_name.value == "TestBrand"

    def test_json_roundtrip(self):
        bp = BrandProfile()
        bp.brand_name = AttributedValue(value="JsonBrand")
        json_str = bp.to_json()
        bp2 = BrandProfile.from_json(json_str)
        assert bp2.brand_name.value == "JsonBrand"

    def test_summary(self):
        bp = BrandProfile()
        bp.brand_name = AttributedValue(value="SummaryBrand")
        bp.industry = AttributedValue(value="tech")
        s = bp.summary()
        assert s["brand_name"] == "SummaryBrand"
        assert s["industry"] == "tech"

    def test_save_load(self, tmp_path):
        bp = BrandProfile()
        bp.brand_name = AttributedValue(value="SaveBrand")
        path = tmp_path / "test_profile.json"
        bp.save(path)
        bp2 = BrandProfile.load(path)
        assert bp2.brand_name.value == "SaveBrand"
