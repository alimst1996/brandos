"""BIZ-005 Prompt contract — structured prompt template for synthesis.

Prompt versioning is mandatory. Every call must record the version used.
"""

from __future__ import annotations

import json
from typing import Any

# ---------------------------------------------------------------------------
# Prompt version
# ---------------------------------------------------------------------------

PROMPT_VERSION = "synthesis-v1.0.0"

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

SYNTHESIS_PROMPT_V1 = """You are a marketing strategy analyst. Given a business profile, generate distinct marketing angle recommendations.

## Business Profile
{business_json}

## Instructions
1. Generate exactly {num_angles} distinct marketing angles.
2. Each angle must target a DIFFERENT customer segment or use case.
3. Each angle must have a unique differentiation claim.
4. Each angle must include at least 2 evidence items with confidence scores.
5. Each angle must have competitive positioning against named competitors.
6. Provide exactly 3 communication fingerprints (tone + persona types).
7. Output ONLY valid JSON matching the schema below. No prose.

## Output Schema
{{
  "angles": [
    {{
      "id": "angle-1",
      "title": "string — short compelling title",
      "description": "string — 1-2 sentence description of the angle",
      "target_segment": "string — who this angle targets",
      "differentiation": "string — what makes this angle unique",
      "competitive_positioning": {{
        "vs_competitors": [
          {{
            "competitor": "string — competitor name",
            "advantage": "string — our advantage over them",
            "evidence": "string — supporting evidence"
          }}
        ],
        "market_position": "string — e.g. 'premium alternative'",
        "moat": "string — defensible advantage"
      }},
      "evidence": [
        {{
          "type": "market_data|customer_insight|competitive_analysis|brand_asset|social_proof",
          "source": "string — where this evidence comes from",
          "confidence": 0.0-1.0,
          "detail": "string — specific evidence detail"
        }}
      ],
      "risk_level": "low|medium|high",
      "estimated_impact": "high|medium|low"
    }}
  ],
  "communication_fingerprints": [
    {{
      "persona_type": "authoritative|empathetic|aspirational|disruptive|minimalist|storyteller|educator|community_builder|premium_exclusive|playful",
      "tone": "string — description of the tone",
      "key_phrases": ["string — example phrases"],
      "channels": ["instagram|linkedin|twitter|tiktok|email|website|blog|youtube|podcast|paid_ads"],
      "content_style": "string — how content should look/feel"
    }}
  ]
}}

## Quality Rules
- Angles must be genuinely distinct (different segments, different claims).
- Evidence confidence must reflect actual certainty (don't inflate).
- Competitive advantages must be specific and defensible.
- Communication fingerprints are NOT fictional customer identities — they are communication style guides.
- No made-up metrics, customer names, or biographical details.
"""

# ---------------------------------------------------------------------------
# Prompt renderer
# ---------------------------------------------------------------------------


def render_prompt(
    business: dict[str, Any],
    num_angles: int = 3,
    prompt_version: str = PROMPT_VERSION,
) -> str:
    """Render the synthesis prompt with business data.

    Args:
        business: Business profile as dict.
        num_angles: Number of angles to generate (default 3).
        prompt_version: Version tag (for tracking, not interpolation).

    Returns:
        Rendered prompt string.
    """
    business_json = json.dumps(business, indent=2, ensure_ascii=False)
    return SYNTHESIS_PROMPT_V1.format(
        business_json=business_json,
        num_angles=num_angles,
    )
