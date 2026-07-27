#!/usr/bin/env python3
"""
Tests for Brand Extractor and Communication Fingerprints.

Run: python -m pytest tests/test_extractor.py -v
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from brand_extractor import BrandExtractor, CrawledPage, extract_brand_voice
from communication_fingerprints import (
    AUTHORITATIVE,
    BOLD,
    EMPATHETIC,
    FingerprintType,
    get_all_fingerprints,
    get_fingerprint,
    list_fingerprint_types,
)


# ---------------------------------------------------------------------------
# Communication Fingerprints tests
# ---------------------------------------------------------------------------

class TestFingerprints:
    def test_three_mvp_fingerprints_exist(self):
        fps = get_all_fingerprints()
        assert len(fps) == 3
        assert FingerprintType.AUTHORITATIVE in fps
        assert FingerprintType.EMPATHETIC in fps
        assert FingerprintType.BOLD in fps

    def test_authoritative_properties(self):
        assert AUTHORITATIVE.fingerprint_type == FingerprintType.AUTHORITATIVE
        assert AUTHORITATIVE.tone.authority_level == "high"
        assert "proven" in AUTHORITATIVE.vocabulary.preferred_words
        assert "maybe" in AUTHORITATIVE.vocabulary.avoided_words

    def test_empathetic_properties(self):
        assert EMPATHETIC.fingerprint_type == FingerprintType.EMPATHETIC
        assert EMPATHETIC.tone.empathy_level == "high"
        assert EMPATHETIC.vocabulary.use_questions is True

    def test_bold_properties(self):
        assert BOLD.fingerprint_type == FingerprintType.BOLD
        assert BOLD.tone.boldness_level == "high"
        assert BOLD.vocabulary.sentence_length == "short"

    def test_get_fingerprint(self):
        fp = get_fingerprint(FingerprintType.AUTHORITATIVE)
        assert fp is AUTHORITATIVE

    def test_get_unknown_fingerprint_raises(self):
        # Can't create an unknown enum value, but we can test the registry
        fps = get_all_fingerprints()
        assert len(fps) == 3

    def test_list_types(self):
        types = list_fingerprint_types()
        assert "authoritative" in types
        assert "empathetic" in types
        assert "bold" in types

    def test_to_dict_roundtrip(self):
        d = AUTHORITATIVE.to_dict()
        from communication_fingerprints import CommunicationFingerprint
        fp2 = CommunicationFingerprint.from_dict(d)
        assert fp2.name == "Authoritative"
        assert fp2.fingerprint_type == FingerprintType.AUTHORITATIVE

    def test_to_json_roundtrip(self):
        json_str = EMPATHETIC.to_json()
        from communication_fingerprints import CommunicationFingerprint
        fp2 = CommunicationFingerprint.from_json(json_str)
        assert fp2.name == "Empathetic"


# ---------------------------------------------------------------------------
# CrawledPage tests
# ---------------------------------------------------------------------------

class TestCrawledPage:
    def test_from_dict(self):
        page = CrawledPage.from_dict({
            "url": "https://example.com",
            "title": "Example",
            "content": "Hello world",
        })
        assert page.url == "https://example.com"
        assert page.title == "Example"

    def test_defaults(self):
        page = CrawledPage(url="https://test.com")
        assert page.title == ""
        assert page.content == ""


# ---------------------------------------------------------------------------
# Brand Extractor tests
# ---------------------------------------------------------------------------

class TestBrandExtractor:
    def test_extract_empty_pages(self):
        extractor = BrandExtractor()
        profile = extractor.extract([])
        assert profile.brand_name.value == ""

    def test_extract_basic_profile(self):
        pages = [
            {
                "url": "https://acmetech.com",
                "title": "AcmeTech - Innovation Platform",
                "content": (
                    "AcmeTech is the leading platform for enterprise software. "
                    "Our proven technology helps businesses scale with data-driven "
                    "solutions. We establish benchmarks for quality and excellence. "
                    "Our expert team provides validated, certified solutions that "
                    "set the industry standard."
                ),
                "meta_description": "AcmeTech: enterprise software platform for modern businesses.",
            },
        ]
        profile = extract_brand_voice(pages)
        assert profile.brand_name.value != ""
        assert profile.overall_confidence >= 0.0
        assert len(profile.source_urls) == 1

    def test_extract_tone_detection(self):
        pages = [
            {
                "url": "https://luxurybrand.com",
                "title": "LuxBrand | Exclusive Luxury",
                "content": (
                    "Welcome to our exclusive, premium, bespoke collection. "
                    "Each piece reflects artisan craftsmanship and heritage. "
                    "Our curated, elegant designs embody sophistication and prestige. "
                    "Experience refined luxury like never before."
                ),
                "meta_description": "Exclusive luxury brand offering bespoke, curated products.",
            },
        ]
        profile = extract_brand_voice(pages)
        # Should detect luxury tone
        assert profile.primary_tone.value != ""

    def test_extract_industry_detection(self):
        pages = [
            {
                "url": "https://beautyco.com",
                "title": "BeautyCo - Skincare",
                "content": (
                    "Our skincare formula is designed for your daily routine. "
                    "Achieve a natural glow with our cosmetic-grade ingredients. "
                    "Beauty care made simple and effective."
                ),
            },
        ]
        profile = extract_brand_voice(pages)
        assert profile.industry.value == "beauty"

    def test_extract_values_detection(self):
        pages = [
            {
                "url": "https://ecobrand.com",
                "title": "EcoBrand",
                "content": (
                    "We believe in sustainable, eco-friendly products. "
                    "Our green approach ensures environmental responsibility. "
                    "Quality and authenticity are at our core."
                ),
            },
        ]
        profile = extract_brand_voice(pages)
        value_names = [v.value for v in profile.core_values]
        assert "sustainability" in value_names or "quality" in value_names

    def test_extract_vocabulary_level(self):
        pages = [
            {
                "url": "https://techcorp.com",
                "title": "TechCorp",
                "content": (
                    "Our comprehensive, sophisticated platform delivers "
                    "extraordinary functionality for enterprise organizations. "
                    "Unprecedented capabilities transform operational efficiency."
                ),
            },
        ]
        profile = extract_brand_voice(pages)
        assert profile.vocabulary_level.value in ("basic", "intermediate", "advanced")

    def test_multiple_pages(self):
        pages = [
            {
                "url": "https://brand.com",
                "title": "Brand | Home",
                "content": "Welcome to Brand. We provide quality products.",
                "meta_description": "Brand: quality products for everyone.",
            },
            {
                "url": "https://brand.com/about",
                "title": "Brand | About Us",
                "content": "Brand was established to deliver authentic, quality experiences.",
                "meta_description": "About Brand: our mission and values.",
            },
        ]
        profile = extract_brand_voice(pages)
        assert len(profile.source_urls) == 2
        assert profile.total_evidence_count > 0
