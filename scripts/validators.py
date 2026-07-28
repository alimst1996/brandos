#!/usr/bin/env python3
"""
Validators for BrandOS Intelligence.

Three validators ensure generated content meets quality bars:
- ClaimValidator: catches unsupported statistics, superlatives, and factual claims
- BrandValidator: enforces brand voice consistency (name, values, avoided phrases)
- PersonaValidator: checks communication fingerprint alignment (vocabulary, tone, formality)

Every validation returns a ValidationResult with pass/fail, errors, warnings,
and a details dict for programmatic inspection.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from brand_profile import AttributedValue, BrandProfile
from communication_fingerprints import CommunicationFingerprint


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    """Outcome of a single validation pass."""
    passed: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def fail(self, error: str) -> None:
        self.passed = False
        self.errors.append(error)

    def warn(self, warning: str) -> None:
        self.warnings.append(warning)


# ---------------------------------------------------------------------------
# Claim Validator
# ---------------------------------------------------------------------------

# Patterns that look like factual claims / statistics
_STAT_PATTERN = re.compile(
    r"\b\d+\.?\d*\s*%"              # "95%", "3.5%"
    r"|\b\d+\s*(?:out of|in)\s*\d+" # "9 out of 10"
    r"|\b#\d+\b"                     # "#1 brand"
)

_SUPERLATIVE_PATTERN = re.compile(
    r"\b(?:best|greatest|most popular|leading|number one|top[- ]rated|"
    r"unmatched|unrivaled|world[- ]class|industry[- ]leading)\b",
    re.IGNORECASE,
)


class ClaimValidator:
    """
    Validates that factual claims and superlatives in generated text
    are backed by source evidence. Prevents hallucinated statistics.
    """

    def validate(
        self,
        text: str,
        source_evidence: list[str] | None = None,
    ) -> ValidationResult:
        result = ValidationResult()
        evidence_lower = " ".join(e.lower() for e in (source_evidence or []))

        # Check for unsupported statistics
        for match in _STAT_PATTERN.finditer(text):
            stat = match.group(0)
            # A stat is supported if a similar numeric expression appears in evidence
            stat_core = re.search(r"\d+\.?\d*", stat)
            if stat_core and stat_core.group(0) not in evidence_lower:
                result.fail(
                    f"Unsupported statistic: '{stat}' not found in source evidence."
                )

        # Check for superlatives without evidence
        for match in _SUPERLATIVE_PATTERN.finditer(text):
            word = match.group(0).lower()
            if not evidence_lower:
                result.warn(
                    f"Superlative '{word}' used without any source evidence."
                )
            elif word not in evidence_lower:
                result.warn(
                    f"Superlative '{word}' not directly supported by source evidence."
                )

        return result


# ---------------------------------------------------------------------------
# Brand Validator
# ---------------------------------------------------------------------------

class BrandValidator:
    """
    Validates that generated content aligns with a BrandProfile:
    - Brand name is mentioned
    - Avoided phrases are not present
    - Core values are reflected (warning if missing)
    """

    def validate(self, text: str, brand: BrandProfile) -> ValidationResult:
        result = ValidationResult()
        text_lower = text.lower()

        # Check brand name
        brand_name = brand.brand_name.value
        if brand_name:
            name_present = brand_name.lower() in text_lower
            result.details["brand_name_present"] = name_present
            if not name_present:
                result.warn(f"Brand name '{brand_name}' not found in content.")
        else:
            result.details["brand_name_present"] = False

        # Check avoided phrases
        for avoided in brand.avoided_phrases:
            phrase = avoided.value.lower()
            if phrase and phrase in text_lower:
                result.fail(
                    f"Avoided phrase '{avoided.value}' found in content."
                )

        # Check core values (informational warning only)
        if brand.core_values:
            values_found = []
            values_missing = []
            for val in brand.core_values:
                v = val.value.lower()
                if v and v in text_lower:
                    values_found.append(val.value)
                else:
                    values_missing.append(val.value)
            result.details["values_found"] = values_found
            result.details["values_missing"] = values_missing

        return result


# ---------------------------------------------------------------------------
# Persona Validator
# ---------------------------------------------------------------------------

class PersonaValidator:
    """
    Validates that generated content matches a CommunicationFingerprint:
    - Preferred vocabulary words are used
    - Avoided vocabulary words are not used
    - Formality level is respected
    """

    def validate(
        self,
        text: str,
        fingerprint: CommunicationFingerprint,
    ) -> ValidationResult:
        result = ValidationResult()
        text_lower = text.lower()
        words_in_text = set(re.findall(r"\b[a-z]+\b", text_lower))

        # Check preferred words
        preferred = fingerprint.vocabulary.preferred_words
        preferred_found = [w for w in preferred if w.lower() in words_in_text]
        result.details["preferred_words_found"] = preferred_found

        # Check avoided words — these are errors
        avoided = fingerprint.vocabulary.avoided_words
        avoided_found = [w for w in avoided if w.lower() in words_in_text]
        for w in avoided_found:
            result.fail(f"Avoided word '{w}' found (fingerprint: {fingerprint.name}).")

        # Check formality — if fingerprint is formal, casual signal words fail
        formality = fingerprint.vocabulary.formality_level
        if formality == "formal":
            casual_signals = {
                "hey", "awesome", "cool", "yeah", "gonna", "wanna",
                "gotta", "totally", "literally", "basically",
            }
            casual_found = words_in_text & casual_signals
            if casual_found:
                result.fail(
                    f"Casual language {sorted(casual_found)} found in formal fingerprint."
                )

        # If no preferred words found at all, warn (but don't fail)
        if preferred and not preferred_found:
            result.warn(
                f"No preferred vocabulary words from {fingerprint.name} found in content."
            )

        return result
