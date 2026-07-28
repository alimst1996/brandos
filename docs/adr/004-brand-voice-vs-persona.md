# ADR-004: Brand Voice vs. Persona Separation

## Status

Accepted

## Date

2026-07-24

## Context

BrandOS needs to model two distinct concepts that are often conflated in
marketing tools:

1. **Brand Voice** — how the brand communicates: tone, vocabulary, style,
   values, visual language. This is an intrinsic property of the brand itself.

2. **Persona** — who the brand is speaking to: audience demographics,
   psychographics, preferences, behavior patterns. This is an extrinsic
   property of the target audience.

Conflating these leads to problems:
- Changing the audience (persona) shouldn't require rewriting brand guidelines.
- The same brand voice may target multiple personas (e.g., a luxury perfume
  brand speaking to both collectors and gift buyers).
- Content generation needs both — the voice to write *like* the brand, and
  the persona to write *for* the audience.

## Decision

Model Brand Voice and Persona as **separate entities** with independent
lifecycle and versioning.

### Brand Voice entity:
- `tone`: formal, casual, playful, authoritative, etc.
- `vocabulary`: preferred terms, banned terms, domain jargon
- `style`: sentence length, punctuation habits, emoji usage
- `values`: what the brand stands for (used for content alignment)
- `visualLanguage`: color palette references, imagery style

### Persona entity:
- `name`: human-readable label (e.g., "Luxury Collector", "Gift Buyer")
- `demographics`: age range, location, income level
- `psychographics`: interests, values, lifestyle markers
- `channels`: where this persona is most active
- `painPoints`: what problems the brand solves for this persona

### Relationship:
- A workspace has one Brand Voice (the brand doesn't change per campaign).
- A workspace has one or more Personas.
- Content generation selects both: Brand Voice + target Persona.
- Campaign analytics can track performance per Persona.

## Consequences

### Positive

- Clear separation of concerns: brand identity vs. audience understanding.
- A brand can target multiple personas without duplicating voice definitions.
- Content generation has two clean inputs, making prompts more predictable.
- Persona changes (new audience segment) don't require voice rework.

### Negative

- Two entities to manage instead of one (slightly more UI complexity).
- Engineers must remember to pass both to content generation pipelines.
- If a brand has only one persona, the separation feels like overhead.

### Neutral

- This is a data modeling decision. The schemas are independent; each can
  evolve without breaking the other.
- The Brand Voice is effectively a singleton per workspace. This could be
  enforced at the database level (unique constraint on workspaceId) or at
  the application level.

## Alternatives Considered

| Alternative | Why rejected |
|-------------|--------------|
| Single "Brand Profile" combining voice + persona | Conflates two concerns; changing audience requires rewriting brand data |
| Voice-only (no persona modeling) | Content generation cannot adapt tone for different audience segments |
| Persona-only (voice derived from persona) | Voice is a brand property, not an audience property |

## Links

- Related Jira issues: FOUND-007 (Brand Voice schema), FOUND-008 (Persona schema)
