#!/usr/bin/env python3
"""Brand Profile model for BrandOS Intelligence.

Represents a brand's identity, voice, values, and communication constraints.
Profiles drive all content generation — every prompt contract and communication
fingerprint references a brand profile to ensure output is brand-aligned.

Usage:
    from scripts.brand_profile import BrandProfile, BrandVoice, BrandIdentity

    profile = BrandProfile(
        identity=BrandIdentity(name="Acme Corp", industry="SaaS"),
        voice=BrandVoice(tone="professional", personality=["innovative", "trustworthy"]),
        values=["reliability", "simplicity"],
        constraints=BrandConstraints(prohibited_terms=["cheap", "discount"]),
    )
    serialized = profile.to_dict()
    restored = BrandProfile.from_dict(serialized)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass(frozen=True)
class BrandIdentity:
    """Core brand identification fields."""
    name: str
    industry: str = ""
    tagline: str = ""
    description: str = ""
    website: str = ""

    def validate(self) -> list[str]:
        """Return a list of validation errors (empty = valid)."""
        errors = []
        if not self.name or not self.name.strip():
            errors.append("Brand name is required")
        return errors


@dataclass(frozen=True)
class BrandVoice:
    """How the brand communicates.

    Attributes:
        tone: Overall tone (e.g. "professional", "playful", "authoritative").
        personality: List of personality traits (e.g. ["innovative", "warm"]).
        reading_level: Target reading level (e.g. "general", "expert", "grade8").
        sentence_style: Preferred sentence structure (e.g. "concise", "flowing").
    """
    tone: str = "professional"
    personality: tuple[str, ...] = ()
    reading_level: str = "general"
    sentence_style: str = "concise"

    def validate(self) -> list[str]:
        errors = []
        if not self.tone or not self.tone.strip():
            errors.append("Voice tone is required")
        return errors


@dataclass(frozen=True)
class BrandConstraints:
    """Hard boundaries for generated content.

    Attributes:
        prohibited_terms: Words/phrases that must NEVER appear in output.
        required_disclaimers: Disclaimers to append when certain topics arise.
        max_content_length: Maximum character length for generated content (0 = no limit).
        language: ISO 639-1 language code (e.g. "en", "fa").
    """
    prohibited_terms: tuple[str, ...] = ()
    required_disclaimers: tuple[str, ...] = ()
    max_content_length: int = 0
    language: str = "en"

    def validate(self) -> list[str]:
        errors = []
        if self.max_content_length < 0:
            errors.append("max_content_length must be >= 0")
        return errors


@dataclass
class BrandProfile:
    """Complete brand profile for content generation.

    A BrandProfile is the single source of truth for how a brand communicates.
    All content generation starts from a profile.

    Attributes:
        identity: Core brand identification (name, industry, tagline).
        voice: Communication style (tone, personality, reading level).
        values: Core brand values (e.g. ["innovation", "trust"]).
        constraints: Hard boundaries (prohibited terms, length limits).
        metadata: Extensible key-value store for brand-specific data.
    """
    identity: BrandIdentity
    voice: BrandVoice = field(default_factory=BrandVoice)
    values: list[str] = field(default_factory=list)
    constraints: BrandConstraints = field(default_factory=BrandConstraints)
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> list[str]:
        """Return all validation errors across sub-models."""
        errors = []
        errors.extend(self.identity.validate())
        errors.extend(self.voice.validate())
        errors.extend(self.constraints.validate())
        return errors

    def is_valid(self) -> bool:
        return len(self.validate()) == 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict (frozen dataclasses included)."""
        return {
            "identity": asdict(self.identity),
            "voice": asdict(self.voice),
            "values": list(self.values),
            "constraints": asdict(self.constraints),
            "metadata": dict(self.metadata),
        }

    def to_json(self, **kwargs: Any) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), **kwargs)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BrandProfile:
        """Deserialize from a dict (inverse of to_dict)."""
        identity = BrandIdentity(**data.get("identity", {}))
        voice_data = data.get("voice", {})
        # tuple-ify list fields from JSON
        if "personality" in voice_data and isinstance(voice_data["personality"], list):
            voice_data["personality"] = tuple(voice_data["personality"])
        voice = BrandVoice(**voice_data)
        constraints_data = data.get("constraints", {})
        for key in ("prohibited_terms", "required_disclaimers"):
            if key in constraints_data and isinstance(constraints_data[key], list):
                constraints_data[key] = tuple(constraints_data[key])
        constraints = BrandConstraints(**constraints_data)
        return cls(
            identity=identity,
            voice=voice,
            values=data.get("values", []),
            constraints=constraints,
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def from_json(cls, json_str: str) -> BrandProfile:
        """Deserialize from a JSON string."""
        return cls.from_dict(json.loads(json_str))
