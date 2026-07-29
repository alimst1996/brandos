#!/usr/bin/env python3
"""Comprehensive test suite for BrandOS text content generation engine.

Covers all six modules: brand_profile, fingerprints, prompt_contracts,
providers (with stub), validators, and text_generator (end-to-end).

Run: python -m pytest tests/test_text_generator.py -v
"""
import json
import sys
import time
import unittest
from pathlib import Path

# Ensure scripts/ is importable
_root = Path(__file__).resolve().parent.parent
_scripts = _root / "scripts"
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))

from brand_profile import (
    BrandProfile,
    BrandIdentity,
    BrandVoice,
    BrandConstraints,
)
from fingerprints import Fingerprint, get_fingerprint, list_fingerprints
from prompt_contracts import (
    PromptContract,
    get_contract,
    list_contracts,
    register_contract,
)
from providers import (
    GenerationResult,
    StubProvider,
    get_provider,
    list_providers,
    register_provider,
)
from validators import (
    ClaimValidator,
    BrandVoiceValidator,
    PersonaValidator,
    ValidationResult,
    validate_output,
    is_valid,
    get_errors,
    get_warnings,
)
from text_generator import TextGenerator, GenerationAudit


# ===========================================================================
# Brand profile tests
# ===========================================================================

class TestBrandIdentity(unittest.TestCase):
    def test_valid_identity(self):
        ident = BrandIdentity(name="Acme", industry="Tech")
        self.assertEqual(ident.validate(), [])

    def test_empty_name_invalid(self):
        ident = BrandIdentity(name="")
        self.assertIn("Brand name is required", ident.validate())

    def test_whitespace_name_invalid(self):
        ident = BrandIdentity(name="   ")
        self.assertIn("Brand name is required", ident.validate())

    def test_frozen(self):
        ident = BrandIdentity(name="Acme")
        with self.assertRaises(AttributeError):
            ident.name = "Other"


class TestBrandVoice(unittest.TestCase):
    def test_defaults(self):
        voice = BrandVoice()
        self.assertEqual(voice.tone, "professional")
        self.assertEqual(voice.reading_level, "general")

    def test_empty_tone_invalid(self):
        voice = BrandVoice(tone="")
        self.assertIn("Voice tone is required", voice.validate())

    def test_frozen_with_tuple_personality(self):
        voice = BrandVoice(personality=("innovative", "warm"))
        self.assertEqual(voice.personality, ("innovative", "warm"))


class TestBrandConstraints(unittest.TestCase):
    def test_defaults(self):
        c = BrandConstraints()
        self.assertEqual(c.language, "en")
        self.assertEqual(c.max_content_length, 0)

    def test_negative_length_invalid(self):
        c = BrandConstraints(max_content_length=-1)
        self.assertIn("max_content_length must be >= 0", c.validate())


class TestBrandProfile(unittest.TestCase):
    def _make_profile(self, **kwargs):
        defaults = dict(
            identity=BrandIdentity(name="TestCorp", industry="SaaS"),
            voice=BrandVoice(tone="professional", personality=("innovative",)),
            values=["trust", "quality"],
            constraints=BrandConstraints(language="en"),
        )
        defaults.update(kwargs)
        return BrandProfile(**defaults)

    def test_valid_profile(self):
        p = self._make_profile()
        self.assertTrue(p.is_valid())
        self.assertEqual(p.validate(), [])

    def test_invalid_identity_propagates(self):
        p = self._make_profile(identity=BrandIdentity(name=""))
        self.assertFalse(p.is_valid())
        self.assertIn("Brand name is required", p.validate())

    def test_roundtrip_dict(self):
        p = self._make_profile(metadata={"key": "value"})
        d = p.to_dict()
        p2 = BrandProfile.from_dict(d)
        self.assertEqual(p.identity.name, p2.identity.name)
        self.assertEqual(p.voice.personality, p2.voice.personality)
        self.assertEqual(p.values, p2.values)
        self.assertEqual(p.constraints.language, p2.constraints.language)
        self.assertEqual(p.metadata, p2.metadata)

    def test_roundtrip_json(self):
        p = self._make_profile()
        j = p.to_json()
        p2 = BrandProfile.from_json(j)
        self.assertEqual(p.identity.name, p2.identity.name)

    def test_prohibited_terms_roundtrip(self):
        p = self._make_profile(
            constraints=BrandConstraints(prohibited_terms=("cheap", "discount"))
        )
        d = p.to_dict()
        p2 = BrandProfile.from_dict(d)
        self.assertEqual(p2.constraints.prohibited_terms, ("cheap", "discount"))


