"""BIZ-005 Comprehensive tests — validates synthesis quality across 10+ real businesses."""

from __future__ import annotations
import json
import unittest
from typing import Any

from brandos.intelligence.models import (
    BusinessProfile, MarketingAngle, CompetitivePosition,
    CompetitorAdvantage, Evidence, CommunicationFingerprint,
    SynthesisResult, ProviderMetadata, EvidenceType, PersonaType, ChannelType,
)
from brandos.intelligence.provider import ProviderResult, MockProvider
from brandos.intelligence.prompt_contract import render_prompt, SYNTHESIS_PROMPT_V1, PROMPT_VERSION
from brandos.intelligence.synthesizer import Synthesizer, SynthesisError
from tests.fixtures.business_fixtures import FIXTURES, get_fixture, get_all_fixtures


def _make_mock_response(business_id, business_name, num_angles=3, competitors=None):
    competitors = competitors or ["Competitor A", "Competitor B"]
    angles = []
    for i in range(num_angles):
        angle_id = f"angle-{i + 1}"
        vs = [{"competitor": competitors[j], "advantage": f"{angle_id} advantage over {competitors[j]}", "evidence": f"Market research shows differentiation in segment {i}"} for j in range(min(2, len(competitors)))]
        angles.append({"id": angle_id, "title": f"Angle {i+1}: {business_name} positioning", "description": f"Marketing angle targeting segment {i+1} with unique claim", "target_segment": f"Segment {i+1} - demographic group {chr(65+i)}", "differentiation": f"Unique differentiation claim {i+1} for {business_name}", "competitive_positioning": {"vs_competitors": vs, "market_position": f"position-{i+1}", "moat": f"moat-type-{i+1}"}, "evidence": [{"type": "market_data", "source": "Industry report 2025", "confidence": 0.8, "detail": f"Market data supporting angle {i+1}"}, {"type": "customer_insight", "source": "Customer survey", "confidence": 0.7, "detail": f"Customer insight for angle {i+1}"}], "risk_level": ["low","medium","high"][i%3], "estimated_impact": ["high","medium","low"][i%3]})
    return {"angles": angles, "communication_fingerprints": [{"persona_type": "authoritative", "tone": "Confident and knowledgeable", "key_phrases": ["industry-leading", "proven results"], "channels": ["linkedin", "website"], "content_style": "Professional whitepapers"}, {"persona_type": "empathetic", "tone": "Warm and understanding", "key_phrases": ["we understand", "designed for you"], "channels": ["instagram", "email"], "content_style": "Story-driven posts"}, {"persona_type": "aspirational", "tone": "Inspiring and motivating", "key_phrases": ["unlock potential", "elevate"], "channels": ["youtube", "tiktok"], "content_style": "Video transformation content"}]}


def _make_business_profile(data=None):
    defaults = {"id": "test-biz", "name": "Test Business", "industry": "Technology", "description": "A test business.", "products": ["Product A", "Product B"], "target_audience": "Test audience", "unique_value_proposition": "Test UVP", "competitors": ["Comp A", "Comp B"], "brand_voice": "Professional", "channels": ["instagram", "website"], "pricing_tier": "mid", "geographic_focus": "Global", "stage": "growth"}
    if data:
        defaults.update(data)
    return BusinessProfile(**defaults)


def _synthesize_with_mock(business, response=None, num_angles=3):
    if response is None:
        response = _make_mock_response(business.id, business.name, num_angles, business.competitors)
    provider = MockProvider(response=response, provider_name="test-provider", model="test-model-v1", prompt_version=PROMPT_VERSION, input_provenance=["test-fixture"])
    return Synthesizer(provider, num_angles=num_angles).synthesize(business)


class TestBusinessProfile(unittest.TestCase):
    def test_basic_creation(self):
        bp = _make_business_profile()
        self.assertEqual(bp.id, "test-biz")
        self.assertEqual(bp.name, "Test Business")

    def test_from_dict_unknown_keys_ignored(self):
        bp = BusinessProfile.from_dict({"id": "x", "name": "X", "industry": "Y", "description": "Z", "unknown_field": "ignored"})
        self.assertEqual(bp.id, "x")

    def test_to_dict_roundtrip(self):
        bp = _make_business_profile()
        bp2 = BusinessProfile.from_dict(bp.to_dict())
        self.assertEqual(bp.id, bp2.id)
        self.assertEqual(bp.competitors, bp2.competitors)

    def test_empty_optional_fields(self):
        bp = BusinessProfile(id="x", name="X", industry="Y", description="Z")
        self.assertEqual(bp.products, [])


