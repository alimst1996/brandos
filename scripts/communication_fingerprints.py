#!/usr/bin/env python3
"""
Communication Fingerprints for BrandOS Intelligence.

MVP defines exactly 3 fingerprints — communication style patterns,
never fictional customer identities. Each fingerprint captures a
distinct voice archetype that brands can align with.

MVP constraint: Do not activate the remaining nine personas or
advanced prompt experimentation.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class FingerprintType(str, Enum):
    """The 3 MVP communication fingerprints."""
    AUTHORITATIVE = "authoritative"
    EMPATHETIC = "empathetic"
    BOLD = "bold"


@dataclass
class VocabularyProfile:
    """Vocabulary characteristics for a fingerprint."""
    preferred_words: list[str] = field(default_factory=list)
    avoided_words: list[str] = field(default_factory=list)
    sentence_length: str = "medium"  # short, medium, long
    formality_level: str = "neutral"  # casual, neutral, formal
    use_questions: bool = False
    use_exclamations: bool = False
    use_imperatives: bool = False


@dataclass
class ToneMarkers:
    """Tonal characteristics for content generation."""
    confidence_level: str = "moderate"  # low, moderate, high
    emotional_temperature: str = "neutral"  # cold, neutral, warm, hot
    urgency_level: str = "normal"  # low, normal, high
    authority_level: str = "moderate"  # low, moderate, high
    empathy_level: str = "moderate"  # low, moderate, high
    boldness_level: str = "moderate"  # low, moderate, high


@dataclass
class StructuralPatterns:
    """Content structure preferences."""
    paragraph_style: str = "standard"  # standard, short, varied
    use_bullet_points: bool = False
    use_numbered_lists: bool = False
    use_headers: bool = False
    call_to_action_style: str = "subtle"  # subtle, direct, bold
    opening_hook_style: str = "standard"  # question, statement, story, standard


@dataclass
class CommunicationFingerprint:
    """
    A communication style fingerprint.

    This is NOT a fictional customer identity. It is a set of
    linguistic and tonal patterns that describe how a brand communicates.
    """
    fingerprint_type: FingerprintType
    name: str
    description: str

    # Core characteristics
    vocabulary: VocabularyProfile = field(default_factory=VocabularyProfile)
    tone: ToneMarkers = field(default_factory=ToneMarkers)
    structure: StructuralPatterns = field(default_factory=StructuralPatterns)

    # Content generation guidelines
    do_guidelines: list[str] = field(default_factory=list)
    dont_guidelines: list[str] = field(default_factory=list)

    # Example phrases (real-world style examples, not fabricated)
    example_phrases: list[str] = field(default_factory=list)

    # Metadata
    version: str = "1.0.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "fingerprint_type": self.fingerprint_type.value,
            "name": self.name,
            "description": self.description,
            "vocabulary": asdict(self.vocabulary),
            "tone": asdict(self.tone),
            "structure": asdict(self.structure),
            "do_guidelines": self.do_guidelines,
            "dont_guidelines": self.dont_guidelines,
            "example_phrases": self.example_phrases,
            "version": self.version,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CommunicationFingerprint:
        return cls(
            fingerprint_type=FingerprintType(data["fingerprint_type"]),
            name=data["name"],
            description=data["description"],
            vocabulary=VocabularyProfile(**data.get("vocabulary", {})),
            tone=ToneMarkers(**data.get("tone", {})),
            structure=StructuralPatterns(**data.get("structure", {})),
            do_guidelines=data.get("do_guidelines", []),
            dont_guidelines=data.get("dont_guidelines", []),
            example_phrases=data.get("example_phrases", []),
            version=data.get("version", "1.0.0"),
        )

    @classmethod
    def from_json(cls, json_str: str) -> CommunicationFingerprint:
        return cls.from_dict(json.loads(json_str))


# ---------------------------------------------------------------------------
# The 3 MVP fingerprints (hardcoded, version-controlled)
# ---------------------------------------------------------------------------

AUTHORITATIVE = CommunicationFingerprint(
    fingerprint_type=FingerprintType.AUTHORITATIVE,
    name="Authoritative",
    description=(
        "Projects expertise and confidence. Uses data, credentials, and "
        "established knowledge to build trust. Speaks with certainty and "
        "positions the brand as a domain leader."
    ),
    vocabulary=VocabularyProfile(
        preferred_words=[
            "proven", "established", "research shows", "data indicates",
            "expert", "industry-leading", "validated", "certified",
            "benchmark", "standard", "definitive", "authoritative",
        ],
        avoided_words=[
            "maybe", "might", "possibly", "I think", "sort of",
            "kind of", "hopefully", "guess", "pretty much",
        ],
        sentence_length="medium",
        formality_level="formal",
        use_questions=False,
        use_exclamations=False,
        use_imperatives=True,
    ),
    tone=ToneMarkers(
        confidence_level="high",
        emotional_temperature="cold",
        urgency_level="normal",
        authority_level="high",
        empathy_level="low",
        boldness_level="moderate",
    ),
    structure=StructuralPatterns(
        paragraph_style="standard",
        use_bullet_points=True,
        use_numbered_lists=True,
        use_headers=True,
        call_to_action_style="direct",
        opening_hook_style="statement",
    ),
    do_guidelines=[
        "Lead with data or credentials",
        "Use definitive language (is, will, does)",
        "Reference established standards or research",
        "Structure content with clear hierarchy",
        "Provide evidence for every claim",
    ],
    dont_guidelines=[
        "Use hedging language (might, maybe, perhaps)",
        "Make unsupported claims",
        "Use slang or casual expressions",
        "Overuse exclamation marks",
        "Appear uncertain or apologetic",
    ],
    example_phrases=[
        "Research demonstrates that...",
        "The industry standard for...",
        "Our proven methodology...",
        "Data from [source] confirms...",
        "As established leaders in...",
    ],
)

EMPATHETIC = CommunicationFingerprint(
    fingerprint_type=FingerprintType.EMPATHETIC,
    name="Empathetic",
    description=(
        "Creates emotional connection through understanding and warmth. "
        "Acknowledges feelings, validates experiences, and builds trust "
        "through relatability and care."
    ),
    vocabulary=VocabularyProfile(
        preferred_words=[
            "understand", "feel", "care", "support", "together",
            "community", "journey", "wellbeing", "comfort", "nurture",
            "gentle", "safe", "belong", "welcome",
        ],
        avoided_words=[
            "obviously", "just", "simply", "easy", "everyone knows",
            "clearly", "should have", "you need to",
        ],
        sentence_length="medium",
        formality_level="casual",
        use_questions=True,
        use_exclamations=True,
        use_imperatives=False,
    ),
    tone=ToneMarkers(
        confidence_level="moderate",
        emotional_temperature="warm",
        urgency_level="low",
        authority_level="low",
        empathy_level="high",
        boldness_level="low",
    ),
    structure=StructuralPatterns(
        paragraph_style="short",
        use_bullet_points=False,
        use_numbered_lists=False,
        use_headers=False,
        call_to_action_style="subtle",
        opening_hook_style="question",
    ),
    do_guidelines=[
        "Acknowledge the reader's feelings or situation",
        "Use inclusive language (we, us, together)",
        "Share relatable experiences",
        "Validate emotions before offering solutions",
        "Use warm, conversational tone",
    ],
    dont_guidelines=[
        "Dismiss or minimize feelings",
        "Use cold, clinical language",
        "Push hard on sales or urgency",
        "Talk down to the audience",
        "Use jargon or technical terms unnecessarily",
    ],
    example_phrases=[
        "We understand how it feels when...",
        "You're not alone in this...",
        "Let's take this journey together...",
        "It's okay to feel...",
        "We're here for you, every step...",
    ],
)

BOLD = CommunicationFingerprint(
    fingerprint_type=FingerprintType.BOLD,
    name="Bold",
    description=(
        "Provocative and innovative. Challenges conventions, takes strong "
        "positions, and uses memorable, punchy language. Designed for brands "
        "that want to stand out and disrupt."
    ),
    vocabulary=VocabularyProfile(
        preferred_words=[
            "revolutionary", "breakthrough", "disrupt", "reimagine",
            "defy", "unleash", "transform", "challenge", "pioneer",
            "fearless", "unapologetic", "game-changing",
        ],
        avoided_words=[
            "traditional", "conventional", "standard", "typical",
            "normal", "expected", "safe", "gradual", "conservative",
        ],
        sentence_length="short",
        formality_level="casual",
        use_questions=True,
        use_exclamations=True,
        use_imperatives=True,
    ),
    tone=ToneMarkers(
        confidence_level="high",
        emotional_temperature="hot",
        urgency_level="high",
        authority_level="moderate",
        empathy_level="low",
        boldness_level="high",
    ),
    structure=StructuralPatterns(
        paragraph_style="short",
        use_bullet_points=True,
        use_numbered_lists=False,
        use_headers=True,
        call_to_action_style="bold",
        opening_hook_style="statement",
    ),
    do_guidelines=[
        "Make strong, memorable statements",
        "Challenge conventional thinking",
        "Use punchy, concise language",
        "Take a clear stance on issues",
        "Create urgency and excitement",
    ],
    dont_guidelines=[
        "Hedge or qualify statements",
        "Use long, complex sentences",
        "Follow the crowd or play it safe",
        "Be generic or forgettable",
        "Overuse exclamation marks (one per paragraph max)",
    ],
    example_phrases=[
        "Stop settling for...",
        "The future belongs to...",
        "We didn't follow the rules. We rewrote them.",
        "This changes everything.",
        "Dare to...",
    ],
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_FINGERPRINT_REGISTRY: dict[FingerprintType, CommunicationFingerprint] = {
    FingerprintType.AUTHORITATIVE: AUTHORITATIVE,
    FingerprintType.EMPATHETIC: EMPATHETIC,
    FingerprintType.BOLD: BOLD,
}


def get_fingerprint(fp_type: FingerprintType) -> CommunicationFingerprint:
    """Get a fingerprint by type."""
    if fp_type not in _FINGERPRINT_REGISTRY:
        raise ValueError(f"Unknown fingerprint type: {fp_type}")
    return _FINGERPRINT_REGISTRY[fp_type]


def get_all_fingerprints() -> dict[FingerprintType, CommunicationFingerprint]:
    """Get all MVP fingerprints."""
    return dict(_FINGERPRINT_REGISTRY)


def list_fingerprint_types() -> list[str]:
    """List all available fingerprint type names."""
    return [fp.value for fp in FingerprintType]