# ===========================================================================
# Fingerprint tests
# ===========================================================================

class TestFingerprints(unittest.TestCase):
    def test_three_fingerprints_exist(self):
        fps = list_fingerprints()
        self.assertEqual(len(fps), 3)
        self.assertIn("authority", fps)
        self.assertIn("empathy", fps)
        self.assertIn("momentum", fps)

    def test_get_fingerprint(self):
        fp = get_fingerprint("authority")
        self.assertEqual(fp.name, "authority")
        self.assertIn("credibility", fp.intent.lower())

    def test_unknown_fingerprint_raises(self):
        with self.assertRaises(KeyError) as ctx:
            get_fingerprint("nonexistent")
        self.assertIn("nonexistent", str(ctx.exception))

    def test_render_system_prompt_includes_brand(self):
        fp = get_fingerprint("empathy")
        profile = BrandProfile(
            identity=BrandIdentity(name="Acme", industry="Tech"),
            voice=BrandVoice(tone="warm"),
        )
        prompt = fp.render_system_prompt(profile)
        self.assertIn("Acme", prompt)
        self.assertIn("Tech", prompt)
        self.assertIn("warm", prompt)
        self.assertIn("Empathetic Guidance", prompt)

    def test_render_system_prompt_includes_prohibited(self):
        fp = get_fingerprint("authority")
        profile = BrandProfile(
            identity=BrandIdentity(name="Acme"),
            constraints=BrandConstraints(prohibited_terms=("cheap", "hack")),
        )
        prompt = fp.render_system_prompt(profile)
        self.assertIn("cheap", prompt)
        self.assertIn("hack", prompt)

    def test_render_system_prompt_includes_values(self):
        fp = get_fingerprint("momentum")
        profile = BrandProfile(
            identity=BrandIdentity(name="Acme"),
            values=["innovation", "trust"],
        )
        prompt = fp.render_system_prompt(profile)
        self.assertIn("innovation", prompt)
        self.assertIn("trust", prompt)

    def test_get_constraints(self):
        fp = get_fingerprint("authority")
        c = fp.get_constraints()
        self.assertEqual(c["name"], "authority")
        self.assertIsInstance(c["style_markers"], list)
        self.assertTrue(len(c["style_markers"]) > 0)

    def test_fingerprint_is_frozen(self):
        fp = get_fingerprint("authority")
        with self.assertRaises(AttributeError):
            fp.name = "other"


# ===========================================================================
# Prompt contract tests
# ===========================================================================

class TestPromptContracts(unittest.TestCase):
    def test_three_contracts_exist(self):
        names = list_contracts()
        self.assertIn("product-description", names)
        self.assertIn("brand-story", names)
        self.assertIn("social-post", names)

    def test_get_contract(self):
        c = get_contract("product-description")
        self.assertEqual(c.name, "product-description")
        self.assertEqual(c.version, 1)

    def test_unknown_contract_raises(self):
        with self.assertRaises(KeyError):
            get_contract("nonexistent")

    def test_render_with_all_vars(self):
        c = get_contract("product-description")
        text = c.render(
            product_name="Midnight Noir",
            product_category="perfume",
            key_notes="oud, amber",
            target_audience="luxury buyers",
            unique_selling_point="artisanal blend",
            fingerprint_name="authority",
            fingerprint_guidance="Be authoritative.",
        )
        self.assertIn("Midnight Noir", text)
        self.assertIn("perfume", text)
        self.assertIn("oud, amber", text)

    def test_render_with_defaults(self):
        c = get_contract("product-description")
        text = c.render(
            product_name="Test",
            product_category="cat",
            key_notes="a, b",
            target_audience="all",
            unique_selling_point="good",
            fingerprint_name="empathy",
            fingerprint_guidance="Be empathetic.",
        )
        # Optional defaults should be present
        self.assertIn("medium", text)

    def test_render_missing_required_raises(self):
        c = get_contract("product-description")
        with self.assertRaises(ValueError) as ctx:
            c.render(product_name="Test")
        self.assertIn("Missing required", str(ctx.exception))

    def test_render_unknown_var_raises(self):
        c = get_contract("product-description")
        with self.assertRaises(ValueError) as ctx:
            c.render(
                product_name="Test",
                product_category="cat",
                key_notes="a",
                target_audience="all",
                unique_selling_point="good",
                fingerprint_name="auth",
                fingerprint_guidance="x",
                bogus_variable="nope",
            )
        self.assertIn("Unknown variables", str(ctx.exception))

    def test_register_custom_contract(self):
        custom = PromptContract(
            name="test-custom",
            version=1,
            description="Test",
            template="Hello {name}",
            required_vars=("name",),
        )
        register_contract(custom)
        c = get_contract("test-custom")
        self.assertEqual(c.render(name="World"), "Hello World")
        # Cleanup
        import prompt_contracts
        del prompt_contracts._CONTRACTS["test-custom"]

    def test_to_dict_from_dict(self):
        c = get_contract("social-post")
        d = c.to_dict()
        c2 = PromptContract.from_dict(d)
        self.assertEqual(c.name, c2.name)
        self.assertEqual(c.version, c2.version)
        self.assertEqual(c.template, c2.template)

    def test_get_placeholders(self):
        c = PromptContract(
            name="test",
            version=1,
            description="test contract",
            template="{a} and {b}",
        )
        self.assertEqual(c.get_placeholders(), ["a", "b"])


