# Brand Knowledge Layer Schema

**Task:** BOS-68 / BRAND-001  
**Status:** Complete  
**Last Updated:** 2026-07-27

## Overview

The Brand Knowledge Layer is the core data model that organizes all brand-related
intelligence in the BrandOS platform. It serves as the single source of truth for
brand identity, audience, competitive landscape, content strategy, and messaging.

## Design Principles

1. **Normalized** — No redundant or conflicting definitions. Each concept lives in
   exactly one place.
2. **User vs. Inferred Separation** — User-provided brand truth is explicitly
   separated from AI-inferred/discovered signals.
3. **Versioned** — Brand evolves. Every knowledge snapshot is versioned with full
   audit trail.
4. **Importable/Exportable** — Full JSON serialization for audit, migration, and
   backup.
5. **Queryable** — Each layer is independently queryable and relates to specific
   extraction or user input.

## Architecture

```
BrandKnowledge (root)
├── brandIdentity          Layer 1: Brand Identity
│   ├── voice
│   ├── values
│   ├── positioning
│   └── visual
├── audienceSegments[]     Layer 2: Audience Segmentation
├── competitiveLandscape   Layer 3: Competitive Landscape
│   ├── competitors[]
│   └── differentiators
├── contentPillars         Layer 4: Content Pillars & Themes
│   ├── pillars[]
│   └── themes[]
├── messagingHierarchy     Layer 5: Messaging Hierarchy
│   ├── primaryMessage
│   ├── supportingMessages[]
│   └── proofPoints[]
└── productMarketFit       Layer 6: Product-Market Fit Narrative
    ├── problemStatement
    ├── solution
    ├── targetMarket
    └── uniqueValue
```

## Data Model

### Root: BrandKnowledge

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `schemaVersion` | `string` | ✅ | Semantic version (e.g. `"1.0.0"`) |
| `brandId` | `string` | ✅ | UUID of the brand |
| `workspaceId` | `string` | ✅ | UUID of the workspace (tenant isolation) |
| `version` | `number` | ✅ | Monotonic version counter |
| `createdAt` | `string` (ISO 8601) | ✅ | Creation timestamp |
| `updatedAt` | `string` (ISO 8601) | ✅ | Last update timestamp |
| `createdBy` | `string` | ✅ | Actor UUID or `"system"` |
| `source` | `enum` | ✅ | `"user"`, `"inferred"`, `"mixed"` |
| `status` | `enum` | ✅ | `"draft"`, `"active"`, `"archived"` |
| `brandIdentity` | `BrandIdentity` | ✅ | Layer 1 |
| `audienceSegments` | `AudienceSegment[]` | ✅ | Layer 2 (can be empty) |
| `competitiveLandscape` | `CompetitiveLandscape` | ✅ | Layer 3 |
| `contentPillars` | `ContentPillars` | ✅ | Layer 4 |
| `messagingHierarchy` | `MessagingHierarchy` | ✅ | Layer 5 |
| `productMarketFit` | `ProductMarketFit` | ✅ | Layer 6 |
| `metadata` | `Record<string, unknown>` | ❌ | Extensible metadata |

### Layer 1: BrandIdentity

Organizes brand voice, values, positioning, and visual identity.

#### BrandVoice

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `tone` | `string` | ✅ | Overall tone (e.g. "professional yet approachable") |
| `personality` | `string[]` | ✅ | Brand personality traits |
| `language` | `string` | ✅ | Primary language code (e.g. `"en"`) |
| `doSay` | `string[]` | ❌ | Words/phrases the brand uses |
| `dontSay` | `string[]` | ❌ | Words/phrases the brand avoids |
| `examples` | `VoiceExample[]` | ❌ | Sample copy demonstrating the voice |

#### VoiceExample

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `context` | `string` | ✅ | Where this example applies |
| `text` | `string` | ✅ | The example copy |
| `source` | `DataOrigin` | ✅ | User-provided or inferred |

#### BrandValues

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `core` | `ValueItem[]` | ✅ | Core brand values |
| `mission` | `string` | ❌ | Mission statement |
| `vision` | `string` | ❌ | Vision statement |

#### ValueItem

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `string` | ✅ | Value name |
| `description` | `string` | ✅ | What this value means |
| `source` | `DataOrigin` | ✅ | User-provided or inferred |

#### BrandPositioning

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `statement` | `string` | ✅ | Positioning statement |
| `category` | `string` | ✅ | Market category |
| `differentiator` | `string` | ✅ | Key differentiator |
| `targetAudience` | `string` | ✅ | Who the brand serves |
| `source` | `DataOrigin` | ✅ | User-provided or inferred |

#### BrandVisual

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `primaryColor` | `string` | ❌ | Hex color code |
| `secondaryColor` | `string` | ❌ | Hex color code |
| `logoUrl` | `string` | ❌ | URL or path to logo |
| `fonts` | `FontSpec[]` | ❌ | Typography specifications |
| `imageryStyle` | `string` | ❌ | Description of imagery style |

