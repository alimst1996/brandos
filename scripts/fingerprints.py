#!/usr/bin/env python3
"""Three MVP communication fingerprints for BrandOS Intelligence.

A communication fingerprint is NOT a fictional customer identity — it is a
documented communication style that defines how content reaches the audience.
Each fingerprint pairs a communication intent with a delivery style.

MVP fingerprints (3):
  1. Authority  — thought leadership, industry expertise, credibility
  2. Empathy    — understanding pain points, supportive guidance, solution-oriented
  3. Momentum   — urgency, action-oriented, social proof, FOMO-aware

Usage:
    from scripts.fingerprints import Fingerprint, get_fingerprint, list_fingerprints

    fp = get_fingerprint("authority")
    system_prompt = fp.render_system_prompt(brand_profile)
    constraints = fp.get_constraints()
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from brand_profile import BrandProfile


@dataclass(frozen=True)
class Fingerprint:
    """A communication style fingerprint.

    Attributes:
        name: Unique identifier (e.g. "authority", "empathy", "momentum").
        label: Human-readable name (e.g. "Thought Leadership").
        description: What this fingerprint communicates and when to use it.
        intent: The communication goal (e.g. "establish credibility").
        style_markers: Concrete style instructions for the prompt.
        tone_adjustments: How the fingerprint modifies the brand voice tone.
        avoid: What this fingerprint must NOT do.
        example_opening: A sample opening sentence showing the style.
    """
    name: str
    label: str
    description: str
    intent: str
    style_markers: tuple[str, ...]
    tone_adjustments: tuple[str, ...]
    avoid: tuple[str, ...]
    example_opening: str = ""

    def render_system_prompt(self, profile: BrandProfile) -> str:
        """Render a model-ready system prompt combining this fingerprint with a brand profile."""
        lines = [
            f"You are writing content for {profile.identity.name}.",
            f"Industry: {profile.identity.industry}" if profile.identity.industry else "",
            f"Tagline: {profile.identity.tagline}" if profile.identity.tagline else "",
            "",
            f"Communication style: {self.label}",
            f"Intent: {self.intent}",
            "",
            "Brand voice:",
            f"  - Tone: {profile.voice.tone}",
            f"  - Personality: {', '.join(profile.voice.personality)}" if profile.voice.personality else "",
            f"  - Reading level: {profile.voice.reading_level}",
            f"  - Sentence style: {profile.voice.sentence_style}",
            "",
            "Fingerprint style guide:",
        ]
        for marker in self.style_markers:
            lines.append(f"  - {marker}")
        if self.tone_adjustments:
            lines.append("")
            lines.append("Tone adjustments for this fingerprint:")
            for adj in self.tone_adjustments:
                lines.append(f"  - {adj}")
        if self.avoid:
            lines.append("")
            lines.append("AVOID in this fingerprint:")
            for item in self.avoid:
                lines.append(f"  - {item}")
        if profile.constraints.prohibited_terms:
            lines.append("")
            lines.append("Prohibited terms (must never appear):")
            for term in profile.constraints.prohibited_terms:
                lines.append(f"  - {term}")
        if profile.values:
            lines.append("")
            lines.append(f"Brand values to reflect: {', '.join(profile.values)}")
        if profile.constraints.max_content_length > 0:
            lines.append("")
            lines.append(f"Maximum output length: {profile.constraints.max_content_length} characters")
        return "\n".join(line for line in lines if line is not None)

    def get_constraints(self) -> dict[str, Any]:
        """Return fingerprint constraints as a machine-readable dict."""
        return {
            "name": self.name,
            "intent": self.intent,
            "style_markers": list(self.style_markers),
            "tone_adjustments": list(self.tone_adjustments),
            "avoid": list(self.avoid),
        }


# ---------------------------------------------------------------------------
# The three MVP fingerprints
# ---------------------------------------------------------------------------

_AUTHORITY = Fingerprint(
    name="authority",
    label="Thought Leadership",
    description=(
        "Establishes the brand as a credible, knowledgeable leader in its field. "
        "Uses data, expertise signals, and industry context to build trust."
    ),
    intent="Establish credibility and industry expertise",
    style_markers=(
        "Use precise, factual language with evidence where available",
        "Reference industry trends, standards, or best practices",
        "Employ expert vocabulary appropriate to the domain (but avoid jargon overload)",
        "Structure arguments logically: claim → evidence → implication",
        "Use confident, declarative statements — avoid hedging",
    ),
    tone_adjustments=(
        "Slightly more formal than base brand tone",
        "Authoritative but not arrogant",
    ),
    avoid=(
        "Unsubstantiated superlatives ('the best', '#1', 'world-class' without proof)",
        "Casual slang or overly conversational filler",
        "Vague claims without supporting context",
    ),
    example_opening="In today's rapidly evolving landscape, brands that lead with clarity and evidence earn lasting trust.",
)

_EMPATHY = Fingerprint(
    name="empathy",
    label="Empathetic Guidance",
    description=(
        "Connects with the audience by acknowledging their challenges, pain points, "
        "and goals. Positions the brand as a supportive partner, not a vendor."
    ),
    intent="Build trust through understanding and shared problem-solving",
    style_markers=(
        "Lead with the reader's perspective and challenges",
        "Use 'you' and 'your' to direct content at the reader",
        "Acknowledge difficulties before offering solutions",
        "Use inclusive language ('we understand', 'together we can')",
        "Offer actionable, practical advice — not abstract platitudes",
    ),
    tone_adjustments=(
        "Warmer and more conversational than base brand tone",
        "Patient and reassuring, not preachy",
    ),
    avoid=(
        "Blaming the reader for their challenges",
        "Minimizing problems ('it's easy', 'just do X')",
        "Making it about the brand rather than the reader",
    ),
    example_opening="We know the frustration of investing time and resources into strategies that don't deliver.",
)

_MOMENTUM = Fingerprint(
    name="momentum",
    label="Action Momentum",
    description=(
        "Drives action through urgency, social proof, and clear next steps. "
        "Designed for conversion-oriented content without being manipulative."
    ),
    intent="Motivate immediate action through credibility-backed urgency",
    style_markers=(
        "Start with a compelling, benefit-driven hook",
        "Use active voice and action verbs throughout",
        "Include social proof signals where factual (user counts, testimonials, results)",
        "Create urgency with deadlines or limited-time framing (only when truthful)",
        "End every piece with a clear, specific call to action",
    ),
    tone_adjustments=(
        "More energetic and direct than base brand tone",
        "Confident and forward-looking",
    ),
    avoid=(
        "Manipulative pressure tactics (fake scarcity, countdown timers for evergreen offers)",
        "Exaggerated claims or inflated numbers",
        "Multiple competing CTAs — one clear next step per piece",
    ),
    example_opening="Stop settling for good enough. Here's how leading teams are getting ahead — and how you can too.",
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_FINGERPRINTS: dict[str, Fingerprint] = {
    fp.name: fp for fp in (_AUTHORITY, _EMPATHY, _MOMENTUM)
}


def list_fingerprints() -> list[str]:
    """Return available fingerprint names."""
    return list(_FINGERPRINTS.keys())


def get_fingerprint(name: str) -> Fingerprint:
    """Get a fingerprint by name. Raises KeyError if not found."""
    if name not in _FINGERPRINTS:
        available = ", ".join(sorted(_FINGERPRINTS.keys()))
        raise KeyError(f"Fingerprint '{name}' not found. Available: {available}")
    return _FINGERPRINTS[name]