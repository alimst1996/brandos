#!/usr/bin/env python3
"""
Brand Profile schema for BrandOS Intelligence.

Defines the structured data model for a brand's identity,
with evidence trails and confidence scores for each attribute.

Every attribute is backed by:
- evidence: list of source excerpts that support the value
- confidence: float 0-1 indicating extraction certainty
- source_url: where the evidence came from
- extraction_timestamp: when it was extracted

MVP constraint: communication fingerprints only, never fictional customer identities.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ToneCategory(str, Enum):
    """High-level tone categories for brand voice."""
    FORMAL = "formal"
    CASUAL = "casual"
    PLAYFUL = "playful"
    AUTHORITATIVE = "authoritative"
    EMPATHETIC = "empathetic"
    BOLD = "bold"
    MINIMALIST = "minimalist"
    LUXURY = "luxury"


class Industry(str, Enum):
    """Industry verticals for brand classification."""
    TECHNOLOGY = "technology"
    FASHION = "fashion"
    BEAUTY = "beauty"
    FOOD_BEVERAGE = "food_beverage"
    FINANCE = "finance"
    HEALTH = "health"
    EDUCATION = "education"
    LUXURY = "luxury"
    ECOMMERCE = "ecommerce"
    MEDIA = "media"
    OTHER = "other"


# ---------------------------------------------------------------------------
# Evidence model
# ---------------------------------------------------------------------------

@dataclass
class Evidence:
    """A single piece of evidence supporting a brand attribute."""
    value: str
    source_url: str
    excerpt: str  # The actual text excerpt from the source
    confidence: float  # 0-1
    extraction_timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Evidence:
        return cls(**data)


@dataclass
class AttributedValue:
    """A brand attribute value backed by evidence."""
    value: str
    evidence: list[Evidence] = field(default_factory=list)
    overall_confidence: float = 0.0  # Computed from evidence

    def compute_confidence(self) -> float:
        """Compute overall confidence from evidence."""
        if not self.evidence:
            return 0.0
        # Weighted average: more evidence = higher confidence
        confidences = [e.confidence for e in self.evidence]
        base = sum(confidences) / len(confidences)
        # Bonus for multiple sources
        source_bonus = min(0.1 * (len(set(e.source_url for e in self.evidence)) - 1), 0.2)
        self.overall_confidence = min(base + source_bonus, 1.0)
        return self.overall_confidence

    def to_dict(self) -> dict[str, Any]:
        self.compute_confidence()
        return {
            "value": self.value,
            "evidence": [e.to_dict() for e in self.evidence],
            "overall_confidence": self.overall_confidence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AttributedValue:
        evidence = [Evidence.from_dict(e) for e in data.get("evidence", [])]
        return cls(
            value=data["value"],
            evidence=evidence,
            overall_confidence=data.get("overall_confidence", 0.0),
        )


# ---------------------------------------------------------------------------
# Brand Profile
# ---------------------------------------------------------------------------

@dataclass
class BrandProfile:
    """
    Complete brand identity profile.

    Every field is an AttributedValue with evidence and confidence.
    This ensures no brand attribute is ever asserted without backing data.
    """
    # Core identity
    brand_name: AttributedValue = field(default_factory=lambda: AttributedValue(value=""))
    industry: AttributedValue = field(default_factory=lambda: AttributedValue(value=""))
    tagline: AttributedValue = field(default_factory=lambda: AttributedValue(value=""))
    description: AttributedValue = field(default_factory=lambda: AttributedValue(value=""))

    # Voice characteristics
    primary_tone: AttributedValue = field(default_factory=lambda: AttributedValue(value=""))
    secondary_tones: list[AttributedValue] = field(default_factory=list)
    vocabulary_level: AttributedValue = field(default_factory=lambda: AttributedValue(value=""))
    sentence_style: AttributedValue = field(default_factory=lambda: AttributedValue(value=""))

    # Brand values
    core_values: list[AttributedValue] = field(default_factory=list)
    brand_personality: list[AttributedValue] = field(default_factory=list)

    # Target audience
    target_audience: AttributedValue = field(default_factory=lambda: AttributedValue(value=""))
    audience_segments: list[AttributedValue] = field(default_factory=list)

    # Unique selling proposition
    usp: AttributedValue = field(default_factory=lambda: AttributedValue(value=""))

    # Content patterns
    common_phrases: list[AttributedValue] = field(default_factory=list)
    avoided_phrases: list[AttributedValue] = field(default_factory=list)
    hashtag_style: AttributedValue = field(default_factory=lambda: AttributedValue(value=""))

    # Metadata
    extraction_timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    source_urls: list[str] = field(default_factory=list)
    total_evidence_count: int = 0
    overall_confidence: float = 0.0

    def compute_overall_confidence(self) -> float:
        """Compute overall profile confidence from all attributes."""
        confidences = []

        # Single-value fields
        for attr in [self.brand_name, self.industry, self.tagline,
                     self.description, self.primary_tone, self.vocabulary_level,
                     self.sentence_style, self.target_audience, self.usp,
                     self.hashtag_style]:
            conf = attr.compute_confidence()
            if conf > 0:
                confidences.append(conf)

        # List fields
        for attr_list in [self.secondary_tones, self.core_values,
                          self.brand_personality, self.audience_segments,
                          self.common_phrases, self.avoided_phrases]:
            for attr in attr_list:
                conf = attr.compute_confidence()
                if conf > 0:
                    confidences.append(conf)

        if not confidences:
            return 0.0

        self.overall_confidence = sum(confidences) / len(confidences)
        return self.overall_confidence

    def count_evidence(self) -> int:
        """Count total evidence items across all attributes."""
        count = 0
        for attr in [self.brand_name, self.industry, self.tagline,
                     self.description, self.primary_tone, self.vocabulary_level,
                     self.sentence_style, self.target_audience, self.usp,
                     self.hashtag_style]:
            count += len(attr.evidence)

        for attr_list in [self.secondary_tones, self.core_values,
                          self.brand_personality, self.audience_segments,
                          self.common_phrases, self.avoided_phrases]:
            for attr in attr_list:
                count += len(attr.evidence)

        self.total_evidence_count = count
        return count

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        self.compute_overall_confidence()
        self.count_evidence()
        return {
            "brand_name": self.brand_name.to_dict(),
            "industry": self.industry.to_dict(),
            "tagline": self.tagline.to_dict(),
            "description": self.description.to_dict(),
            "primary_tone": self.primary_tone.to_dict(),
            "secondary_tones": [t.to_dict() for t in self.secondary_tones],
            "vocabulary_level": self.vocabulary_level.to_dict(),
            "sentence_style": self.sentence_style.to_dict(),
            "core_values": [v.to_dict() for v in self.core_values],
            "brand_personality": [p.to_dict() for p in self.brand_personality],
            "target_audience": self.target_audience.to_dict(),
            "audience_segments": [s.to_dict() for s in self.audience_segments],
            "usp": self.usp.to_dict(),
            "common_phrases": [p.to_dict() for p in self.common_phrases],
            "avoided_phrases": [p.to_dict() for p in self.avoided_phrases],
            "hashtag_style": self.hashtag_style.to_dict(),
            "extraction_timestamp": self.extraction_timestamp,
            "source_urls": self.source_urls,
            "total_evidence_count": self.total_evidence_count,
            "overall_confidence": self.overall_confidence,
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BrandProfile:
        """Deserialize from dictionary."""
        profile = cls(
            brand_name=AttributedValue.from_dict(data.get("brand_name", {"value": ""})),
            industry=AttributedValue.from_dict(data.get("industry", {"value": ""})),
            tagline=AttributedValue.from_dict(data.get("tagline", {"value": ""})),
            description=AttributedValue.from_dict(data.get("description", {"value": ""})),
            primary_tone=AttributedValue.from_dict(data.get("primary_tone", {"value": ""})),
            secondary_tones=[AttributedValue.from_dict(t) for t in data.get("secondary_tones", [])],
            vocabulary_level=AttributedValue.from_dict(data.get("vocabulary_level", {"value": ""})),
            sentence_style=AttributedValue.from_dict(data.get("sentence_style", {"value": ""})),
            core_values=[AttributedValue.from_dict(v) for v in data.get("core_values", [])],
            brand_personality=[AttributedValue.from_dict(p) for p in data.get("brand_personality", [])],
            target_audience=AttributedValue.from_dict(data.get("target_audience", {"value": ""})),
            audience_segments=[AttributedValue.from_dict(s) for s in data.get("audience_segments", [])],
            usp=AttributedValue.from_dict(data.get("usp", {"value": ""})),
            common_phrases=[AttributedValue.from_dict(p) for p in data.get("common_phrases", [])],
            avoided_phrases=[AttributedValue.from_dict(p) for p in data.get("avoided_phrases", [])],
            hashtag_style=AttributedValue.from_dict(data.get("hashtag_style", {"value": ""})),
            extraction_timestamp=data.get("extraction_timestamp", ""),
            source_urls=data.get("source_urls", []),
            total_evidence_count=data.get("total_evidence_count", 0),
            overall_confidence=data.get("overall_confidence", 0.0),
        )
        return profile

    @classmethod
    def from_json(cls, json_str: str) -> BrandProfile:
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(json_str))

    @classmethod
    def load(cls, path: str | Path) -> BrandProfile:
        """Load from a JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

    def save(self, path: str | Path) -> None:
        """Save to a JSON file."""
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json())

    def summary(self) -> dict[str, Any]:
        """Return a human-readable summary."""
        self.compute_overall_confidence()
        self.count_evidence()
        return {
            "brand_name": self.brand_name.value,
            "industry": self.industry.value,
            "primary_tone": self.primary_tone.value,
            "overall_confidence": round(self.overall_confidence, 3),
            "total_evidence_count": self.total_evidence_count,
            "source_count": len(self.source_urls),
            "core_values_count": len(self.core_values),
            "extraction_timestamp": self.extraction_timestamp,
        }