#### FontSpec

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `string` | ✅ | Font family name |
| `usage` | `string` | ✅ | Where used (heading, body, etc.) |
| `weight` | `string` | ❌ | Font weight(s) |
| `source` | `enum` | ✅ | `"google"`, `"adobe"`, `"custom"`, `"system"` |

### Layer 2: AudienceSegment[]

Each segment describes a target audience group.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `string` | ✅ | Segment UUID |
| `name` | `string` | ✅ | Segment name |
| `description` | `string` | ✅ | Who they are |
| `demographics` | `Demographics` | ❌ | Age, gender, income, etc. |
| `psychographics` | `Psychographics` | ❌ | Values, interests, lifestyle |
| `painPoints` | `string[]` | ✅ | Problems this segment faces |
| `goals` | `string[]` | ✅ | What this segment wants |
| `channels` | `string[]` | ❌ | Where to reach them |
| `source` | `DataOrigin` | ✅ | User-provided or inferred |
| `priority` | `enum` | ✅ | `"primary"`, `"secondary"`, `"tertiary"` |

#### Demographics

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `ageRange` | `string` | ❌ | e.g. `"25-44"` |
| `gender` | `string` | ❌ | Gender focus |
| `income` | `string` | ❌ | Income bracket |
| `location` | `string[]` | ❌ | Geographic regions |
| `education` | `string` | ❌ | Education level |

#### Psychographics

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `values` | `string[]` | ❌ | Core values |
| `interests` | `string[]` | ❌ | Hobbies and interests |
| `lifestyle` | `string` | ❌ | Lifestyle description |
| `behaviorPatterns` | `string[]` | ❌ | Buying/usage patterns |

### Layer 3: CompetitiveLandscape

Maps competitors and brand differentiators.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `competitors` | `Competitor[]` | ✅ | Known competitors |
| `differentiators` | `Differentiator[]` | ✅ | Brand's unique advantages |
| `marketPosition` | `string` | ❌ | Where brand sits in the market |

#### Competitor

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `string` | ✅ | Competitor UUID |
| `name` | `string` | ✅ | Competitor name |
| `url` | `string` | ❌ | Website URL |
| `description` | `string` | ✅ | What they do |
| `strengths` | `string[]` | ❌ | Their strengths |
| `weaknesses` | `string[]` | ❌ | Their weaknesses |
| `overlap` | `string` | ❌ | Where they overlap with this brand |
| `source` | `DataOrigin` | ✅ | User-provided or inferred |

#### Differentiator

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `string` | ✅ | Differentiator name |
| `description` | `string` | ✅ | What makes the brand unique |
| `evidence` | `string[]` | ❌ | Supporting evidence |
| `source` | `DataOrigin` | ✅ | User-provided or inferred |

### Layer 4: ContentPillars

Content strategy organized by pillars and themes.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `pillars` | `Pillar[]` | ✅ | Content pillars |
| `themes` | `Theme[]` | ✅ | Recurring themes |
| `contentMix` | `ContentMix` | ❌ | Content type distribution |

#### Pillar

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `string` | ✅ | Pillar UUID |
| `name` | `string` | ✅ | Pillar name |
| `description` | `string` | ✅ | What this pillar covers |
| `keywords` | `string[]` | ❌ | Associated keywords |
| `priority` | `number` | ✅ | 1 = highest priority |
| `source` | `DataOrigin` | ✅ | User-provided or inferred |

#### Theme

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `string` | ✅ | Theme UUID |
| `name` | `string` | ✅ | Theme name |
| `description` | `string` | ✅ | What this theme is about |
| `relatedPillars` | `string[]` | ✅ | Pillar IDs this theme supports |
| `frequency` | `enum` | ✅ | `"daily"`, `"weekly"`, `"monthly"`, `"seasonal"` |
| `source` | `DataOrigin` | ✅ | User-provided or inferred |

#### ContentMix

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `distribution` | `Record<string, number>` | ✅ | Content type → percentage (e.g. `{"educational": 40, "promotional": 20}`) |
| `platforms` | `string[]` | ❌ | Target platforms |

### Layer 5: MessagingHierarchy

Structured messaging from top-level down to proof points.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `primaryMessage` | `Message` | ✅ | The single most important message |
| `supportingMessages` | `Message[]` | ✅ | Supporting messages |
| `proofPoints` | `ProofPoint[]` | ✅ | Evidence backing the messages |
| `callsToAction` | `CallToAction[]` | ❌ | Primary CTAs |

#### Message

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `string` | ✅ | Message UUID |
| `text` | `string` | ✅ | The message text |
| `audience` | `string` | ❌ | Target segment ID |
| `context` | `string` | ❌ | When/where to use |
| `source` | `DataOrigin` | ✅ | User-provided or inferred |

