"""BIZ-005 Provider abstraction — wraps AI calls with provenance tracking.

Every synthesis call MUST go through a Provider instance to record:
- provider name, model, prompt version
- input provenance (where the business data came from)
- cost, token counts, latency
- raw output + validation result

Providers are NOT allowed to bypass provenance logging.
"""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class ProviderResult:
    """Result of an AI provider call with full provenance."""
    raw_output: str
    parsed: dict[str, Any] | None = None
    provider: str = ""
    model: str = ""
    prompt_version: str = ""
    input_provenance: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    output_tokens: int = 0
    input_tokens: int = 0
    latency_ms: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.error is None and self.parsed is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "input_provenance": self.input_provenance,
            "cost_usd": self.cost_usd,
            "output_tokens": self.output_tokens,
            "input_tokens": self.input_tokens,
            "latency_ms": self.latency_ms,
            "timestamp": self.timestamp,
            "success": self.success,
            "error": self.error,
        }


class Provider(ABC):
    """Abstract base for AI providers.

    Subclasses implement _call_model(). The base class handles
    provenance tracking, timing, and error wrapping.
    """

    def __init__(
        self,
        provider_name: str,
        model: str,
        prompt_version: str,
        input_provenance: list[str] | None = None,
    ):
        self.provider_name = provider_name
        self.model = model
        self.prompt_version = prompt_version
        self.input_provenance = input_provenance or []
        self._history: list[ProviderResult] = []

    @abstractmethod
    def _call_model(self, prompt: str) -> tuple[str, dict[str, Any] | None, dict[str, Any]]:
        """Call the AI model and return (raw_text, parsed_json | None, usage_info).

        usage_info should contain: cost_usd, output_tokens, input_tokens (all optional).
        """
        ...

    def synthesize(self, prompt: str) -> ProviderResult:
        """Execute a synthesis call with full provenance tracking."""
        start = time.monotonic()
        try:
            raw_output, parsed, usage = self._call_model(prompt)
            latency_ms = int((time.monotonic() - start) * 1000)
            result = ProviderResult(
                raw_output=raw_output,
                parsed=parsed,
                provider=self.provider_name,
                model=self.model,
                prompt_version=self.prompt_version,
                input_provenance=list(self.input_provenance),
                cost_usd=usage.get("cost_usd", 0.0),
                output_tokens=usage.get("output_tokens", 0),
                input_tokens=usage.get("input_tokens", 0),
                latency_ms=latency_ms,
            )
        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            result = ProviderResult(
                raw_output="",
                provider=self.provider_name,
                model=self.model,
                prompt_version=self.prompt_version,
                input_provenance=list(self.input_provenance),
                latency_ms=latency_ms,
                error=str(e),
            )
        self._history.append(result)
        return result

    @property
    def history(self) -> list[ProviderResult]:
        return list(self._history)

    @property
    def total_cost(self) -> float:
        return sum(r.cost_usd for r in self._history)


class MockProvider(Provider):
    """Mock provider for testing — returns pre-configured responses."""

    def __init__(
        self,
        response: dict[str, Any] | None = None,
        error: str | None = None,
        **kwargs: Any,
    ):
        super().__init__(
            provider_name=kwargs.get("provider_name", "mock"),
            model=kwargs.get("model", "mock-v1"),
            prompt_version=kwargs.get("prompt_version", "test-v1.0.0"),
            input_provenance=kwargs.get("input_provenance", []),
        )
        self._response = response
        self._error = error

    def _call_model(self, prompt: str) -> tuple[str, dict[str, Any] | None, dict[str, Any]]:
        if self._error:
            raise RuntimeError(self._error)
        raw = json.dumps(self._response)
        return raw, self._response, {"cost_usd": 0.0, "output_tokens": 100, "input_tokens": 50}