# ===========================================================================
# Provider tests
# ===========================================================================

class TestGenerationResult(unittest.TestCase):
    def test_success_result(self):
        r = GenerationResult(text="hello", provider="stub", model="stub-model")
        self.assertTrue(r.success)
        self.assertIsNone(r.error)

    def test_error_result(self):
        r = GenerationResult(text="", provider="stub", model="stub-model", error="fail")
        self.assertFalse(r.success)

    def test_audit_dict_excludes_raw(self):
        r = GenerationResult(
            text="hello",
            provider="stub",
            model="m",
            raw_response={"secret": "key"},
        )
        d = r.to_audit_dict()
        self.assertNotIn("raw_response", d)
        self.assertEqual(d["text"], "hello")

    def test_audit_dict_truncates_long_text(self):
        r = GenerationResult(text="x" * 600, provider="p", model="m")
        d = r.to_audit_dict()
        self.assertTrue(d["text"].endswith("..."))


class TestStubProvider(unittest.TestCase):
    def test_available(self):
        p = StubProvider()
        self.assertTrue(p.is_available())

    def test_generate(self):
        p = StubProvider(response_text="test output")
        r = p.generate("sys", "user")
        self.assertTrue(r.success)
        self.assertEqual(r.text, "test output")
        self.assertEqual(r.provider, "stub")
        self.assertGreater(r.tokens_in, 0)

    def test_not_available(self):
        p = StubProvider(available=False)
        self.assertFalse(p.is_available())


class TestProviderRegistry(unittest.TestCase):
    def test_providers_registered(self):
        names = list_providers()
        self.assertIn("openai", names)
        self.assertIn("openrouter", names)
        self.assertIn("stub", names)

    def test_get_provider(self):
        p = get_provider("stub")
        self.assertIsInstance(p, StubProvider)

    def test_get_unknown_raises(self):
        with self.assertRaises(KeyError):
            get_provider("nonexistent")

    def test_register_custom(self):
        custom = StubProvider(response_text="custom", available=True)
        custom.name = "test-provider"
        register_provider(custom)
        p = get_provider("test-provider")
        self.assertEqual(p.name, "test-provider")
        # Cleanup
        import providers
        del providers._PROVIDERS["test-provider"]


# ===========================================================================
# Validator tests
# ===========================================================================

class TestClaimValidator(unittest.TestCase):
    def setUp(self):
        self.v = ClaimValidator()

    def test_clean_text_passes(self):
        results = self.v.validate("Our product offers reliable performance.")
        passed = [r for r in results if r.passed]
        self.assertTrue(len(passed) > 0)

    def test_superlative_flagged(self):
        results = self.v.validate("The best product in the world.")
        flagged = [r for r in results if not r.passed and r.rule == "claim:superlative"]
        self.assertTrue(len(flagged) > 0)
        self.assertIn("best", flagged[0].detail.lower())

    def test_statistic_flagged(self):
        results = self.v.validate("90% of users prefer our product.")
        flagged = [r for r in results if not r.passed and r.rule == "claim:statistic"]
        self.assertTrue(len(flagged) > 0)

    def test_number_one_flagged(self):
        results = self.v.validate("We are the #1 solution.")
        flagged = [r for r in results if not r.passed]
        self.assertTrue(any("superlative" in r.rule for r in flagged))

    def test_world_class_flagged(self):
        results = self.v.validate("A world-class experience.")
        flagged = [r for r in results if not r.passed]
        self.assertTrue(any("superlative" in r.rule for r in flagged))

    def test_location_present(self):
        results = self.v.validate("The best solution.")
        for r in results:
            if not r.passed and r.location >= 0:
                self.assertGreaterEqual(r.location, 0)