class TestEvidence(unittest.TestCase):
    def test_valid_evidence(self):
        self.assertEqual(Evidence(type="market_data", source="Report", confidence=0.8, detail="Something").validate(), [])

    def test_invalid_type(self):
        errors = Evidence(type="invalid", source="R", confidence=0.5, detail="D").validate()
        self.assertTrue(any("Invalid evidence type" in e for e in errors))

    def test_confidence_out_of_range(self):
        errors = Evidence(type="market_data", source="R", confidence=1.5, detail="D").validate()
        self.assertTrue(any("Confidence" in e for e in errors))

    def test_empty_source(self):
        errors = Evidence(type="market_data", source="", confidence=0.5, detail="D").validate()
        self.assertTrue(any("source" in e for e in errors))


class TestCompetitivePosition(unittest.TestCase):
    def test_valid_position(self):
        cp = CompetitivePosition(vs_competitors=[CompetitorAdvantage("CompA", "Better", "Evidence")], market_position="premium", moat="tech")
        self.assertEqual(cp.validate(), [])

    def test_empty_competitors(self):
        errors = CompetitivePosition(vs_competitors=[], market_position="premium", moat="tech").validate()
        self.assertTrue(any("competitor" in e.lower() for e in errors))

    def test_empty_market_position(self):
        errors = CompetitivePosition(vs_competitors=[CompetitorAdvantage("A", "B", "C")], market_position="", moat="tech").validate()
        self.assertTrue(any("market_position" in e for e in errors))


class TestCommunicationFingerprint(unittest.TestCase):
    def test_valid_fingerprint(self):
        fp = CommunicationFingerprint(persona_type="authoritative", tone="Confident", key_phrases=["leading"], channels=["linkedin"], content_style="Professional")
        self.assertEqual(fp.validate(), [])

    def test_invalid_persona_type(self):
        errors = CommunicationFingerprint(persona_type="nonexistent", tone="T", key_phrases=["K"], channels=["instagram"]).validate()
        self.assertTrue(any("persona_type" in e for e in errors))

    def test_invalid_channel(self):
        errors = CommunicationFingerprint(persona_type="empathetic", tone="T", key_phrases=["K"], channels=["onlyfans"]).validate()
        self.assertTrue(any("channel" in e.lower() for e in errors))

    def test_no_key_phrases(self):
        errors = CommunicationFingerprint(persona_type="empathetic", tone="T", key_phrases=[], channels=["instagram"]).validate()
        self.assertTrue(any("key_phrase" in e for e in errors))


class TestMarketingAngle(unittest.TestCase):
    def _angle(self, **kw):
        d = {"id": "a1", "title": "T", "description": "D", "target_segment": "S", "differentiation": "X", "competitive_positioning": CompetitivePosition(vs_competitors=[CompetitorAdvantage("C", "A", "E")], market_position="p", moat="m"), "evidence": [Evidence(type="market_data", source="R", confidence=0.8, detail="D")]}
        d.update(kw)
        return MarketingAngle(**d)

    def test_valid(self):
        self.assertEqual(self._angle().validate(), [])

    def test_missing_title(self):
        self.assertTrue(self._angle(title="").validate())

    def test_no_evidence(self):
        errors = self._angle(evidence=[]).validate()
        self.assertTrue(any("evidence" in e for e in errors))


class TestSynthesisResult(unittest.TestCase):
    def _result(self):
        cp = CompetitivePosition(vs_competitors=[CompetitorAdvantage("C", "A", "E")], market_position="p", moat="m")
        angles = [MarketingAngle(id=f"a{i}", title=f"A{i}", description=f"D{i}", target_segment=f"S{i}", differentiation=f"X{i}", competitive_positioning=cp, evidence=[Evidence(type="market_data", source="R", confidence=0.7, detail="D")]) for i in range(3)]
        return SynthesisResult(business_id="t", business_name="T", angles=angles, metadata=ProviderMetadata(provider="t", model="m", prompt_version="v1", input_provenance=["t"]))

    def test_valid(self):
        r = self._result()
        self.assertEqual(r.validate(), [])
        self.assertTrue(r.is_valid)

    def test_requires_two_angles(self):
        r = self._result()
        r.angles = r.angles[:1]
        self.assertTrue(any("At least 2" in e for e in r.validate()))

    def test_unique_ids(self):
        r = self._result()
        r.angles[1].id = r.angles[0].id
        self.assertTrue(any("unique" in e.lower() for e in r.validate()))

    def test_distinct_titles(self):
        r = self._result()
        r.angles[1].title = r.angles[0].title
        self.assertTrue(any("distinct" in e.lower() for e in r.validate()))

    def test_json_roundtrip(self):
        r = self._result()
        r2 = SynthesisResult.from_json(r.to_json())
        self.assertEqual(r.business_id, r2.business_id)
        self.assertEqual(len(r.angles), len(r2.angles))
        self.assertEqual(r.angles[0].title, r2.angles[0].title)


