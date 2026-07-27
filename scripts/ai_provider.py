#!/usr/bin/env python3
"""
AI Provider Abstraction for BrandOS Intelligence.

Abstract interface for AI providers with automatic run logging.
Every call records provider, model, prompt, input provenance,
cost, output, and validation result.

Providers must implement the `generate` method.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from ai_run_logger import AIRunRecord, RunLogger
from prompt_contracts import PromptContract


@dataclass
class GenerationResult:
    """Result from an AI generation call."""
    run_id: str
    content: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    raw_response: dict[str, Any] | None = None


class AIProvider(ABC):
    """
    Abstract base class for AI providers.

    Every provider must implement `generate` which takes a
    PromptContract and returns a GenerationResult.
    """

    def __init__(self, provider_name: str, model: str, logger: RunLogger | None = None):
        self.provider_name = provider_name
        self.model = model
        self.logger = logger or RunLogger()

    @abstractmethod
    def _call_api(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> dict[str, Any]:
        """
        Make the actual API call to the provider.

        Returns a dict with at minimum:
            - "content": str (the generated text)
            - "input_tokens": int
            - "output_tokens": int
        """
        ...

    def generate(
        self,
        contract: PromptContract,
        variables: dict[str, Any],
        source_urls: list[str] | None = None,
    ) -> GenerationResult:
        """
        Generate content using the prompt contract.

        Automatically logs the run for audit trail.

        Args:
            contract: The prompt contract to use.
            variables: Template variables for the user prompt.
            source_urls: URLs that contributed to the brand profile.

        Returns:
            GenerationResult with content and metadata.
        """
        user_prompt = contract.render_user_prompt(**variables)

        # Log pre-execution
        record = self.logger.log_run(
            provider=self.provider_name,
            model=self.model,
            contract_id=contract.contract_id,
            prompt_version=contract.version,
            user_prompt=user_prompt,
            brand_name=contract.brand_name,
            fingerprint_type=contract.fingerprint_type,
            content_type=contract.content_type.value,
            source_urls=source_urls,
        )

        try:
            response = self._call_api(
                system_prompt=contract.system_prompt,
                user_prompt=user_prompt,
                max_tokens=contract.max_tokens,
                temperature=contract.temperature,
            )

            content = response.get("content", "")
            input_tokens = response.get("input_tokens", 0)
            output_tokens = response.get("output_tokens", 0)
            cost = self._estimate_cost(input_tokens, output_tokens)

            # Update record with results
            record.raw_output = content
            record.input_tokens = input_tokens
            record.output_tokens = output_tokens
            record.total_cost_usd = cost
            record.status = "success"
            self.logger.update_run(record)

            return GenerationResult(
                run_id=record.run_id,
                content=content,
                provider=self.provider_name,
                model=self.model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
                raw_response=response,
            )

        except Exception as e:
            record.status = "failed"
            record.validation_errors = [str(e)]
            self.logger.update_run(record)
            raise

    def _estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Estimate cost in USD. Override per provider."""
        # Default rough estimate: $0.01 per 1K tokens
        return (input_tokens + output_tokens) / 1000 * 0.01


class MockProvider(AIProvider):
    """
    Mock provider for testing.

    Returns a configurable response without making API calls.
    """

    def __init__(
        self,
        response: str = "Mock AI response.",
        logger: RunLogger | None = None,
    ):
        super().__init__("mock", "mock-model", logger)
        self._response = response

    def _call_api(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> dict[str, Any]:
        return {
            "content": self._response,
            "input_tokens": len(system_prompt.split()) + len(user_prompt.split()),
            "output_tokens": len(self._response.split()),
        }