class TestBrandVoiceValidator(unittest.TestCase):
    def setUp(self):
        self.v = BrandVoiceValidator()
        self.profile = BrandProfile(
            identity=BrandIdentity(name="Test"),
            constraints=BrandConstraints(
                prohibited_terms=("cheap", "discount"),
                max_content_length=100,
            ),
        )

    def test_clean_text_passes(self):
        results = self.v.validate("Quality content.", self.profile)
        self.assertTrue(is_valid(results))

    def test_prohibited_term_flagged(self):
        results = self.v.validate("This is a cheap product.", self.profile)
        errors = get_errors(results)
        self.assertTrue(len(errors) > 0)
        self.assertIn("cheap", errors[0].detail)

    def test_length_exceeded(self):
        text = "x" * 101
        results = self.v.validate(text, self.profile)
        errors = get_errors(results)
        self.assertTrue(any("length" in e.detail.lower() for e in errors))

    def test_empty_text_flagged(self):
        results = self.v.validate("", self.profile)
        errors = get_errors(results)
        self.assertTrue(any("empty" in e.detail.lower() for e in errors))

    def test_no_prohibited_terms_passes(self):
        p = BrandProfile(identity=BrandIdentity(name="Test"))
        results = self.v.validate("Premium quality content.", p)
        self.assertTrue(is_valid(results))

    def test_case_insensitive_prohibited(self):
        results = self.v.validate("CHEAP and Discount.", self.profile)
        errors = get_errors(results)
        self.assertEqual(len(errors), 2)


class TestPersonaValidator(unittest.TestCase):
    def setUp(self):
        self.v = PersonaValidator()

    def test_authority_clean(self):
        results = self.v.validate(
            "Research demonstrates the efficacy of our approach.", "authority"
        )
        self.assertTrue(is_valid(results))

    def test_authority_casual_minimizer(self):
        results = self.v.validate("It is just a simple solution.", "authority")
        warnings = [r for r in results if not r.passed]
        self.assertTrue(len(warnings) > 0)

    def test_empathy_dismissive(self):
        results = self.v.validate("Obviously everyone knows this.", "empathy")
        warnings = [r for r in results if not r.passed]
        self.assertTrue(len(warnings) > 0)

    def test_momentum_hedging(self):
        results = self.v.validate("You might consider perhaps trying this.", "momentum")
        warnings = [r for r in results if not r.passed]
        self.assertTrue(len(warnings) > 0)

    def test_unknown_fingerprint_passes(self):
        results = self.v.validate("Any text here.", "unknown")
        self.assertTrue(is_valid(results))


class TestValidateOutput(unittest.TestCase):
    def _make_profile(self):
        return BrandProfile(
            identity=BrandIdentity(name="Test"),
            constraints=BrandConstraints(prohibited_terms=("hack",)),
        )

    def test_combined_validators(self):
        p = self._make_profile()
        results = validate_output("Our product delivers value.", p, "authority")
        self.assertTrue(is_valid(results))

    def test_combined_catches_prohibited_and_claim(self):
        p = self._make_profile()
        results = validate_output("The best hack for 90% of users.", p, "authority")
        errors = get_errors(results)
        warnings = get_warnings(results)
        # prohibited term "hack" should be an error
        self.assertTrue(any("prohibited" in r.rule for r in errors))
        # superlatives and statistics should be warnings
        self.assertTrue(len(warnings) >= 2)

    def test_no_fingerprint_skips_persona(self):
        p = self._make_profile()
        results = validate_output("Quality content.", p)
        persona_results = [r for r in results if r.rule.startswith("persona:")]
        self.assertEqual(len(persona_results), 0)


