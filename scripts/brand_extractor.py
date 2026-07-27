#!/usr/bin/env python3
"""
Brand Voice Extractor for BrandOS Intelligence.

Extracts brand voice characteristics from crawled web content.
Uses pattern matching, frequency analysis, and heuristic scoring
to build a BrandProfile with evidence trails and confidence scores.

Input: list of CrawledPage dicts (from the crawling subsystem)
Output: BrandProfile with attributed values and evidence

Every extraction records provenance (source URL, excerpt, timestamp).
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from brand_profile import (
    AttributedValue,
    BrandProfile,
    Evidence,
    ToneCategory,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Tone signal words mapped to categories
TONE_SIGNALS: dict[ToneCategory, list[str]] = {
    ToneCategory.FORMAL: [
        "therefore", "consequently", "furthermore", "hereby", "pursuant",
        "aforementioned", "notwithstanding", "accordingly", "henceforth",
    ],
    ToneCategory.CASUAL: [
        "hey", "awesome", "cool", "yeah", "gonna", "wanna", "gotta",
        "totally", "literally", "basically", "stuff", "things",
    ],
    ToneCategory.PLAYFUL: [
        "fun", "exciting", "wow", "yay", "oops", "yummy", "sweet",
        "magic", "sparkle", "adventure", "dream", "fantastic",
    ],
    ToneCategory.AUTHORITATIVE: [
        "proven", "established", "definitive", "benchmark", "standard",
        "research", "data", "evidence", "validated", "certified",
        "expert", "leading", "premier",
    ],
    ToneCategory.EMPATHETIC: [
        "understand", "feel", "care", "support", "together", "journey",
        "comfort", "safe", "welcome", "belong", "nurture", "gentle",
    ],
    ToneCategory.BOLD: [
        "revolutionary", "breakthrough", "disrupt", "reimagine", "defy",
        "unleash", "transform", "challenge", "pioneer", "fearless",
        "game-changing", "unapologetic",
    ],
    ToneCategory.MINIMALIST: [
        "simple", "clean", "essential", "pure", "refined", "stripped",
        "bare", "fundamental", "core", "basic", "uncluttered",
    ],
    ToneCategory.LUXURY: [
        "exclusive", "premium", "artisan", "bespoke", "curated",
        "heritage", "craftsmanship", "elegant", "sophisticated",
        "refined", "prestige", "pristine",
    ],
}

# Industry keyword associations
INDUSTRY_KEYWORDS: dict[str, list[str]] = {
    "technology": ["software", "app", "platform", "digital", "cloud", "saas", "api", "code", "tech"],
    "fashion": ["style", "wear", "collection", "design", "fabric", "trend", "outfit", "season"],
    "beauty": ["skin", "makeup", "cosmetic", "glow", "care", "routine", "formula", "ingredient"],
    "food_beverage": ["recipe", "taste", "flavor", "fresh", "organic", "ingredient", "chef", "cook"],
    "finance": ["invest", "return", "portfolio", "wealth", "financial", "capital", "asset", "growth"],
    "health": ["wellness", "health", "vitality", "fitness", "nutrition", "therapy", "healing"],
    "education": ["learn", "course", "study", "knowledge", "skill", "training", "certificate"],
    "luxury": ["luxury", "exclusive", "premium", "bespoke", "artisan", "heritage", "prestige"],
    "ecommerce": ["shop", "buy", "order", "delivery", "cart", "checkout", "product", "store"],
    "media": ["content", "story", "publish", "stream", "audience", "editorial", "broadcast"],
}

# Common brand value words
VALUE_KEYWORDS: dict[str, list[str]] = {
    "innovation": ["innovate", "innovative", "pioneer", "breakthrough", "cutting-edge", "next-gen"],
    "sustainability": ["sustainable", "eco", "green", "planet", "environment", "organic", "ethical"],
    "quality": ["quality", "craftsmanship", "premium", "excellence", "precision", "meticulous"],
    "authenticity": ["authentic", "genuine", "real", "honest", "transparent", "true", "original"],
    "community": ["community", "together", "belong", "connect", "share", "collaborate", "inclusive"],
    "simplicity": ["simple", "easy", "effortless", "intuitive", "streamlined", "minimal"],
    "tradition": ["heritage", "tradition", "classic", "timeless", "legacy", "established", "founded"],
}


# ---------------------------------------------------------------------------
# Content cleaning
# ---------------------------------------------------------------------------

def clean_html(text: str) -> str:
    """Strip HTML tags and normalize whitespace."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_sentences(text: str) -> list[str]:
    """Split text into sentences."""
    # Simple sentence splitter
    sentences = re.split(r"[.!?]+", text)
    return [s.strip() for s in sentences if len(s.strip()) > 10]


