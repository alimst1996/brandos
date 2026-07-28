#!/usr/bin/env python3
"""
AI Run Logger for BrandOS Intelligence.

Records every AI run with: provider, model, prompt version,
input provenance, cost, output, and validation result.

Persistent JSONL-based audit trail. Every AI operation MUST
log through this module.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class AIRunRecord:
    """A single AI run record for the audit trail."""
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # Provider info
    provider: str = ""          # e.g. "openai", "openrouter", "anthropic"
    model: str = ""             # e.g. "gpt-4o", "claude-sonnet-4"

    # Prompt info
    prompt_contract_id: str = ""
    prompt_version: str = ""
    system_prompt_hash: str = ""
    user_prompt: str = ""

    # Input provenance
    brand_name: str = ""
    fingerprint_type: str = ""
    content_type: str = ""
    source_urls: list[str] = field(default_factory=list)

    # Output
    raw_output: str = ""
    parsed_output: dict[str, Any] = field(default_factory=dict)

    # Cost tracking
    input_tokens: int = 0
    output_tokens: int = 0
    total_cost_usd: float = 0.0

    # Validation
    validation_passed: bool = False
    validation_errors: list[str] = field(default_factory=list)

    # Status
    status: str = "pending"  # pending, success, failed, validation_failed

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


class RunLogger:
    """
    Persistent AI run logger using JSONL format.

    Each run is appended as a single JSON line to the log file.
    This ensures atomic writes and easy streaming/analysis.
    """

    def __init__(self, log_dir: str | Path | None = None):
        if log_dir is None:
            log_dir = Path.home() / ".brandos" / "ai_runs"
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "runs.jsonl"

    def log(self, record: AIRunRecord) -> str:
        """
        Append a run record to the log.

        Returns the run_id.
        """
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(record.to_json() + "\n")
        return record.run_id

    def log_run(
        self,
        provider: str,
        model: str,
        contract_id: str,
        prompt_version: str,
        user_prompt: str,
        brand_name: str = "",
        fingerprint_type: str = "",
        content_type: str = "",
        source_urls: list[str] | None = None,
    ) -> AIRunRecord:
        """
        Create and log a new run record (pre-execution).

        Returns the record for later update with output/validation.
        """
        import hashlib
        record = AIRunRecord(
            provider=provider,
            model=model,
            prompt_contract_id=contract_id,
            prompt_version=prompt_version,
            system_prompt_hash=hashlib.sha256(contract_id.encode()).hexdigest()[:16],
            user_prompt=user_prompt,
            brand_name=brand_name,
            fingerprint_type=fingerprint_type,
            content_type=content_type,
            source_urls=source_urls or [],
            status="pending",
        )
        self.log(record)
        return record

    def update_run(self, record: AIRunRecord) -> str:
        """Append the updated record (output + validation)."""
        return self.log(record)

    def read_runs(self, limit: int = 100) -> list[AIRunRecord]:
        """Read the most recent run records."""
        if not self.log_file.exists():
            return []

        records = []
        with open(self.log_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        data = json.loads(line)
                        records.append(AIRunRecord(**data))
                    except (json.JSONDecodeError, TypeError):
                        continue

        return records[-limit:]

    def get_run(self, run_id: str) -> AIRunRecord | None:
        """Get a specific run by ID."""
        if not self.log_file.exists():
            return None

        with open(self.log_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        data = json.loads(line)
                        if data.get("run_id") == run_id:
                            return AIRunRecord(**data)
                    except (json.JSONDecodeError, TypeError):
                        continue
        return None

    def stats(self) -> dict[str, Any]:
        """Get summary statistics."""
        runs = self.read_runs(limit=10000)
        if not runs:
            return {"total_runs": 0}

        providers = {}
        models = {}
        total_cost = 0.0
        success = 0
        failed = 0

        for r in runs:
            providers[r.provider] = providers.get(r.provider, 0) + 1
            models[r.model] = models.get(r.model, 0) + 1
            total_cost += r.total_cost_usd
            if r.status == "success":
                success += 1
            elif r.status in ("failed", "validation_failed"):
                failed += 1

        return {
            "total_runs": len(runs),
            "success": success,
            "failed": failed,
            "total_cost_usd": round(total_cost, 4),
            "providers": providers,
            "models": models,
        }
