#!/usr/bin/env python3
"""Prompt contracts for BrandOS text content generation.

A prompt contract is a versioned, parameterized template that produces the
final user-prompt sent to an LLM. Contracts are versioned (semver-style
integers) so that production runs can be replayed and audited.

Every AI run records: provider, model, prompt_version, input provenance,
cost, output, and validation result. The prompt version comes from here.

Usage:
    from scripts.prompt_contracts import PromptContract, get_contract, list_contracts

    contract = get_contract("product-description")
    rendered = contract.render(
        product_name="Midnight Noir",
        product_category="luxury perfume",
        key_notes=["oud", "amber", "black rose"],
        fingerprint_name="authority",
    )
"""
from __future__ import annotations

import json
import re
import textwrap
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PromptContract:
    """A versioned prompt template.

    Attributes:
        name: Unique identifier (e.g. "product-description").
        version: Integer version. Increment when the template changes in a way
                 that affects output (bumps invalidate cached/replayed outputs).
        description: Human-readable description of what this contract produces.
        template: The prompt template with {placeholder} variables.
        required_vars: Variable names that MUST be provided at render time.
        optional_vars: Variable names that MAY be provided (with defaults).
        defaults: Default values for optional variables.
        output_format: Expected output format ("text", "json", "markdown").
        max_output_tokens: Recommended max tokens for the LLM response.
        tags: Freeform labels for filtering (e.g. ["marketing", "product"]).
    """
    name: str
    version: int
    description: str
    template: str
    required_vars: tuple[str, ...] = ()
    optional_vars: tuple[str, ...] = ()
    defaults: dict[str, Any] = field(default_factory=dict)
    output_format: str = "text"
    max_output_tokens: int = 500
    tags: tuple[str, ...] = ()

    def render(self, **kwargs: Any) -> str:
        """Render the template with provided variables.

        Raises ValueError if a required variable is missing or if unknown
        variables are passed.
        """
        # Merge optional defaults
        merged = dict(self.defaults)
        merged.update(kwargs)

        # Check required vars
        missing = [v for v in self.required_vars if v not in merged]
        if missing:
            raise ValueError(f"Missing required variables: {', '.join(missing)}")

        # Check for unknown vars (prevent silent typos)
        known = set(self.required_vars) | set(self.optional_vars)
        unknown = set(merged.keys()) - known
        if unknown:
            raise ValueError(f"Unknown variables: {', '.join(sorted(unknown))}")

        return self.template.format(**merged)

    def get_placeholders(self) -> list[str]:
        """Extract all {placeholder} names from the template."""
        return re.findall(r"\{(\w+)\}", self.template)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "template": self.template,
            "required_vars": list(self.required_vars),
            "optional_vars": list(self.optional_vars),
            "defaults": self.defaults,
            "output_format": self.output_format,
            "max_output_tokens": self.max_output_tokens,
            "tags": list(self.tags),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PromptContract:
        return cls(
            name=data["name"],
            version=data["version"],
            description=data.get("description", ""),
            template=data["template"],
            required_vars=tuple(data.get("required_vars", [])),
            optional_vars=tuple(data.get("optional_vars", [])),
            defaults=data.get("defaults", {}),
            output_format=data.get("output_format", "text"),
            max_output_tokens=data.get("max_output_tokens", 500),
            tags=tuple(data.get("tags", [])),
        )


# ---------------------------------------------------------------------------
# Built-in contracts
# ---------------------------------------------------------------------------

_PRODUCT_DESCRIPTION = PromptContract(
    name="product-description",
    version=1,
    description="Generates a brand-aligned product description.",
    template=textwrap.dedent("""\
        Write a product description for the following product.

        Product: {product_name}
        Category: {product_category}
        Key notes/ingredients: {key_notes}
        Target audience: {target_audience}
        Unique selling point: {unique_selling_point}

        Style guidance from fingerprint "{fingerprint_name}":
        {fingerprint_guidance}

        Write the description in {content_length} length.
        Output format: {output_format}
    """).strip(),
    required_vars=(
        "product_name",
        "product_category",
        "key_notes",
        "target_audience",
        "unique_selling_point",
        "fingerprint_name",
        "fingerprint_guidance",
    ),
    optional_vars=("content_length", "output_format"),
    defaults={"content_length": "medium", "output_format": "markdown"},
    output_format="markdown",
    max_output_tokens=400,
    tags=("marketing", "product", "description"),
)

_BRAND_STORY = PromptContract(
    name="brand-story",
    version=1,
    description="Generates a brand origin story or narrative.",
    template=textwrap.dedent("""\
        Tell the brand story for {brand_name}.

        Industry: {industry}
        Core values: {values}
        Key milestones: {milestones}
        Founder inspiration: {founder_inspiration}

        Style guidance from fingerprint "{fingerprint_name}":
        {fingerprint_guidance}

        Write a compelling narrative of approximately {word_count} words.
    """).strip(),
    required_vars=(
        "brand_name",
        "industry",
        "values",
        "milestones",
        "founder_inspiration",
        "fingerprint_name",
        "fingerprint_guidance",
    ),
    optional_vars=("word_count",),
    defaults={"word_count": 300},
    output_format="text",
    max_output_tokens=600,
    tags=("marketing", "brand", "story"),
)

_SOCIAL_POST = PromptContract(
    name="social-post",
    version=1,
    description="Generates a social media post for a brand.",
    template=textwrap.dedent("""\
        Create a social media post for {brand_name}.

        Platform: {platform}
        Topic: {topic}
        Call to action: {call_to_action}
        Hashtag style: {hashtag_style}

        Style guidance from fingerprint "{fingerprint_name}":
        {fingerprint_guidance}

        Keep the post under {max_chars} characters.
        Include relevant hashtags.
    """).strip(),
    required_vars=(
        "brand_name",
        "platform",
        "topic",
        "call_to_action",
        "fingerprint_name",
        "fingerprint_guidance",
    ),
    optional_vars=("hashtag_style", "max_chars"),
    defaults={"hashtag_style": "minimal", "max_chars": 280},
    output_format="text",
    max_output_tokens=200,
    tags=("marketing", "social", "post"),
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_CONTRACTS: dict[str, PromptContract] = {
    c.name: c for c in (_PRODUCT_DESCRIPTION, _BRAND_STORY, _SOCIAL_POST)
}


def list_contracts() -> list[str]:
    """Return available contract names."""
    return list(_CONTRACTS.keys())


def get_contract(name: str) -> PromptContract:
    """Get a contract by name. Raises KeyError if not found."""
    if name not in _CONTRACTS:
        available = ", ".join(sorted(_CONTRACTS.keys()))
        raise KeyError(f"Contract '{name}' not found. Available: {available}")
    return _CONTRACTS[name]


def register_contract(contract: PromptContract) -> None:
    """Register a custom contract (for runtime extension)."""
    _CONTRACTS[contract.name] = contract