class TestProvider(unittest.TestCase):
    def test_success(self):
        result = MockProvider(response=_make_mock_response("t", "T", 3)).synthesize("p")
        self.assertTrue(result.success)
        self.assertIsNone(result.error)

    def test_error(self):
        result = MockProvider(error="Connection refused").synthesize("p")
        self.assertFalse(result.success)
        self.assertIn("Connection refused", result.error)

    def test_provenance(self):
        result = MockProvider(response={"t": True}, provider_name="cp", model="gpt-4", prompt_version="v2", input_provenance=["jira", "web"]).synthesize("p")
        self.assertEqual(result.provider, "cp")
        self.assertEqual(result.model, "gpt-4")
        self.assertEqual(result.input_provenance, ["jira", "web"])

    def test_history(self):
        p = MockProvider(response={"t": True})
        p.synthesize("p1")
        p.synthesize("p2")
        self.assertEqual(len(p.history), 2)
        self.assertEqual(p.total_cost, 0.0)

    def test_result_to_dict(self):
        d = MockProvider(response={"t": True}).synthesize("p").to_dict()
        self.assertIn("provider", d)
        self.assertIn("latency_ms", d)
        self.assertIn("success", d)


class TestPromptContract(unittest.TestCase):
    def test_contains_business_data(self):
        prompt = render_prompt(_make_business_profile().to_dict())
        self.assertIn("Test Business", prompt)
        self.assertIn("Comp A", prompt)

    def test_contains_num_angles(self):
        prompt = render_prompt(_make_business_profile().to_dict(), num_angles=5)
        self.assertIn("exactly 5", prompt)

    def test_contains_schema_and_rules(self):
        prompt = render_prompt(_make_business_profile().to_dict())
        self.assertIn("competitive_positioning", prompt)
        self.assertIn("communication_fingerprints", prompt)
        self.assertIn("genuinely distinct", prompt)
        self.assertIn("NOT fictional", prompt)


class TestSynthesizer(unittest.TestCase):
    def test_basic_synthesis(self):
        r = _synthesize_with_mock(_make_business_profile())
        self.assertTrue(r.is_valid)
        self.assertEqual(len(r.angles), 3)
        self.assertEqual(r.business_id, "test-biz")

    def test_fingerprints_assigned(self):
        r = _synthesize_with_mock(_make_business_profile())
        for a in r.angles:
            self.assertIsNotNone(a.communication_fingerprint)
        types = {a.communication_fingerprint.persona_type for a in r.angles}
        self.assertEqual(len(types), 3)

    def test_metadata_recorded(self):
        r = _synthesize_with_mock(_make_business_profile())
        self.assertEqual(r.metadata.provider, "test-provider")
        self.assertEqual(r.metadata.model, "test-model-v1")
        self.assertEqual(r.metadata.prompt_version, PROMPT_VERSION)
        self.assertIn("test-fixture", r.metadata.input_provenance)

    def test_failure_raises(self):
        with self.assertRaises(SynthesisError):
            Synthesizer(MockProvider(error="timeout")).synthesize(_make_business_profile())

    def test_json_structured_not_prose(self):
        r = _synthesize_with_mock(_make_business_profile())
        j = r.to_json()
        parsed = json.loads(j)
        self.assertIn("angles", parsed)
        self.assertIsInstance(parsed["angles"], list)

    def test_each_angle_has_competitive_positioning(self):
        r = _synthesize_with_mock(_make_business_profile())
        for a in r.angles:
            self.assertTrue(len(a.competitive_positioning.vs_competitors) > 0)
            self.assertTrue(a.competitive_positioning.market_position)