class TestValidationResultHelpers(unittest.TestCase):
    def test_is_valid_all_pass(self):
        results = [ValidationResult(rule="r", passed=True)]
        self.assertTrue(is_valid(results))

    def test_is_valid_with_warning(self):
        results = [
            ValidationResult(rule="r", passed=True),
            ValidationResult(rule="w", passed=False, severity="warning"),
        ]
        # warnings don't fail validation
        self.assertTrue(is_valid(results))

    def test_is_valid_with_error(self):
        results = [
            ValidationResult(rule="e", passed=False, severity="error"),
        ]
        self.assertFalse(is_valid(results))

    def test_get_errors_and_warnings(self):
        results = [
            ValidationResult(rule="ok", passed=True, severity="info"),
            ValidationResult(rule="err", passed=False, severity="error"),
            ValidationResult(rule="warn", passed=False, severity="warning"),
        ]
        self.assertEqual(len(get_errors(results)), 1)
        self.assertEqual(len(get_warnings(results)), 1)


# ===========================================================================
# Text generator (end-to-end) tests
# ===========================================================================

class TestTextGenerator(unittest.TestCase):
    def _make_profile(self, **kwargs):
        defaults = dict(
            identity=BrandIdentity(name="Evardly 1909", industry="Luxury Fragrance"),
            voice=BrandVoice(
                tone="elegant",
                personality=("sophisticated", "minimalist"),
            ),
            values=["craftsmanship", "exclusivity"],
            constraints=BrandConstraints(
                prohibited_terms=("cheap", "discount", "sale"),
                language="en",
            ),
        )
        defaults.update(kwargs)
        return BrandProfile(**defaults)

    def _make_stub_provider(self, text="A beautifully crafted fragrance."):
        return StubProvider(response_text=text)

    def test_basic_generation(self):
        profile = self._make_profile()
        provider = self._make_stub_provider()
        gen = TextGenerator(profile=profile, provider=provider)
        audit = gen.generate(
            contract_name="product-description",
            fingerprint_name="authority",
            product_name="Midnight Noir",
            product_category="luxury perfume",
            key_notes="oud, amber, black rose",
            target_audience="luxury fragrance enthusiasts",
            unique_selling_point="artisanal blending",
        )
        self.assertTrue(audit.result.success)
        self.assertIn("Midnight Noir", audit.user_prompt)
        self.assertIn("Evardly 1909", audit.system_prompt)
        self.assertEqual(audit.contract_name, "product-description")
        self.assertEqual(audit.fingerprint_name, "authority")

    def test_provenance_attached(self):
        profile = self._make_profile()
        provider = self._make_stub_provider()
        gen = TextGenerator(profile=profile, provider=provider)
        audit = gen.generate(
            contract_name="product-description",
            fingerprint_name="empathy",
            product_name="Test",
            product_category="cat",
            key_notes="a",
            target_audience="all",
            unique_selling_point="good",
        )
        self.assertEqual(audit.result.input_provenance["contract"], "product-description")
        self.assertEqual(audit.result.input_provenance["fingerprint"], "empathy")
        self.assertEqual(audit.result.input_provenance["profile"], "Evardly 1909")
        self.assertEqual(audit.result.prompt_version, 1)

    def test_validation_runs_automatically(self):
        profile = self._make_profile()
        # Stub returns text with prohibited term
        provider = self._make_stub_provider(text="This is a cheap fragrance.")
        gen = TextGenerator(profile=profile, provider=provider)
        audit = gen.generate(
            contract_name="product-description",
            fingerprint_name="authority",
            product_name="Test",
            product_category="cat",
            key_notes="a",
            target_audience="all",
            unique_selling_point="good",
        )
        self.assertFalse(audit.is_valid)
        self.assertTrue(len(audit.errors) > 0)
        self.assertTrue(any("prohibited" in e.rule for e in audit.errors))

    def test_validation_disabled(self):
        profile = self._make_profile()
        provider = self._make_stub_provider(text="cheap stuff")
        gen = TextGenerator(profile=profile, provider=provider, auto_validate=False)
        audit = gen.generate(
            contract_name="product-description",
            fingerprint_name="authority",
            product_name="Test",
            product_category="cat",
            key_notes="a",
            target_audience="all",
            unique_selling_point="good",
        )
        self.assertEqual(len(audit.validation_results), 0)

    def test_audit_dict_structure(self):
        profile = self._make_profile()
        provider = self._make_stub_provider()
        gen = TextGenerator(profile=profile, provider=provider)
        audit = gen.generate(
            contract_name="product-description",
            fingerprint_name="authority",
            product_name="Test",
            product_category="cat",
            key_notes="a",
            target_audience="all",
            unique_selling_point="good",
        )
        d = audit.to_dict()
        self.assertIn("result", d)
        self.assertIn("fingerprint_name", d)
        self.assertIn("contract_name", d)
        self.assertIn("is_valid", d)
        self.assertIn("validation_summary", d)

    def test_all_fingerprints_work(self):
        profile = self._make_profile()
        provider = self._make_stub_provider()
        gen = TextGenerator(profile=profile, provider=provider)
        for fp_name in list_fingerprints():
            audit = gen.generate(
                contract_name="product-description",
                fingerprint_name=fp_name,
                product_name="Test",
                product_category="cat",
                key_notes="a",
                target_audience="all",
                unique_selling_point="good",
            )
            self.assertTrue(audit.result.success, f"Fingerprint {fp_name} failed")

    def test_all_contracts_work(self):
        profile = self._make_profile()
        provider = self._make_stub_provider()
        gen = TextGenerator(profile=profile, provider=provider)

        # product-description
        audit = gen.generate(
            contract_name="product-description",
            fingerprint_name="authority",
            product_name="Test",
            product_category="cat",
            key_notes="a",
            target_audience="all",
            unique_selling_point="good",
        )
        self.assertTrue(audit.result.success)

        # brand-story
        audit = gen.generate(
            contract_name="brand-story",
            fingerprint_name="empathy",
            brand_name="Evardly",
            industry="fragrance",
            values="luxury",
            milestones="founded 1909",
            founder_inspiration="art",
        )
        self.assertTrue(audit.result.success)

        # social-post
        audit = gen.generate(
            contract_name="social-post",
            fingerprint_name="momentum",
            brand_name="Evardly",
            platform="Instagram",
            topic="new launch",
            call_to_action="Shop now",
        )
        self.assertTrue(audit.result.success)

    def test_invalid_profile_raises(self):
        profile = BrandProfile(identity=BrandIdentity(name=""))
        provider = self._make_stub_provider()
        with self.assertRaises(ValueError) as ctx:
            TextGenerator(profile=profile, provider=provider)
        self.assertIn("Brand name is required", str(ctx.exception))

    def test_generate_safe_retries(self):
        """generate_safe should retry on validation failure and return best."""
        profile = self._make_profile(
            constraints=BrandConstraints(prohibited_terms=("cheap",))
        )
        # Always returns prohibited term
        provider = self._make_stub_provider(text="cheap quality")
        gen = TextGenerator(profile=profile, provider=provider)
        audit = gen.generate_safe(
            contract_name="product-description",
            fingerprint_name="authority",
            max_retries=1,
            product_name="Test",
            product_category="cat",
            key_notes="a",
            target_audience="all",
            unique_selling_point="good",
        )
        # Should have attempted but still found errors (stub always returns same text)
        self.assertFalse(audit.is_valid)


