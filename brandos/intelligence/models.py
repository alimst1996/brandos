"""BIZ-005 Data models — structured JSON output for marketing angle synthesis.

All models are dataclass-based (stdlib only, no external dependencies).
JSON serialisation via asdict() / custom encoder.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class EvidenceType(str, Enum):
    MARKET_DATA = "market_data"
    CUSTOMER_INSIGHT = "customer_insight"
    COMPETITIVE_ANALYSIS = "competitive_analysis"
    BRAND_ASSET = "brand_asset"
    SOCIAL_PROOF = "social_proof"


class PersonaType(str, Enum):
    """MVP communication fingerprints — NOT fictional customer identities."""
    AUTHORITATIVE = "authoritative"
    EMPATHETIC = "empathetic"
    ASPIRATIONAL = "aspirational"
    DISRUPTIVE = "disruptive"
    MINIMALIST = "minimalist"
    STORYTELLER = "storyteller"
    EDUCATOR = "educator"
    COMMUNITY_BUILDER = "community_builder"
    PREMIUM_EXCLUSIVE = "premium_exclusive"
    PLAYFUL = "playful"


class ChannelType(str, Enum):
    INSTAGRAM = "instagram"
    LINKEDIN = "linkedin"
    TWITTER = "twitter"
    TIKTOK = "tiktok"
    EMAIL = "email"
    WEBSITE = "website"
    BLOG = "blog"
    YOUTUBE = "youtube"
    PODCAST = "podcast"
    PAID_ADS = "paid_ads"


# ---------------------------------------------------------------------------
# Core models
# ---------------------------------------------------------------------------


@dataclass
class BusinessProfile:
    """Input: business information to synthesise angles from."""
    id: str
    name: str
    industry: str
    description: str
    products: list[str] = field(default_factory=list)
    target_audience: str = ""
    unique_value_proposition: str = ""
    competitors: list[str] = field(default_factory=list)
    brand_voice: str = ""
    channels: list[str] = field(default_factory=list)
    pricing_tier: str = ""  # budget | mid | premium | luxury
    geographic_focus: str = ""
    stage: str = ""  # startup | growth | established | enterprise

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> BusinessProfile:
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class Evidence:
    """Supporting evidence for a marketing angle."""
    type: str  # EvidenceType value
    source: str
    confidence: float  # 0.0 – 1.0
    detail: str

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.type not in [e.value for e in EvidenceType]:
            errors.append(f"Invalid evidence type: {self.type}")
        if not 0.0 <= self.confidence <= 1.0:
            errors.append(f"Confidence must be 0.0-1.0, got {self.confidence}")
        if not self.source.strip():
            errors.append("Evidence source is required")
        if not self.detail.strip():
            errors.append("Evidence detail is required")
        return errors


@dataclass
class CompetitorAdvantage:
    """Positioning relative to a specific competitor."""
    competitor: str
    advantage: str
    evidence: str


@dataclass
class CompetitivePosition:
    """How this angle positions against the competitive landscape."""
    vs_competitors: list[CompetitorAdvantage] = field(default_factory=list)
    market_position: str = ""  # e.g. "premium alternative", "value leader"
    moat: str = ""  # e.g. "proprietary technology", "brand heritage"

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.vs_competitors:
            errors.append("At least one competitor comparison required")
        if not self.market_position.strip():
            errors.append("market_position is required")
        for i, comp in enumerate(self.vs_competitors):
            if not comp.competitor.strip():
                errors.append(f"vs_competitors[{i}].competitor is required")
            if not comp.advantage.strip():
                errors.append(f"vs_competitors[{i}].advantage is required")
        return errors


@dataclass
class CommunicationFingerprint:
    """MVP communication fingerprint — 3 per synthesis, NOT fictional identities."""
    persona_type: str  # PersonaType value
    tone: str
    key_phrases: list[str] = field(default_factory=list)
    channels: list[str] = field(default_factory=list)
    content_style: str = ""

    def validate(self) -> list[str]:
        errors: list[str] = []
        valid_types = [e.value for e in PersonaType]
        if self.persona_type not in valid_types:
            errors.append(f"Invalid persona_type: {self.persona_type}. Must be one of: {valid_types}")
        if not self.tone.strip():
            errors.append("tone is required")
        if not self.key_phrases:
            errors.append("At least one key_phrase required")
        if not self.channels:
            errors.append("At least one channel required")
        for ch in self.channels:
            if ch not in [c.value for c in ChannelType]:
                errors.append(f"Invalid channel: {ch}")
        return errors


@dataclass
class MarketingAngle:
    """A distinct marketing angle recommendation."""
    id: str
    title: str
    description: str
    target_segment: str
    differentiation: str
    competitive_positioning: CompetitivePosition
    evidence: list[Evidence] = field(default_factory=list)
    communication_fingerprint: CommunicationFingerprint | None = None
    risk_level: str = "medium"  # low | medium | high
    estimated_impact: str = ""  # high | medium | low

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.id.strip():
            errors.append("Angle id is required")
        if not self.title.strip():
            errors.append("Angle title is required")
        if not self.description.strip():
            errors.append("Angle description is required")
        if not self.target_segment.strip():
            errors.append("target_segment is required")
        if not self.differentiation.strip():
            errors.append("differentiation is required")
        if not self.evidence:
            errors.append("At least one evidence item required")
        for i, ev in enumerate(self.evidence):
            for err in ev.validate():
                errors.append(f"evidence[{i}]: {err}")
        for err in self.competitive_positioning.validate():
            errors.append(f"competitive_positioning: {err}")
        if self.communication_fingerprint:
            for err in self.communication_fingerprint.validate():
                errors.append(f"communication_fingerprint: {err}")
        return errors


@dataclass
class ProviderMetadata:
    """AI run provenance — required for every synthesis."""
    provider: str
    model: str
    prompt_version: str
    input_provenance: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    output_tokens: int = 0
    input_tokens: int = 0
    latency_ms: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.provider.strip():
            errors.append("provider is required")
        if not self.model.strip():
            errors.append("model is required")
        if not self.prompt_version.strip():
            errors.append("prompt_version is required")
        return errors


@dataclass
class SynthesisResult:
    """Top-level output: synthesised marketing angles for a business."""
    business_id: str
    business_name: str
    synthesis_timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    angles: list[MarketingAngle] = field(default_factory=list)
    metadata: ProviderMetadata | None = None
    validation_errors: list[str] = field(default_factory=list)
    is_valid: bool = True

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.business_id.strip():
            errors.append("business_id is required")
        if not self.business_name.strip():
            errors.append("business_name is required")
        if not self.angles:
            errors.append("At least one marketing angle required")
        if len(self.angles) < 2:
            errors.append("At least 2 distinct angles required for meaningful recommendation")
        # Check angle IDs are unique
        ids = [a.id for a in self.angles]
        if len(ids) != len(set(ids)):
            errors.append("Angle IDs must be unique")
        # Check angles are distinct (different titles)
        titles = [a.title.lower().strip() for a in self.angles]
        if len(titles) != len(set(titles)):
            errors.append("Angle titles must be distinct")
        for i, angle in enumerate(self.angles):
            for err in angle.validate():
                errors.append(f"angles[{i}] ({angle.id}): {err}")
        if self.metadata:
            for err in self.metadata.validate():
                errors.append(f"metadata: {err}")
        return errors

    def to_json(self, indent: int = 2) -> str:
        def _enum_handler(obj: Any) -> Any:
            if isinstance(obj, Enum):
                return obj.value
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
        return json.dumps(asdict(self), indent=indent, default=_enum_handler)

    @classmethod
    def from_json(cls, text: str) -> SynthesisResult:
        data = json.loads(text)
        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, d: dict[str, Any]) -> SynthesisResult:
        angles = []
        for a in d.get("angles", []):
            cp = CompetitivePosition(
                vs_competitors=[
                    CompetitorAdvantage(**c) for c in a.get("competitive_positioning", {}).get("vs_competitors", [])
                ],
                market_position=a.get("competitive_positioning", {}).get("market_position", ""),
                moat=a.get("competitive_positioning", {}).get("moat", ""),
            )
            ev = [Evidence(**e) for e in a.get("evidence", [])]
            cf_data = a.get("communication_fingerprint")
            cf = CommunicationFingerprint(**cf_data) if cf_data else None
            angles.append(MarketingAngle(
                id=a["id"],
                title=a["title"],
                description=a["description"],
                target_segment=a.get("target_segment", ""),
                differentiation=a.get("differentiation", ""),
                competitive_positioning=cp,
                evidence=ev,
                communication_fingerprint=cf,
                risk_level=a.get("risk_level", "medium"),
                estimated_impact=a.get("estimated_impact", ""),
            ))
        meta_data = d.get("metadata")
        metadata = None
        if meta_data:
            metadata = ProviderMetadata(**{
                k: v for k, v in meta_data.items()
                if k in ProviderMetadata.__dataclass_fields__
            })
        return cls(
            business_id=d["business_id"],
            business_name=d["business_name"],
            synthesis_timestamp=d.get("synthesis_timestamp", ""),
            angles=angles,
            metadata=metadata,
            validation_errors=d.get("validation_errors", []),
            is_valid=d.get("is_valid", True),
        )
