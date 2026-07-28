#!/usr/bin/env python3
"""
Prompt Contract Builder for BrandOS Intelligence.

Factory functions that assemble PromptContracts from a BrandProfile
and CommunicationFingerprint. Each builder produces a ready-to-use
contract for a specific content type.
"""

from __future__ import annotations

import hashlib
from typing import Any

from brand_profile import BrandProfile
from communication_fingerprints import CommunicationFingerprint, FingerprintType
from prompt_contracts import ContentType, PromptContract


def _make_id(brand: str, content_type: str, fingerprint: str) -> str:
    """Generate a deterministic contract ID."""
    raw = f"{brand}:{content_type}:{fingerprint}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def _build_system_prompt(
    fingerprint: CommunicationFingerprint,
    brand: BrandProfile,
) -> str:
    """Build the system prompt from fingerprint and brand profile."""
    voice_desc = fingerprint.description
    do_rules = "\n".join(f"- {g}" for g in fingerprint.do_guidelines)
    dont_rules = "\n".join(f"- {g}" for g in fingerprint.dont_guidelines)
    values = ", ".join(v.value for v in brand.core_values) if brand.core_values else "not specified"
    tone = brand.primary_tone.value if brand.primary_tone.value else fingerprint.name.lower()

    return (
        f"You are a brand voice writer for {brand.brand_name.value or 'the brand'}.\n\n"
        f"VOICE STYLE: {fingerprint.name}\n"
        f"{voice_desc}\n\n"
        f"BRAND TONE: {tone}\n"
        f"BRAND VALUES: {values}\n\n"
        f"DO:\n{do_rules}\n\n"
        f"DON'T:\n{dont_rules}\n\n"
        f"Vocabulary: prefer {', '.join(fingerprint.vocabulary.preferred_words[:5])}\n"
        f"Avoid: {', '.join(fingerprint.vocabulary.avoided_words[:5])}\n"
        f"Sentence length: {fingerprint.vocabulary.sentence_length}\n"
        f"Formality: {fingerprint.vocabulary.formality_level}"
    )


def build_social_post_contract(
    brand: BrandProfile,
    fingerprint: CommunicationFingerprint,
) -> PromptContract:
    """Build a contract for social media post generation."""
    system = _build_system_prompt(fingerprint, brand)
    user_tpl = (
        "Write a social media post for {brand_name}.\n\n"
        "Topic: {topic}\n"
        "Platform: {platform}\n"
        "Max length: {max_length} characters\n\n"
        "The post should reflect the brand's {tone} voice and "
        "incorporate these values: {values}.\n"
        "Hashtag style: {hashtag_style}"
    )
    cid = _make_id(brand.brand_name.value, "social_post", fingerprint.fingerprint_type.value)
    return PromptContract(
        contract_id=cid,
        content_type=ContentType.SOCIAL_POST,
        fingerprint_type=fingerprint.fingerprint_type.value,
        brand_name=brand.brand_name.value,
        system_prompt=system,
        user_prompt_template=user_tpl,
        max_tokens=300,
        temperature=0.8,
    )


def build_product_description_contract(
    brand: BrandProfile,
    fingerprint: CommunicationFingerprint,
) -> PromptContract:
    """Build a contract for product description generation."""
    system = _build_system_prompt(fingerprint, brand)
    user_tpl = (
        "Write a product description for {brand_name}.\n\n"
        "Product: {product_name}\n"
        "Key features: {features}\n"
        "Target audience: {audience}\n"
        "Max length: {max_length} words\n\n"
        "The description should feel {tone} and highlight {usp}."
    )
    cid = _make_id(brand.brand_name.value, "product_desc", fingerprint.fingerprint_type.value)
    return PromptContract(
        contract_id=cid,
        content_type=ContentType.PRODUCT_DESCRIPTION,
        fingerprint_type=fingerprint.fingerprint_type.value,
        brand_name=brand.brand_name.value,
        system_prompt=system,
        user_prompt_template=user_tpl,
        max_tokens=400,
        temperature=0.7,
    )


def build_email_subject_contract(
    brand: BrandProfile,
    fingerprint: CommunicationFingerprint,
) -> PromptContract:
    """Build a contract for email subject line generation."""
    system = _build_system_prompt(fingerprint, brand)
    user_tpl = (
        "Write 5 email subject lines for {brand_name}.\n\n"
        "Campaign goal: {goal}\n"
        "Audience: {audience}\n"
        "Tone: {tone}\n\n"
        "Each subject line should be under 60 characters and "
        "match the brand's {fingerprint_name} voice."
    )
    cid = _make_id(brand.brand_name.value, "email_subject", fingerprint.fingerprint_type.value)
    return PromptContract(
        contract_id=cid,
        content_type=ContentType.EMAIL_SUBJECT,
        fingerprint_type=fingerprint.fingerprint_type.value,
        brand_name=brand.brand_name.value,
        system_prompt=system,
        user_prompt_template=user_tpl,
        max_tokens=200,
        temperature=0.9,
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_CONTRACT_BUILDERS = {
    ContentType.SOCIAL_POST: build_social_post_contract,
    ContentType.PRODUCT_DESCRIPTION: build_product_description_contract,
    ContentType.EMAIL_SUBJECT: build_email_subject_contract,
}


def build_contract(
    content_type: ContentType,
    brand: BrandProfile,
    fingerprint: CommunicationFingerprint,
) -> PromptContract:
    """Build a prompt contract for the given content type."""
    builder = _CONTRACT_BUILDERS.get(content_type)
    if not builder:
        raise ValueError(f"No builder registered for content type: {content_type}")
    return builder(brand, fingerprint)
