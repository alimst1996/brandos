#!/usr/bin/env python3
"""Text content generation engine for BrandOS Intelligence.

The main orchestration layer that combines brand profiles, communication
fingerprints, prompt contracts, provider abstraction, and output validation
into a single generate() call.

Every generation produces a GenerationAudit record that captures the full
provenance chain: profile -> fingerprint -> contract -> provider -> validation.

Usage:
    from text_generator import TextGenerator, GenerationAudit

    generator = TextGenerator(profile, provider_name="stub")
    audit = generator.generate(
        contract_name="product-description",
        fingerprint_name="authority",
        product_name="Midnight Noir",
        product_category="luxury perfume",
        key_notes="oud, amber, black rose",
        target_audience="luxury fragrance enthusiasts",
        unique_selling_point="artisanal blending from rare ingredients",
    )
    print(audit.result.text)
    print(audit.validation_results)
    print(audit.result.to_audit_dict())

CLI usage:
    python scripts/text_generator.py --fingerprint authority --contract product-description \\
        --product-name "Midnight Noir" --product-category "luxury perfume" \\
        --key-notes "oud, amber, black rose" --target-audience "luxury enthusiasts" \\
        --unique-selling-point "artisanal blending"
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from typing import Any

from brand_profile import BrandProfile, BrandIdentity, BrandVoice, BrandConstraints
from fingerprints import get_fingerprint, list_fingerprints, Fingerprint
from prompt_contracts import get_contract, list_contracts, PromptContract
from providers import (
    GenerationResult,
    get_provider,
    get_available_provider,
    list_providers,
    Provider,
)
from validators import (
    validate_output,
    ValidationResult,
    is_valid,
    get_errors,
    get_warnings,
)


# ---------------------------------------------------------------------------
# Audit record
# ---------------------------------------------------------------------------

@dataclass
class GenerationAudit:
    """Complete audit record for a single content generation.

    Attributes:
        result: The provider's generation result (text, cost, tokens).
        validation_results: All validation rule outcomes.
        fingerprint_name: Which fingerprint was used.
        contract_name: Which prompt contract was used.
        contract_version: The contract version (for replay).
        system_prompt: The rendered system prompt sent to the model.
        user_prompt: The rendered user prompt sent to the model.
        errors: Validation errors (severity=error).
        warnings: Validation warnings (severity=warning).
    """
    result: GenerationResult
    validation_results: list[ValidationResult] = field(default_factory=list)
    fingerprint_name: str = ""
    contract_name: str = ""
    contract_version: int = 0
    system_prompt: str = ""
    user_prompt: str = ""
    errors: list[ValidationResult] = field(default_factory=list)
    warnings: list[ValidationResult] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "result": self.result.to_audit_dict(),
            "fingerprint_name": self.fingerprint_name,
            "contract_name": self.contract_name,
            "contract_version": self.contract_version,
            "is_valid": self.is_valid,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "validation_summary": [
                {"rule": r.rule, "passed": r.passed, "severity": r.severity, "detail": r.detail}
                for r in self.validation_results
            ],
        }


# ---------------------------------------------------------------------------
# Text generator
# ---------------------------------------------------------------------------

class TextGenerator:
    """Main text content generation engine.

    Orchestrates: BrandProfile + Fingerprint + PromptContract -> Provider -> Validation.

    Args:
        profile: The brand profile driving all generation.
        provider_name: Name of the AI provider to use (default: auto-detect).
        provider: A Provider instance directly (overrides provider_name).
        model: Model identifier to pass to the provider.
        max_tokens: Maximum tokens for generation.
        temperature: Sampling temperature (0.0-1.0).
        auto_validate: Whether to run validators automatically (default True).
    """

    def __init__(
        self,
        profile: BrandProfile,
        provider_name: str = "auto",
        provider: Provider | None = None,
        model: str | None = None,
        max_tokens: int = 500,
        temperature: float = 0.7,
        auto_validate: bool = True,
    ) -> None:
        if not profile.is_valid():
            errors = profile.validate()
            raise ValueError(f"Invalid brand profile: {'; '.join(errors)}")

        self._profile = profile
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._auto_validate = auto_validate

        # Resolve provider
        if provider is not None:
            self._provider = provider
        elif provider_name == "auto":
            resolved = get_available_provider()
            if resolved is None:
                raise RuntimeError(
                    "No AI provider available. Set OPENAI_API_KEY or OPENROUTER_API_KEY, "
                    "or pass a Provider instance directly."
                )
            self._provider = resolved
        else:
            self._provider = get_provider(provider_name)

    @property
    def provider_name(self) -> str:
        return self._provider.name

    @property
    def profile(self) -> BrandProfile:
        return self._profile

    def generate(
        self,
        contract_name: str,
        fingerprint_name: str,
        **contract_vars: Any,
    ) -> GenerationAudit:
        """Generate brand-aligned text content.

        Args:
            contract_name: Name of the prompt contract to use.
            fingerprint_name: Name of the communication fingerprint.
            **contract_vars: Variables to fill in the prompt contract template.

        Returns:
            GenerationAudit with the result, validation, and full provenance.
        """
        # 1. Resolve fingerprint and contract
        fingerprint = get_fingerprint(fingerprint_name)
        contract = get_contract(contract_name)

        # 2. Render prompts
        system_prompt = fingerprint.render_system_prompt(self._profile)
        # Inject fingerprint guidance into contract vars if not provided
        contract_vars.setdefault("fingerprint_name", fingerprint_name)
        contract_vars.setdefault("fingerprint_guidance", "; ".join(fingerprint.style_markers))
        user_prompt = contract.render(**contract_vars)

        # 3. Generate via provider
        result = self._provider.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=self._model,
            max_tokens=min(self._max_tokens, contract.max_output_tokens),
            temperature=self._temperature,
        )

        # 4. Attach provenance to result
        result.prompt_version = contract.version
        result.input_provenance = {
            "contract": contract_name,
            "fingerprint": fingerprint_name,
            "profile": self._profile.identity.name,
        }

        # 5. Validate output
        validation_results: list[ValidationResult] = []
        if self._auto_validate and result.success:
            validation_results = validate_output(
                result.text, self._profile, fingerprint_name
            )

        errors = get_errors(validation_results)
        warnings = get_warnings(validation_results)

        return GenerationAudit(
            result=result,
            validation_results=validation_results,
            fingerprint_name=fingerprint_name,
            contract_name=contract_name,
            contract_version=contract.version,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            errors=errors,
            warnings=warnings,
        )

    def generate_safe(
        self,
        contract_name: str,
        fingerprint_name: str,
        max_retries: int = 2,
        **contract_vars: Any,
    ) -> GenerationAudit:
        """Generate with automatic retry on validation failure.

        If the output has validation errors, re-generate up to max_retries times.
        Returns the best result (fewest errors) across all attempts.
        """
        best_audit: GenerationAudit | None = None

        for attempt in range(max_retries + 1):
            audit = self.generate(contract_name, fingerprint_name, **contract_vars)

            if best_audit is None or len(audit.errors) < len(best_audit.errors):
                best_audit = audit

            if audit.is_valid:
                return audit

        return best_audit  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _build_default_profile() -> BrandProfile:
    """Build a default brand profile for CLI usage."""
    return BrandProfile(
        identity=BrandIdentity(name="BrandOS", industry="Technology"),
        voice=BrandVoice(tone="professional", personality=("innovative", "trustworthy")),
        values=["quality", "innovation"],
        constraints=BrandConstraints(),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="BrandOS text content generation engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Contracts: " + ", ".join(list_contracts()) +
               "\nFingerprints: " + ", ".join(list_fingerprints()) +
               "\nProviders: " + ", ".join(list_providers()),
    )
    parser.add_argument("--contract", "-c", default="product-description",
                        help="Prompt contract name")
    parser.add_argument("--fingerprint", "-f", default="authority",
                        help="Communication fingerprint name")
    parser.add_argument("--provider", "-p", default="auto",
                        help="AI provider name (default: auto-detect)")
    parser.add_argument("--model", "-m", default=None,
                        help="Model identifier")
    parser.add_argument("--max-tokens", type=int, default=500)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--no-validate", action="store_true",
                        help="Skip output validation")
    parser.add_argument("--json", action="store_true",
                        help="Output as JSON")

    # Contract variables as --key value pairs
    parser.add_argument("--product-name", default="Example Product")
    parser.add_argument("--product-category", default="general")
    parser.add_argument("--key-notes", default="quality, innovation")
    parser.add_argument("--target-audience", default="professionals")
    parser.add_argument("--unique-selling-point", default="best in class quality")

    args = parser.parse_args()

    profile = _build_default_profile()

    contract_vars = {
        "product_name": args.product_name,
        "product_category": args.product_category,
        "key_notes": args.key_notes,
        "target_audience": args.target_audience,
        "unique_selling_point": args.unique_selling_point,
    }

    try:
        generator = TextGenerator(
            profile=profile,
            provider_name=args.provider,
            model=args.model,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
            auto_validate=not args.no_validate,
        )

        audit = generator.generate(args.contract, args.fingerprint, **contract_vars)

        if args.json:
            print(json.dumps(audit.to_dict(), indent=2))
        else:
            print(f"Provider: {audit.result.provider} / {audit.result.model}")
            print(f"Contract: {audit.contract_name} v{audit.contract_version}")
            print(f"Fingerprint: {audit.fingerprint_name}")
            print(f"Tokens: {audit.result.tokens_in} in / {audit.result.tokens_out} out")
            print(f"Cost: ${audit.result.cost_usd:.6f}")
            print(f"Latency: {audit.result.latency_ms}ms")
            print(f"Valid: {audit.is_valid} ({len(audit.errors)} errors, {len(audit.warnings)} warnings)")
            print("---")
            print(audit.result.text)
            if audit.validation_results:
                print("---")
                print("Validation:")
                for vr in audit.validation_results:
                    status = "PASS" if vr.passed else vr.severity.upper()
                    print(f"  [{status}] {vr.rule}: {vr.detail}")

        sys.exit(0 if audit.result.success else 1)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
