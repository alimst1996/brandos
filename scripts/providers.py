#!/usr/bin/env python3
"""Provider abstraction for BrandOS text content generation.

A unified interface for AI text generation providers. Each provider adapter
wraps a concrete API (OpenAI, OpenRouter, Anthropic, etc.) behind the same
generate() method and returns a GenerationResult that records provenance,
cost, and output -- required for every AI run.

Usage:
    from providers import get_provider, list_providers, GenerationResult

    provider = get_provider("openai")
    result = provider.generate(
        system_prompt="You are a brand writer.",
        user_prompt="Write a product description for...",
        model="gpt-4o-mini",
    )
    print(result.text, result.cost_usd, result.tokens_used)
"""
from __future__ import annotations

import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class GenerationResult:
    """Immutable record of a single AI generation.

    Every AI run must produce one of these. It is the audit trail that proves
    what was asked, what was returned, and what it cost.
    """
    text: str
    provider: str
    model: str
    prompt_version: int = 0
    input_provenance: dict[str, str] = field(default_factory=dict)
    cost_usd: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    raw_response: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.error is None

    def to_audit_dict(self) -> dict[str, Any]:
        """Serialization for audit logging (excludes raw_response)."""
        truncated = self.text[:500] + "..." if len(self.text) > 500 else self.text
        return {
            "text": truncated,
            "provider": self.provider,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "input_provenance": self.input_provenance,
            "cost_usd": self.cost_usd,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "latency_ms": self.latency_ms,
            "timestamp": self.timestamp,
            "error": self.error,
        }


class Provider(ABC):
    """Abstract base for AI text generation providers."""

    name: str

    @abstractmethod
    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        max_tokens: int = 500,
        temperature: float = 0.7,
    ) -> GenerationResult:
        ...

    @abstractmethod
    def is_available(self) -> bool:
        ...


# ---------------------------------------------------------------------------
# OpenAI provider
# ---------------------------------------------------------------------------

class OpenAIProvider(Provider):
    """OpenAI API provider adapter."""

    name = "openai"

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")

    def is_available(self) -> bool:
        return bool(self._api_key)

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        max_tokens: int = 500,
        temperature: float = 0.7,
    ) -> GenerationResult:
        model = model or "gpt-4o-mini"
        start = time.time()
        try:
            import openai
            client = openai.OpenAI(api_key=self._api_key)
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            text = response.choices[0].message.content or ""
            tokens_in = response.usage.prompt_tokens if response.usage else 0
            tokens_out = response.usage.completion_tokens if response.usage else 0
            latency = int((time.time() - start) * 1000)
            cost = self._estimate_cost(model, tokens_in, tokens_out)
            return GenerationResult(
                text=text,
                provider=self.name,
                model=model,
                cost_usd=cost,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_ms=latency,
                raw_response=response.model_dump() if hasattr(response, "model_dump") else {},
            )
        except ImportError:
            return GenerationResult(
                text="",
                provider=self.name,
                model=model,
                error="openai package not installed. Run: pip install openai",
                latency_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return GenerationResult(
                text="",
                provider=self.name,
                model=model,
                error=str(e),
                latency_ms=int((time.time() - start) * 1000),
            )

    @staticmethod
    def _estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
        """Rough cost estimation (USD per 1M tokens)."""
        pricing: dict[str, tuple[float, float]] = {
            "gpt-4o": (2.50, 10.00),
            "gpt-4o-mini": (0.15, 0.60),
            "gpt-4-turbo": (10.00, 30.00),
            "gpt-3.5-turbo": (0.50, 1.50),
        }
        in_price, out_price = pricing.get(model, (0.0, 0.0))
        return (tokens_in * in_price + tokens_out * out_price) / 1_000_000


# ---------------------------------------------------------------------------
# OpenRouter provider
# ---------------------------------------------------------------------------

class OpenRouterProvider(Provider):
    """OpenRouter API provider (routes to multiple models)."""

    name = "openrouter"

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")

    def is_available(self) -> bool:
        return bool(self._api_key)

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        max_tokens: int = 500,
        temperature: float = 0.7,
    ) -> GenerationResult:
        model = model or "anthropic/claude-sonnet-4"
        start = time.time()
        try:
            import httpx
            resp = httpx.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            tokens_in = usage.get("prompt_tokens", 0)
            tokens_out = usage.get("completion_tokens", 0)
            latency = int((time.time() - start) * 1000)
            return GenerationResult(
                text=text,
                provider=self.name,
                model=model,
                cost_usd=data.get("usage", {}).get("cost", 0.0),
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_ms=latency,
                raw_response=data,
            )
        except ImportError:
            return GenerationResult(
                text="",
                provider=self.name,
                model=model,
                error="httpx package not installed. Run: pip install httpx",
                latency_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return GenerationResult(
                text="",
                provider=self.name,
                model=model,
                error=str(e),
                latency_ms=int((time.time() - start) * 1000),
            )


# ---------------------------------------------------------------------------
# Stub provider for testing (no API calls, returns deterministic output)
# ---------------------------------------------------------------------------

class StubProvider(Provider):
    """Test-only provider that returns canned responses. Never makes API calls."""

    name = "stub"

    def __init__(self, response_text: str = "[stub response]", available: bool = True) -> None:
        self._response_text = response_text
        self._available = available

    def is_available(self) -> bool:
        return self._available

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        max_tokens: int = 500,
        temperature: float = 0.7,
    ) -> GenerationResult:
        model = model or "stub-model"
        return GenerationResult(
            text=self._response_text,
            provider=self.name,
            model=model,
            tokens_in=len(system_prompt.split()) + len(user_prompt.split()),
            tokens_out=len(self._response_text.split()),
            latency_ms=1,
        )


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

_PROVIDERS: dict[str, Provider] = {
    p.name: p for p in (OpenAIProvider(), OpenRouterProvider(), StubProvider())
}


def list_providers() -> list[str]:
    """Return registered provider names."""
    return list(_PROVIDERS.keys())


def get_provider(name: str) -> Provider:
    """Get a provider by name. Raises KeyError if not found."""
    if name not in _PROVIDERS:
        available = ", ".join(sorted(_PROVIDERS.keys()))
        raise KeyError(f"Provider {name!r} not found. Available: {available}")
    return _PROVIDERS[name]


def register_provider(provider: Provider) -> None:
    """Register a custom provider (for runtime extension)."""
    _PROVIDERS[provider.name] = provider


def get_available_provider() -> Provider | None:
    """Return the first available provider, or None."""
    for p in _PROVIDERS.values():
        if p.is_available():
            return p
    return None
