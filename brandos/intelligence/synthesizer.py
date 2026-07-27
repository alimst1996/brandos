"""BIZ-005 Synthesizer — core engine for marketing angle generation.

Takes a BusinessProfile + Provider, produces a validated SynthesisResult.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .models import (
    BusinessProfile,
    MarketingAngle,
    CompetitivePosition,
    CompetitorAdvantage,
    Evidence,
    CommunicationFingerprint,
    SynthesisResult,
    ProviderMetadata,
)
from .provider import Provider, ProviderResult
from .prompt_contract import render_prompt, PROMPT_VERSION

logger = logging.getLogger(__name__)


class SynthesisError(Exception):
    """Raised when synthesis fails irrecoverably."""
    pass


class Synthesizer:
    """Marketing angle synthesizer.

    Usage:
        provider = SomeProvider(...)
        synth = Synthesizer(provider)
        result = synth.synthesize(business_profile)
    """

    DEFAULT_NUM_ANGLES = 3
    MAX_RETRIES = 2

    def __init__(self, provider: Provider, num_angles: int = DEFAULT_NUM_ANGLES):
        self.provider = provider
        self.num_angles = num_angles

    def synthesize(self, business: BusinessProfile) -> SynthesisResult:
        """Run full synthesis pipeline: prompt -> provider -> parse -> validate."""
        prompt = render_prompt(
            business=business.to_dict(),
            num_angles=self.num_angles,
            prompt_version=PROMPT_VERSION,
        )

        provider_result = self.provider.synthesize(prompt)

        if not provider_result.success:
            raise SynthesisError(
                f"Provider call failed: {provider_result.error}"
            )

        result = self._build_result(business, provider_result)

        # Validate
        errors = result.validate()
        result.validation_errors = errors
        result.is_valid = len(errors) == 0

        return result

    def _build_result(
        self, business: BusinessProfile, pr: ProviderResult
    ) -> SynthesisResult:
        """Parse provider output into a SynthesisResult."""
        data = pr.parsed
        if not data:
            raise SynthesisError("Provider returned no parsed data")

        angles = self._parse_angles(data.get("angles", []))
        fingerprints = self._parse_fingerprints(
            data.get("communication_fingerprints", [])
        )

        # Assign fingerprints to angles (distribute evenly)
        for i, angle in enumerate(angles):
            if fingerprints:
                angle.communication_fingerprint = fingerprints[i % len(fingerprints)]

        metadata = ProviderMetadata(
            provider=pr.provider,
            model=pr.model,
            prompt_version=pr.prompt_version,
            input_provenance=pr.input_provenance,
            cost_usd=pr.cost_usd,
            output_tokens=pr.output_tokens,
            input_tokens=pr.input_tokens,
            latency_ms=pr.latency_ms,
        )

        return SynthesisResult(
            business_id=business.id,
            business_name=business.name,
            angles=angles,
            metadata=metadata,
        )

    def _parse_angles(self, raw_angles: list[dict[str, Any]]) -> list[MarketingAngle]:
        """Parse raw angle dicts into MarketingAngle objects."""
        angles: list[MarketingAngle] = []
        for i, raw in enumerate(raw_angles):
            cp_raw = raw.get("competitive_positioning", {})
            vs_list = [
                CompetitorAdvantage(
                    competitor=c.get("competitor", ""),
                    advantage=c.get("advantage", ""),
                    evidence=c.get("evidence", ""),
                )
                for c in cp_raw.get("vs_competitors", [])
            ]
            cp = CompetitivePosition(
                vs_competitors=vs_list,
                market_position=cp_raw.get("market_position", ""),
                moat=cp_raw.get("moat", ""),
            )

            evidence = [
                Evidence(
                    type=e.get("type", "market_data"),
                    source=e.get("source", ""),
                    confidence=float(e.get("confidence", 0.5)),
                    detail=e.get("detail", ""),
                )
                for e in raw.get("evidence", [])
            ]

            angle = MarketingAngle(
                id=raw.get("id", f"angle-{i + 1}"),
                title=raw.get("title", ""),
                description=raw.get("description", ""),
                target_segment=raw.get("target_segment", ""),
                differentiation=raw.get("differentiation", ""),
                competitive_positioning=cp,
                evidence=evidence,
                risk_level=raw.get("risk_level", "medium"),
                estimated_impact=raw.get("estimated_impact", ""),
            )
            angles.append(angle)
        return angles

    def _parse_fingerprints(
        self, raw_fps: list[dict[str, Any]]
    ) -> list[CommunicationFingerprint]:
        """Parse raw fingerprint dicts."""
        fps: list[CommunicationFingerprint] = []
        for raw in raw_fps:
            fp = CommunicationFingerprint(
                persona_type=raw.get("persona_type", "empathetic"),
                tone=raw.get("tone", ""),
                key_phrases=raw.get("key_phrases", []),
                channels=raw.get("channels", []),
                content_style=raw.get("content_style", ""),
            )
            fps.append(fp)
        return fps