#### ProofPoint

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `string` | ✅ | Proof point UUID |
| `claim` | `string` | ✅ | The claim being supported |
| `evidence` | `string` | ✅ | Supporting evidence |
| `type` | `enum` | ✅ | `"statistic"`, `"testimonial"`, `"case-study"`, `"award"`, `"certification"` |
| `source` | `DataOrigin` | ✅ | User-provided or inferred |

#### CallToAction

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `text` | `string` | ✅ | CTA text |
| `target` | `string` | ✅ | Where it leads |
| `priority` | `number` | ✅ | Display priority |

### Layer 6: ProductMarketFit

The brand's product-market fit narrative.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `problemStatement` | `string` | ✅ | The problem being solved |
| `solution` | `string` | ✅ | How the brand solves it |
| `targetMarket` | `string` | ✅ | Who benefits most |
| `uniqueValue` | `string` | ✅ | The unique value proposition |
| `traction` | `TractionMetric[]` | ❌ | Evidence of PMF |
| `customerQuotes` | `CustomerQuote[]` | ❌ | Customer testimonials |
| `source` | `DataOrigin` | ✅ | User-provided or inferred |

#### TractionMetric

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `metric` | `string` | ✅ | Metric name |
| `value` | `string` | ✅ | Current value |
| `trend` | `enum` | ✅ | `"growing"`, `"stable"`, `"declining"` |
| `period` | `string` | ❌ | Time period |

#### CustomerQuote

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `quote` | `string` | ✅ | Customer quote text |
| `author` | `string` | ❌ | Author name |
| `role` | `string` | ❌ | Author role/title |
| `source` | `DataOrigin` | ✅ | User-provided or inferred |

## Shared Types

### DataOrigin

Every field that can be user-provided or inferred carries a `source` discriminator:

```typescript
type DataOrigin = "user" | "inferred";
```

This enables the platform to:
- Display user-provided data with higher confidence
- Allow users to override inferred data
- Track which data came from AI analysis vs. manual input

### Versioning Strategy

Each `BrandKnowledge` record has:
- `version`: Monotonic counter (incremented on every save)
- `schemaVersion`: Semantic version of the schema format
- `createdAt` / `updatedAt`: Temporal tracking

Version history is stored separately (not inline) to keep the active record lean.
The platform maintains a `brand_knowledge_versions` table that snapshots the full
record on each update.

## Import/Export Format

The schema is fully serializable to JSON. Export produces a single JSON file
conforming to the TypeScript types. Import validates against the JSON Schema
(`schema.json`) before persisting.

```json
{
  "schemaVersion": "1.0.0",
  "brandId": "uuid",
  "workspaceId": "uuid",
  "version": 1,
  "createdAt": "2026-07-27T12:00:00Z",
  "updatedAt": "2026-07-27T12:00:00Z",
  "createdBy": "user-uuid",
  "source": "user",
  "status": "draft",
  "brandIdentity": { ... },
  "audienceSegments": [],
  "competitiveLandscape": { ... },
  "contentPillars": { ... },
  "messagingHierarchy": { ... },
  "productMarketFit": { ... }
}
```

## Database Schema (Planned)

The Brand Knowledge Layer maps to these database tables:

| Table | Purpose |
|-------|---------|
| `brand_knowledge` | Root record (one per brand) |
| `brand_knowledge_versions` | Version history snapshots |
| `audience_segments` | One row per segment |
| `competitors` | One row per competitor |
| `content_pillars` | One row per pillar |
| `content_themes` | One row per theme |
| `messaging_messages` | One row per message |
| `proof_points` | One row per proof point |

Foreign keys use `brand_knowledge.brand_id` → `brands.id` with workspace isolation
via `workspace_id`.

## Security Considerations

- All records are workspace-scoped (tenant isolation)
- No PII stored in brand knowledge (brand data, not personal data)
- Import validation prevents schema injection
- Version history is append-only (no deletion, only archival)
- Export requires workspace membership verification

## Downstream Dependencies

This schema feeds:

| Epic | Usage |
|------|-------|
| EPIC-07 | Brand Intelligence (extraction and synthesis) |
| EPIC-08 | Content Generation (voice-aware copy) |
| EPIC-09 | Image Generation (visual identity) |
| EPIC-10 | Social Media (audience-aware posting) |
| EPIC-11 | Analytics (brand consistency tracking) |
| EPIC-12 | Multi-language (localization context) |

## Files

| File | Purpose |
|------|---------|
| `docs/brand-knowledge-layer.md` | This document |
| `src/brand-knowledge/types.ts` | TypeScript type definitions |
| `src/brand-knowledge/schema.json` | JSON Schema for validation |
| `src/brand-knowledge/index.ts` | Barrel exports |
| `src/brand-knowledge/__tests__/schema.test.py` | Schema validation tests |
| `src/brand-knowledge/examples/minimal.json` | Minimal valid example |
| `src/brand-knowledge/examples/complete.json` | Complete example with all layers |
