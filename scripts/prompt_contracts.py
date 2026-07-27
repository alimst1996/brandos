#!/usr/bin/env python3
"""
Prompt Contracts for BrandOS Intelligence.

Structured templates for AI content generation that combine
Brand Profile + Communication Fingerprint into enforceable prompts.

Every prompt contract is versioned and logged for audit trail.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ContentType(str, Enum):
    """Supported content types for generation."""
    SOCIAL_POST = "social_post"
    BLOG_INTRO = "blog_intro"
    PRODUCT_DESCRIPTION = "product_description"
    EMAIL_SUBJECT = "email_subject"
    AD_COPY = "ad_copy"
    TAGLINE = "tagline"


@dataclass
class PromptContract:
    """
    A structured prompt template for AI content generation.

    Combines brand profile, fingerprint, and content type into
    a single enforceable contract. Every contract is versioned
    and carries an audit trail.
    """
    contract_id: str
    content_type: ContentType
    fingerprint_type: str
    brand_name: str

    # The actual prompt template
    system_prompt: str
    user_prompt_template: str

    # Constraints
    max_tokens: int = 500
    temperature: float = 0.7

    # Metadata
    version: str = "1.0.0"
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    prompt_hash: str = ""  # For deduplication

    def render_user_prompt(self, **kwargs: Any) -> str:
        """Render the user prompt template with actual values."""
        try:
            return self.user_prompt_template.format(**kwargs)
        except KeyError as e:
            raise ValueError(f"Missing template variable: {e}") from e

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "content_type": self.content_type.value,
            "fingerprint_type": self.fingerprint_type,
            "brand_name": self.brand_name,
            "system_prompt": self.system_prompt,
            "user_prompt_template": self.user_prompt_template,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "version": self.version,
            "created_at": self.created_at,
            "prompt_hash": self.prompt_hash,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PromptContract:
        return cls(
            contract_id=data["contract_id"],
            content_type=ContentType(data["content_type"]),
            fingerprint_type=data["fingerprint_type"],
            brand_name=data["brand_name"],
            system_prompt=data["system_prompt"],
            user_prompt_template=data["user_prompt_template"],
            max_tokens=data.get("max_tokens", 500),
            temperature=data.get("temperature", 0.7),
            version=data.get("version", "1.0.0"),
            created_at=data.get("created_at", ""),
            prompt_hash=data.get("prompt_hash", ""),
        )