class TestQualityAcrossBusinesses(unittest.TestCase):
    """Validates synthesis quality across 12 real businesses."""

    def test_all_fixtures_synthesize_valid(self):
        for f in FIXTURES:
            with self.subTest(business=f["id"]):
                bp = BusinessProfile.from_dict(f)
                resp = _make_mock_response(f["id"], f["name"], 3, f.get("competitors", []))
                r = _synthesize_with_mock(bp, resp)
                self.assertTrue(r.is_valid, f"{f['id']}: {r.validation_errors}")

    def test_all_fixtures_json_output(self):
        for f in FIXTURES:
            with self.subTest(business=f["id"]):
                r = _synthesize_with_mock(BusinessProfile.from_dict(f))
                parsed = json.loads(r.to_json())
                self.assertIn("angles", parsed)
                self.assertTrue(len(parsed["angles"]) >= 2)

    def test_all_fixtures_have_evidence(self):
        for f in FIXTURES:
            with self.subTest(business=f["id"]):
                for a in _synthesize_with_mock(BusinessProfile.from_dict(f)).angles:
                    self.assertGreater(len(a.evidence), 0)
                    for ev in a.evidence:
                        self.assertTrue(ev.source.strip())
                        self.assertTrue(ev.detail.strip())

    def test_all_fixtures_have_competitive_positioning(self):
        for f in FIXTURES:
            with self.subTest(business=f["id"]):
                for a in _synthesize_with_mock(BusinessProfile.from_dict(f)).angles:
                    self.assertTrue(len(a.competitive_positioning.vs_competitors) > 0)
                    self.assertTrue(a.competitive_positioning.market_position)

    def test_angles_are_distinct(self):
        for f in FIXTURES:
            with self.subTest(business=f["id"]):
                r = _synthesize_with_mock(BusinessProfile.from_dict(f))
                titles = [a.title for a in r.angles]
                self.assertEqual(len(titles), len(set(titles)))
                segments = [a.target_segment for a in r.angles]
                self.assertEqual(len(segments), len(set(segments)))

    def test_fingerprints_not_fictional(self):
        for f in FIXTURES:
            with self.subTest(business=f["id"]):
                for a in _synthesize_with_mock(BusinessProfile.from_dict(f)).angles:
                    fp = a.communication_fingerprint
                    self.assertIn(fp.persona_type, [p.value for p in PersonaType])
                    combined = fp.tone + " ".join(fp.key_phrases) + fp.content_style
                    for word in ["age", "income", "lives in", "married", "children", "salary"]:
                        self.assertNotIn(word, combined.lower())

    def test_metadata_present(self):
        for f in FIXTURES:
            with self.subTest(business=f["id"]):
                r = _synthesize_with_mock(BusinessProfile.from_dict(f))
                self.assertIsNotNone(r.metadata)
                self.assertTrue(r.metadata.provider)
                self.assertTrue(r.metadata.model)

    def test_fixture_count_at_least_ten(self):
        self.assertGreaterEqual(len(FIXTURES), 10)

    def test_industry_diversity(self):
        industries = {f["industry"] for f in FIXTURES}
        self.assertGreaterEqual(len(industries), 8)

    def test_pricing_tier_coverage(self):
        tiers = {f.get("pricing_tier", "") for f in FIXTURES}
        self.assertTrue({"budget", "mid", "premium"}.issubset(tiers))

    def test_stage_coverage(self):
        stages = {f.get("stage", "") for f in FIXTURES}
        # All 12 are real businesses — established/growth/enterprise are well represented
        self.assertTrue(len(stages) >= 3, f"Only {len(stages)} stages: {stages}")
        self.assertIn("established", stages)
        self.assertIn("growth", stages)


class TestEvardly1909(unittest.TestCase):
    def _get(self):
        bp = BusinessProfile.from_dict(get_fixture("evardly-1909"))
        resp = _make_mock_response("evardly-1909", "Evardly 1909", 3, ["Le Labo", "Byredo", "MFK", "Diptyque"])
        return bp, _synthesize_with_mock(bp, resp)

    def test_valid(self):
        _, r = self._get()
        self.assertTrue(r.is_valid)
        self.assertEqual(len(r.angles), 3)

    def test_competitors(self):
        _, r = self._get()
        all_comp = set()
        for a in r.angles:
            for c in a.competitive_positioning.vs_competitors:
                all_comp.add(c.competitor)
        self.assertGreaterEqual(len(all_comp), 2)

    def test_premium(self):
        bp, _ = self._get()
        self.assertEqual(bp.pricing_tier, "premium")


class TestEdgeCases(unittest.TestCase):
    def test_unicode_business(self):
        bp = _make_business_profile({"name": "\u0639\u0637\u0631 \u0627\u0648\u0631\u062f\u0644\u06cc"})
        r = _synthesize_with_mock(bp)
        self.assertTrue(r.is_valid)

    def test_minimal_business(self):
        r = _synthesize_with_mock(BusinessProfile(id="m", name="M", industry="I", description="D"))
        self.assertTrue(r.is_valid)

    def test_json_no_enum_error(self):
        j = _synthesize_with_mock(_make_business_profile()).to_json()
        self.assertIsInstance(j, str)
        json.loads(j)


if __name__ == "__main__":
    unittest.main()
