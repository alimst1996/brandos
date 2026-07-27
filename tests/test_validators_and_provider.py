#!/usr/bin/env python3
"""
Tests for Validators, Prompt Contracts, AI Provider, and Run Logger.

Run: python -m pytest tests/test_validators_and_provider.py -v
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from brand_profile import AttributedValue, BrandProfile, Evidence
from communication_fingerprints import AUTHORITATIVE, BOLD, EMPATHETIC, FingerprintType
from prompt_contracts import ContentType, PromptContract
from prompt_contract_builder import build_contract
from ai_run_logger import AIRunRecord, RunLogger
from ai_provider import MockProvider
from validators import BrandValidator, ClaimValidator, PersonaValidator, ValidationResult


# ---------------------------------------------------------------------------
# Prompt Contracts
# ---------------------------------------------------------------------------

class TestPromptContracts:
    def test_contract_creation(self):
        contract = PromptContract(
            contract_id="test-123",
            content_type=ContentType.SOCIAL_POST,
            fingerprint_type="authoritative",
            brand_name="TestBrand",
            system_prompt="You are a writer.",
            user_prompt_template="Write about {topic} for {brand_name}.",
        )
        assert contract.contract_id == "test-123"

    def test_render_user_prompt(self):
        contract = PromptContract(
            contract_id="test",
            content_type=ContentType.SOCIAL_POST,
            fingerprint_type="bold",
            brand_name="Acme",
            system_prompt="sys",
            user_prompt_template="Write about {topic} for {brand_name}.",
        )
        rendered = contract.render_user_prompt(topic="AI", brand_name="Acme")
        assert "AI" in rendered
        assert "Acme" in rendered

    def test_render_missing_variable_raises(self):
        contract = PromptContract(
            contract_id="test",
            content_type=ContentType.SOCIAL_POST,
            fingerprint_type="bold",
            brand_name="Acme",
            system_prompt="sys",
            user_prompt_template="Write about {topic}.",
        )
        with pytest.raises(ValueError, match="Missing template variable"):
            contract.render_user_prompt()

    def test_to_dict_roundtrip(self):
        contract = PromptContract(
            contract_id="rt-1",
            content_type=ContentType.PRODUCT_DESCRIPTION,
            fingerprint_type="empathetic",
            brand_name="Brand",
            system_prompt="sys prompt",
            user_prompt_template="user prompt {x}",
        )
        d = contract.to_dict()
        c2 = PromptContract.from_dict(d)
        assert c2.contract_id == "rt-1"

    def test_to_json(self):
        contract = PromptContract(
            contract_id="j1",
            content_type=ContentType.EMAIL_SUBJECT,
            fingerprint_type="authoritative",
            brand_name="B",
            system_prompt="s",
            user_prompt_template="u",
        )
        j = contract.to_json()
        data = json.loads(j)
        assert data["contract_id"] == "j1"


class TestPromptContractBuilder:
    def _make_brand(self) -> BrandProfile:
        bp = BrandProfile()
        bp.brand_name = AttributedValue(value="TestBrand")
        bp.primary_tone = AttributedValue(value="bold")
        bp.core_values = [AttributedValue(value="innovation"), AttributedValue(value="quality")]
        return bp

    def test_build_social_post(self):
        brand = self._make_brand()
        contract = build_contract(ContentType.SOCIAL_POST, brand, BOLD)
        assert contract.content_type == ContentType.SOCIAL_POST
        assert "TestBrand" in contract.system_prompt
        assert contract.fingerprint_type == "bold"

    def test_build_product_description(self):
        brand = self._make_brand()
        contract = build_contract(ContentType.PRODUCT_DESCRIPTION, brand, AUTHORITATIVE)
        assert contract.content_type == ContentType.PRODUCT_DESCRIPTION

    def test_build_email_subject(self):
        brand = self._make_brand()
        contract = build_contract(ContentType.EMAIL_SUBJECT, brand, EMPATHETIC)
        assert contract.content_type == ContentType.EMAIL_SUBJECT
        assert contract.fingerprint_type == "empathetic"


# ---------------------------------------------------------------------------
# AI Run Logger
# ---------------------------------------------------------------------------

class TestRunLogger:
    def test_log_and_read(self, tmp_path):
        logger = RunLogger(log_dir=tmp_path)
        record = AIRunRecord(
            provider="openai",
            model="gpt-4o",
            prompt_contract_id="c1",
            prompt_version="1.0.0",
            user_prompt="test prompt",
            brand_name="TestBrand",
            status="success",
        )
        logger.log(record)

        runs = logger.read_runs()
        assert len(runs) == 1
        assert runs[0].provider == "openai"
        assert runs[0].status == "success"

    def test_log_run_method(self, tmp_path):
        logger = RunLogger(log_dir=tmp_path)
        record = logger.log_run(
            provider="openrouter",
            model="claude-sonnet",
            contract_id="c2",
            prompt_version="1.0.0",
            user_prompt="generate post",
            brand_name="Brand",
        )
        assert record.run_id != ""
        assert record.status == "pending"

    def test_update_run(self, tmp_path):
        logger = RunLogger(log_dir=tmp_path)
        record = logger.log_run(
            provider="test",
            model="test-model",
            contract_id="c3",
            prompt_version="1.0.0",
            user_prompt="prompt",
        )
        record.status = "success"
        record.raw_output = "generated text"
        logger.update_run(record)

        runs = logger.read_runs()
        assert len(runs) == 2  # initial + update
        assert runs[1].status == "success"

    def test_get_run(self, tmp_path):
        logger = RunLogger(log_dir=tmp_path)
        record = AIRunRecord(
            run_id="findme",
            provider="test",
            model="m",
            prompt_contract_id="c",
            prompt_version="1",
            user_prompt="p",
            status="done",
        )
        logger.log(record)
        found = logger.get_run("findme")
        assert found is not None
        assert found.run_id == "findme"

    def test_stats(self, tmp_path):
        logger = RunLogger(log_dir=tmp_path)
        for i in range(3):
            record = AIRunRecord(
                provider="openai",
                model="gpt-4o",
                prompt_contract_id=f"c{i}",
                prompt_version="1",
                user_prompt="p",
                status="success" if i < 2 else "failed",
                total_cost_usd=0.01,
            )
            logger.log(record)
        stats = logger.stats()
        assert stats["total_runs"] == 3
        assert stats["success"] == 2
        assert stats["failed"] == 1


# ---------------------------------------------------------------------------
# AI Provider (Mock)
# ---------------------------------------------------------------------------

class TestMockProvider:
    def test_generate(self, tmp_path):
        logger = RunLogger(log_dir=tmp_path)
        provider = MockProvider(response="Hello world!", logger=logger)

        contract = PromptContract(
            contract_id="test-c",
            content_type=ContentType.SOCIAL_POST,
            fingerprint_type="bold",
            brand_name="Test",
            system_prompt="You are a writer.",
            user_prompt_template="Write about {topic}.",
        )

        result = provider.generate(contract, {"topic": "AI"})
        assert result.content == "Hello world!"
        assert result.run_id != ""
        assert result.provider == "mock"

        # Check logging
        runs = logger.read_runs()
        assert len(runs) >= 1

    def test_generate_logs_on_failure(self, tmp_path):
        logger = RunLogger(log_dir=tmp_path)

        class FailingProvider(MockProvider):
            def _call_api(self, system_prompt, user_prompt, max_tokens, temperature):
                raise RuntimeError("API error")

        provider = FailingProvider(logger=logger)
        contract = PromptContract(
            contract_id="fail-c",
            content_type=ContentType.SOCIAL_POST,
            fingerprint_type="bold",
            brand_name="Test",
            system_prompt="sys",
            user_prompt_template="Write.",
        )

        with pytest.raises(RuntimeError, match="API error"):
            provider.generate(contract, {})

        runs = logger.read_runs()
        assert any(r.status == "failed" for r in runs)


# ---------------------------------------------------------------------------
# ClaimValidator
# ---------------------------------------------------------------------------

class TestClaimValidator:
    def test_passes_clean_text(self):
        v = ClaimValidator()
        result = v.validate("Our products are designed with care.")
        assert result.passed is True

    def test_catches_unsupported_stat(self):
        v = ClaimValidator()
        result = v.validate(
            "95% of customers recommend our product.",
            source_evidence=["We make great products."],
        )
        assert result.passed is False
        assert any("95" in e for e in result.errors)

    def test_passes_supported_stat(self):
        v = ClaimValidator()
        result = v.validate(
            "95% of customers recommend us.",
            source_evidence=["95% of customers recommend us in our latest survey."],
        )
        assert result.passed is True

    def test_warns_on_superlative_without_evidence(self):
        v = ClaimValidator()
        result = v.validate("We are the best in the industry.")
        assert len(result.warnings) > 0


# ---------------------------------------------------------------------------
# BrandValidator
# ---------------------------------------------------------------------------

class TestBrandValidator:
    def _make_brand(self) -> BrandProfile:
        bp = BrandProfile()
        bp.brand_name = AttributedValue(value="Acme")
        bp.core_values = [AttributedValue(value="innovation"), AttributedValue(value="quality")]
        bp.avoided_phrases = [AttributedValue(value="cheap")]
        return bp

    def test_passes_compliant_text(self):
        v = BrandValidator()
        brand = self._make_brand()
        result = v.validate("Acme drives innovation and quality.", brand)
        assert result.passed is True
        assert result.details["brand_name_present"] is True

    def test_catches_avoided_phrase(self):
        v = BrandValidator()
        brand = self._make_brand()
        result = v.validate("Our cheap products are great.", brand)
        assert result.passed is False
        assert len(result.errors) > 0

    def test_warns_missing_brand_name(self):
        v = BrandValidator()
        brand = self._make_brand()
        result = v.validate("We make great products.", brand)
        assert any("Brand name" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# PersonaValidator
# ---------------------------------------------------------------------------

class TestPersonaValidator:
    def test_passes_matching_text(self):
        v = PersonaValidator()
        result = v.validate(
            "Our proven, research-backed methodology delivers data-driven results.",
            AUTHORITATIVE,
        )
        assert result.passed is True
        assert len(result.details["preferred_words_found"]) > 0

    def test_catches_avoided_word(self):
        v = PersonaValidator()
        result = v.validate(
            "Maybe this could possibly work, I think.",
            AUTHORITATIVE,
        )
        assert result.passed is False
        assert any("maybe" in e.lower() for e in result.errors)

    def test_formal_fingerprint_rejects_casual(self):
        v = PersonaValidator()
        result = v.validate(
            "Hey, this is gonna be awesome, yeah!",
            AUTHORITATIVE,
        )
        assert result.passed is False

    def test_empathetic_allows_warm_language(self):
        v = PersonaValidator()
        result = v.validate(
            "We understand how you feel. Together we care about your journey.",
            EMPATHETIC,
        )
        assert result.passed is True
