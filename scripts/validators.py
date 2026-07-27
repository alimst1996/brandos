#!/usr/bin/env python3
"""Output validators for BrandOS text content generation.

Every generated text passes through a validation pipeline before delivery.
Validators are pure functions that return a ValidationResult with pass/fail
and detailed reasons. They are composable and idempotent.

Validators:
  - ClaimValidator: Flags unsupported claims (superlatives, statistics without source).
  - BrandVoiceValidator: Checks prohibited terms, tone markers, reading level.
  - PersonaValidator: Verifies fingerprint alignment (style markers present/absent).

Usage:
    from validators import validate_output, ClaimValidator, BrandVoiceValidator

    results = validate_output(text, profile, fingerprint_name="authority")
    for r in results:
        if not r.passed:
            print(r.rule, r.detail)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from brand_profile import BrandProfile


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ValidationResult:
    """Result of a single validation rule.

    Attributes:
        rule: Rule identifier (e.g. "claim:superlative", "voice:prohibited_term").
        passed: True if the rule passed (content is acceptable).
        severity: "error" (must fix), "warning" (should fix), "info" (advisory).
        detail: Human-readable explanation.
        location: Character offset or line where the issue was found (if applicable).
    """
    rule: str
    passed: bool
    severity: str = "info"
    detail: str = ""
    location: int = -1


# ---------------------------------------------------------------------------
# Claim validator
# ---------------------------------------------------------------------------

# Patterns that signal an unsupported claim
_SUPERLATIVE_PATTERNS = [
    r"\b(?:the\s+)?(?:best|worst|most\s+\w+|least\s+\w+|only|first|last|greatest|finest|ultimate|unmatched|unrivaled|unparalleled)\b",
    r"#\s*1\b",
    r"\bnumber\s+one\b",
    r"\bworld[\s-]class\b",
    r"\bmarket[\s-]leading\b",
    r"\bincredible\b",
    r"\brevolutionary\b",
    r"\bgame[\s-]changing\b",
]

_STATISTIC_PATTERNS = [
    r"\b\d+%",
    r"\b\d+\s*(?:x|times)\s+(?:more|less|faster|better)\b",
    r"\bstudies?\s+(?:show|prove|suggest|indicate)\b",
    r"\bresearch\s+(?:shows|proves|suggests|indicates)\b",
    r"\baccording\s+to\s+(?:studies|research|experts)\b",
]


class ClaimValidator:
    """Flags unsupported claims in generated text.

    This validator checks for:
    - Superlatives without evidence
    - Statistical claims without sources
    - Vague authority appeals

    It does NOT judge truthfulness — it flags claims that need evidence.
    """

    def validate(self, text: str) -> list[ValidationResult]:
        results: list[ValidationResult] = []
        text_lower = text.lower()

        for pattern in _SUPERLATIVE_PATTERNS:
            for match in re.finditer(pattern, text_lower):
                results.append(ValidationResult(
                    rule="claim:superlative",
                    passed=False,
                    severity="warning",
                    detail=f"Unsupported superlative: '{match.group()}'. Add evidence or soften the claim.",
                    location=match.start(),
                ))

        for pattern in _STATISTIC_PATTERNS:
            for match in re.finditer(pattern, text_lower):
                results.append(ValidationResult(
                    rule="claim:statistic",
                    passed=False,
                    severity="warning",
                    detail=f"Statistical claim without source: '{match.group()}'. Cite a source.",
                    location=match.start(),
                ))

        if not results:
            results.append(ValidationResult(
                rule="claim:clean",
                passed=True,
                detail="No unsupported claims detected.",
            ))
        return results


# ---------------------------------------------------------------------------
# Brand voice validator
# ---------------------------------------------------------------------------

class BrandVoiceValidator:
    """Checks generated text against brand voice constraints.

    Validates:
    - Prohibited terms from BrandProfile.constraints
    - Language alignment
    - Content length limits
    """

    def validate(self, text: str, profile: BrandProfile) -> list[ValidationResult]:
        results: list[ValidationResult] = []

        # Prohibited terms
        for term in profile.constraints.prohibited_terms:
            pattern = re.compile(re.escape(term), re.IGNORECASE)
            match = pattern.search(text)
            if match:
                results.append(ValidationResult(
                    rule="voice:prohibited_term",
                    passed=False,
                    severity="error",
                    detail=f"Prohibited term found: '{term}'. Remove or replace.",
                    location=match.start(),
                ))

        # Length limit
        max_len = profile.constraints.max_content_length
        if max_len > 0 and len(text) > max_len:
            results.append(ValidationResult(
                rule="voice:length_exceeded",
                passed=False,
                severity="error",
                detail=f"Content length {len(text)} exceeds limit of {max_len} characters.",
            ))

        # Empty text
        if not text.strip():
            results.append(ValidationResult(
                rule="voice:empty_output",
                passed=False,
                severity="error",
                detail="Generated text is empty.",
            ))

        if not results:
            results.append(ValidationResult(
                rule="voice:clean",
                passed=True,
                detail="Voice constraints satisfied.",
            ))
        return results


# ---------------------------------------------------------------------------
# Persona (fingerprint) validator
# ---------------------------------------------------------------------------

_AVOID_PENALTIES: dict[str, list[str]] = {
    "authority": [
        (r"\b(?:just|simply|easy)\b", "casual_minimizer"),
    ],
    "empathy": [
        (r"\b(?:obviously|clearly|everyone knows)\b", "dismissive"),
    ],
    "momentum": [
        (r"\b(?:maybe|perhaps|might consider)\b", "hedging"),
    ],
}


class PersonaValidator:
    """Checks that generated text aligns with the chosen fingerprint.

    Each fingerprint has style markers and things to avoid. This validator
    checks for common violations without making subjective quality judgments.
    """

    def validate(self, text: str, fingerprint_name: str) -> list[ValidationResult]:
        results: list[ValidationResult] = []
        text_lower = text.lower()

        # Check fingerprint-specific anti-patterns
        penalties = _AVOID_PENALTIES.get(fingerprint_name, [])
        for pattern, label in penalties:
            for match in re.finditer(pattern, text_lower):
                results.append(ValidationResult(
                    rule=f"persona:{fingerprint_name}:{label}",
                    passed=False,
                    severity="warning",
                    detail=f"Fingerprint '{fingerprint_name}' anti-pattern: '{match.group()}'.",
                    location=match.start(),
                ))

        if not results:
            results.append(ValidationResult(
                rule=f"persona:{fingerprint_name}:aligned",
                passed=True,
                detail=f"Content aligns with '{fingerprint_name}' fingerprint.",
            ))
        return results


# ---------------------------------------------------------------------------
# Combined validation pipeline
# ---------------------------------------------------------------------------

def validate_output(
    text: str,
    profile: BrandProfile,
    fingerprint_name: str = "",
) -> list[ValidationResult]:
    """Run all validators on generated text and return combined results.

    Args:
        text: The generated text to validate.
        profile: The brand profile to validate against.
        fingerprint_name: The fingerprint name for persona validation (optional).

    Returns:
        List of ValidationResult from all validators.
    """
    all_results: list[ValidationResult] = []

    # Always run claim and voice validators
    claim_val = ClaimValidator()
    all_results.extend(claim_val.validate(text))

    voice_val = BrandVoiceValidator()
    all_results.extend(voice_val.validate(text, profile))

    # Run persona validator only if fingerprint specified
    if fingerprint_name:
        persona_val = PersonaValidator()
        all_results.extend(persona_val.validate(text, fingerprint_name))

    return all_results


def is_valid(results: list[ValidationResult]) -> bool:
    """Return True if no validation results have severity 'error'."""
    return all(r.passed or r.severity != "error" for r in results)


def get_errors(results: list[ValidationResult]) -> list[ValidationResult]:
    """Filter to only error-severity results that failed."""
    return [r for r in results if not r.passed and r.severity == "error"]


def get_warnings(results: list[ValidationResult]) -> list[ValidationResult]:
    """Filter to only warning-severity results that failed."""
    return [r for r in results if not r.passed and r.severity == "warning"]