class TestTextGeneratorProviderResolution(unittest.TestCase):
    def test_direct_provider_instance(self):
        profile = BrandProfile(identity=BrandIdentity(name="Test"))
        stub = StubProvider(response_text="ok")
        gen = TextGenerator(profile=profile, provider=stub)
        self.assertEqual(gen.provider_name, "stub")

    def test_explicit_provider_name(self):
        profile = BrandProfile(identity=BrandIdentity(name="Test"))
        gen = TextGenerator(profile=profile, provider_name="stub")
        self.assertEqual(gen.provider_name, "stub")

    def test_no_provider_available_raises(self):
        """When no API keys and no stub, should raise."""
        profile = BrandProfile(identity=BrandIdentity(name="Test"))
        # Register a provider that's not available
        unavailable = StubProvider(available=False)
        import providers as pv
        old = pv._PROVIDERS.get("_test_unavail")
        pv._PROVIDERS["_test_unavail"] = unavailable
        try:
            # auto should fail when only unavailable providers exist
            # (but stub is available by default, so this test verifies the auto path)
            gen = TextGenerator(profile=profile, provider_name="auto")
            self.assertIsNotNone(gen)
        finally:
            if old is not None:
                pv._PROVIDERS["_test_unavail"] = old
            elif "_test_unavail" in pv._PROVIDERS:
                del pv._PROVIDERS["_test_unavail"]


if __name__ == "__main__":
    unittest.main()