def extract_phrases(text: str, min_words: int = 2, max_words: int = 5) -> list[str]:
    """Extract potential brand phrases (n-grams)."""
    words = re.findall(r"\b[a-z]+\b", text.lower())
    phrases = []
    for n in range(min_words, max_words + 1):
        for i in range(len(words) - n + 1):
            phrase = " ".join(words[i:i + n])
            phrases.append(phrase)
    return phrases


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

def _score_tone(text: str) -> dict[ToneCategory, float]:
    """Score text against each tone category."""
    text_lower = text.lower()
    words = re.findall(r"\b\w+\b", text_lower)
    total_words = max(len(words), 1)

    scores: dict[ToneCategory, float] = {}
    for category, signals in TONE_SIGNALS.items():
        count = sum(1 for w in words if w in signals)
        # Also check multi-word signals
        for signal in signals:
            if " " in signal and signal in text_lower:
                count += 1
        scores[category] = min(count / total_words * 100, 1.0)

    return scores


def _detect_industry(text: str) -> dict[str, float]:
    """Detect industry from text content."""
    text_lower = text.lower()
    words = set(re.findall(r"\b\w+\b", text_lower))
    total_words = max(len(words), 1)

    scores: dict[str, float] = {}
    for industry, keywords in INDUSTRY_KEYWORDS.items():
        count = len(words & set(keywords))
        scores[industry] = min(count / total_words * 5, 1.0)

    return scores


def _detect_values(text: str) -> dict[str, float]:
    """Detect brand values from text content."""
    text_lower = text.lower()
    words = set(re.findall(r"\b\w+\b", text_lower))

    scores: dict[str, float] = {}
    for value, keywords in VALUE_KEYWORDS.items():
        count = len(words & set(keywords))
        scores[value] = min(count / max(len(words), 1) * 10, 1.0)

    return scores


def _extract_brand_name_from_url(url: str) -> str:
    """Extract a probable brand name from a URL."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    # Remove www. and common TLDs
    name = re.sub(r"^www\.", "", hostname)
    name = re.sub(r"\.(com|org|net|io|co|app|dev)$", "", name)
    # Take the main part
    parts = name.split(".")
    return parts[0].capitalize() if parts else ""


# ---------------------------------------------------------------------------
# Main extractor
# ---------------------------------------------------------------------------

@dataclass
class CrawledPage:
    """Represents a single crawled page."""
    url: str
    title: str = ""
    content: str = ""
    meta_description: str = ""
    meta_keywords: list[str] = field(default_factory=list)
    crawl_timestamp: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CrawledPage:
        return cls(
            url=data.get("url", ""),
            title=data.get("title", ""),
            content=data.get("content", ""),
            meta_description=data.get("meta_description", ""),
            meta_keywords=data.get("meta_keywords", []),
            crawl_timestamp=data.get("crawl_timestamp", ""),
        )


class BrandExtractor:
    """
    Extracts brand voice characteristics from crawled content.

    Produces a BrandProfile with evidence trails and confidence scores.
    Every extracted attribute is backed by specific text excerpts.
    """

    def __init__(self, min_confidence: float = 0.1):
        self.min_confidence = min_confidence

    def extract(self, pages: list[CrawledPage | dict[str, Any]]) -> BrandProfile:
        """
        Extract brand profile from crawled pages.

        Args:
            pages: List of CrawledPage objects or dicts.

        Returns:
            BrandProfile with attributed values and evidence.
        """
        # Normalize input
        crawled = []
        for p in pages:
            if isinstance(p, dict):
                crawled.append(CrawledPage.from_dict(p))
            else:
                crawled.append(p)

        if not crawled:
            return BrandProfile()

        # Combine all text for analysis
        all_text = " ".join(
            clean_html(p.content) for p in crawled if p.content
        )
        source_urls = [p.url for p in crawled]

        profile = BrandProfile()
        profile.source_urls = source_urls

        # Extract each attribute
        profile.brand_name = self._extract_brand_name(crawled)
        profile.industry = self._extract_industry(all_text, crawled)
        profile.primary_tone = self._extract_primary_tone(all_text, crawled)
        profile.secondary_tones = self._extract_secondary_tones(all_text, crawled)
        profile.core_values = self._extract_values(all_text, crawled)
        profile.description = self._extract_description(crawled)
        profile.common_phrases = self._extract_common_phrases(all_text, crawled)
        profile.vocabulary_level = self._extract_vocabulary_level(all_text, crawled)
        profile.sentence_style = self._extract_sentence_style(all_text, crawled)
        profile.tagline = self._extract_tagline(crawled)
        profile.target_audience = self._extract_target_audience(all_text, crawled)

        # Compute final scores
        profile.compute_overall_confidence()
        profile.count_evidence()

        return profile

    def _extract_brand_name(self, pages: list[CrawledPage]) -> AttributedValue:
        """Extract brand name from page titles and URLs."""
        # Look for brand name in page titles (usually "| Brand" or "- Brand")
        names: Counter[str] = Counter()
        evidence: list[Evidence] = []

        for page in pages:
            if page.title:
                # Try to extract from title patterns
                for pattern in [
                    r"\|\s*(.+?)$",
                    r"[-–]\s*(.+?)$",
                    r"^(.+?)\s*[-–|]",
                ]:
                    match = re.search(pattern, page.title)
                    if match:
                        name = match.group(1).strip()
                        if 2 < len(name) < 50:
                            names[name] += 1
                            evidence.append(Evidence(
                                value=name,
                                source_url=page.url,
                                excerpt=page.title,
                                confidence=0.7,
                            ))

            # Fallback: extract from URL
            url_name = _extract_brand_name_from_url(page.url)
            if url_name and url_name not in ("localhost", "127", "example"):
                names[url_name] += 1
                evidence.append(Evidence(
                    value=url_name,
                    source_url=page.url,
                    excerpt=f"Extracted from URL: {page.url}",
                    confidence=0.5,
                ))

        if not names:
            return AttributedValue(value="")

        # Most common name
        best_name = names.most_common(1)[0][0]
        # Filter evidence to only the best name
        relevant_evidence = [e for e in evidence if e.value == best_name]

        return AttributedValue(value=best_name, evidence=relevant_evidence)

    def _extract_industry(self, text: str, pages: list[CrawledPage]) -> AttributedValue:
        """Detect industry from content."""
        scores = _detect_industry(text)
        if not scores:
            return AttributedValue(value="")

        best_industry = max(scores, key=scores.get)  # type: ignore
        confidence = scores[best_industry]

        if confidence < self.min_confidence:
            return AttributedValue(value="")

        # Find evidence excerpts
        evidence = []
        keywords = INDUSTRY_KEYWORDS.get(best_industry, [])
        for page in pages:
            content = clean_html(page.content)
            for keyword in keywords[:3]:  # Top 3 keywords
                idx = content.lower().find(keyword)
                if idx >= 0:
                    start = max(0, idx - 50)
                    end = min(len(content), idx + len(keyword) + 50)
                    excerpt = content[start:end]
                    evidence.append(Evidence(
                        value=best_industry,
                        source_url=page.url,
                        excerpt=excerpt,
                        confidence=confidence,
                    ))
                    break  # One evidence per page

        return AttributedValue(value=best_industry, evidence=evidence)

    def _extract_primary_tone(self, text: str, pages: list[CrawledPage]) -> AttributedValue:
        """Extract the primary tone category."""
        scores = _score_tone(text)
        if not scores:
            return AttributedValue(value="")

        best_tone = max(scores, key=scores.get)  # type: ignore
        confidence = scores[best_tone]

        if confidence < self.min_confidence:
            return AttributedValue(value="")

        # Find evidence
        evidence = []
        signals = TONE_SIGNALS.get(best_tone, [])
        for page in pages:
            content = clean_html(page.content)
            for signal in signals[:3]:
                idx = content.lower().find(signal)
                if idx >= 0:
                    start = max(0, idx - 40)
                    end = min(len(content), idx + len(signal) + 40)
                    evidence.append(Evidence(
                        value=best_tone.value,
                        source_url=page.url,
                        excerpt=content[start:end],
                        confidence=confidence,
                    ))
                    break

        return AttributedValue(value=best_tone.value, evidence=evidence)

    def _extract_secondary_tones(self, text: str, pages: list[CrawledPage]) -> list[AttributedValue]:
        """Extract secondary tone categories."""
        scores = _score_tone(text)
        primary = self._extract_primary_tone(text, pages)

        # Get top 2 non-primary tones
        sorted_tones = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        secondary = []
        for tone, score in sorted_tones:
            if tone.value != primary.value and score >= self.min_confidence:
                evidence = []
                for page in pages[:2]:
                    evidence.append(Evidence(
                        value=tone.value,
                        source_url=page.url,
                        excerpt=f"Tone signal detected (score: {score:.2f})",
                        confidence=score,
                    ))
                secondary.append(AttributedValue(value=tone.value, evidence=evidence))
                if len(secondary) >= 2:
                    break

        return secondary

    def _extract_values(self, text: str, pages: list[CrawledPage]) -> list[AttributedValue]:
        """Extract brand values from content."""
        scores = _detect_values(text)
        values = []

        for value_name, score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
            if score >= self.min_confidence:
                evidence = []
                keywords = VALUE_KEYWORDS.get(value_name, [])
                for page in pages:
                    content = clean_html(page.content)
                    for keyword in keywords[:2]:
                        idx = content.lower().find(keyword)
                        if idx >= 0:
                            start = max(0, idx - 40)
                            end = min(len(content), idx + len(keyword) + 40)
                            evidence.append(Evidence(
                                value=value_name,
                                source_url=page.url,
                                excerpt=content[start:end],
                                confidence=score,
                            ))
                            break

                values.append(AttributedValue(value=value_name, evidence=evidence))
                if len(values) >= 5:
                    break

        return values

    def _extract_description(self, pages: list[CrawledPage]) -> AttributedValue:
        """Extract brand description from meta descriptions."""
        evidence = []
        descriptions = []

        for page in pages:
            if page.meta_description and len(page.meta_description) > 20:
                descriptions.append(page.meta_description)
                evidence.append(Evidence(
                    value=page.meta_description,
                    source_url=page.url,
                    excerpt=page.meta_description,
                    confidence=0.8,
                ))

        if not descriptions:
            return AttributedValue(value="")

        # Use the longest description as primary
        best = max(descriptions, key=len)
        return AttributedValue(value=best, evidence=evidence)

    def _extract_common_phrases(self, text: str, pages: list[CrawledPage]) -> list[AttributedValue]:
        """Extract frequently used brand phrases."""
        phrases = extract_phrases(text, min_words=2, max_words=4)
        phrase_counts = Counter(phrases)

        # Filter to phrases that appear multiple times
        common = [
            (phrase, count)
            for phrase, count in phrase_counts.most_common(20)
            if count >= 2
        ]

        result = []
        for phrase, count in common[:10]:
            evidence = []
            for page in pages:
                if phrase in page.content.lower():
                    idx = page.content.lower().find(phrase)
                    start = max(0, idx - 30)
                    end = min(len(page.content), idx + len(phrase) + 30)
                    evidence.append(Evidence(
                        value=phrase,
                        source_url=page.url,
                        excerpt=page.content[start:end],
                        confidence=min(count / 10, 1.0),
                    ))
                    if len(evidence) >= 2:
                        break

            result.append(AttributedValue(value=phrase, evidence=evidence))

        return result

    def _extract_vocabulary_level(self, text: str, pages: list[CrawledPage]) -> AttributedValue:
        """Estimate vocabulary sophistication level."""
        words = re.findall(r"\b[a-z]+\b", text.lower())
        if not words:
            return AttributedValue(value="")

        # Average word length as a proxy for complexity
        avg_len = sum(len(w) for w in words) / len(words)

        if avg_len > 6:
            level = "advanced"
        elif avg_len > 4.5:
            level = "intermediate"
        else:
            level = "basic"

        evidence = []
        for page in pages[:2]:
            evidence.append(Evidence(
                value=level,
                source_url=page.url,
                excerpt=f"Average word length: {avg_len:.1f} characters",
                confidence=min(abs(avg_len - 5) / 3, 1.0),
            ))

        return AttributedValue(value=level, evidence=evidence)

    def _extract_sentence_style(self, text: str, pages: list[CrawledPage]) -> AttributedValue:
        """Analyze sentence construction style."""
        sentences = extract_sentences(text)
        if not sentences:
            return AttributedValue(value="")

        avg_len = sum(len(s.split()) for s in sentences) / len(sentences)

        if avg_len > 20:
            style = "complex"
        elif avg_len > 12:
            style = "moderate"
        else:
            style = "concise"

        evidence = []
        for page in pages[:2]:
            evidence.append(Evidence(
                value=style,
                source_url=page.url,
                excerpt=f"Average sentence length: {avg_len:.1f} words",
                confidence=0.6,
            ))

        return AttributedValue(value=style, evidence=evidence)

    def _extract_tagline(self, pages: list[CrawledPage]) -> AttributedValue:
        """Try to extract a tagline from meta or headers."""
        evidence = []

        for page in pages:
            # Look for tagline patterns in content
            content = clean_html(page.content)
            # Common tagline patterns
            for pattern in [
                r"(?:tagline|slogan|mission)[:\s]+(.{10,80})",
                r"<h[12][^>]*>(.{10,80})</h[12]>",
                r"class=\"tagline\"[^>]*>(.{10,80})<",
            ]:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    tagline = match.group(1).strip()
                    evidence.append(Evidence(
                        value=tagline,
                        source_url=page.url,
                        excerpt=tagline,
                        confidence=0.6,
                    ))

        if not evidence:
            return AttributedValue(value="")

        return AttributedValue(value=evidence[0].value, evidence=evidence)

    def _extract_target_audience(self, text: str, pages: list[CrawledPage]) -> AttributedValue:
        """Infer target audience from content patterns."""
        text_lower = text.lower()

        # Simple audience signals
        audience_signals = {
            "professionals": ["professional", "enterprise", "business", "corporate", "b2b"],
            "consumers": ["consumer", "lifestyle", "personal", "everyday", "home"],
            "young_adults": ["gen z", "millennial", "youth", "trendy", "viral"],
            "luxury_buyers": ["luxury", "exclusive", "premium", "bespoke", "connoisseur"],
            "tech_enthusiasts": ["developer", "open-source", "api", "technical", "engineering"],
        }

        scores: dict[str, float] = {}
        for audience, signals in audience_signals.items():
            count = sum(1 for s in signals if s in text_lower)
            scores[audience] = count / max(len(signals), 1)

        if not scores:
            return AttributedValue(value="")

        best = max(scores, key=scores.get)  # type: ignore
        confidence = scores[best]

        if confidence < self.min_confidence:
            return AttributedValue(value="")

        evidence = []
        for page in pages[:2]:
            evidence.append(Evidence(
                value=best,
                source_url=page.url,
                excerpt=f"Audience signal detected (score: {confidence:.2f})",
                confidence=confidence,
            ))

        return AttributedValue(value=best, evidence=evidence)


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def extract_brand_voice(pages: list[dict[str, Any] | CrawledPage]) -> BrandProfile:
    """
    Convenience function to extract brand voice from crawled pages.

    Args:
        pages: List of crawled page dicts or CrawledPage objects.

    Returns:
        BrandProfile with evidence and confidence scores.
    """
    extractor = BrandExtractor()
    return extractor.extract(pages)
