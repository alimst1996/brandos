/**
 * Brand Knowledge Layer — Public API
 *
 * Re-exports all types and provides schema metadata.
 */

export type {
  // Shared
  DataOrigin,
  BrandKnowledgeStatus,
  AggregateSource,
  SegmentPriority,
  ThemeFrequency,
  ProofPointType,
  TrendDirection,
  FontSource,
  // Layer 1: Brand Identity
  BrandIdentity,
  BrandVoice,
  VoiceExample,
  BrandValues,
  ValueItem,
  BrandPositioning,
  BrandVisual,
  FontSpec,
  // Layer 2: Audience Segmentation
  AudienceSegment,
  Demographics,
  Psychographics,
  // Layer 3: Competitive Landscape
  CompetitiveLandscape,
  Competitor,
  Differentiator,
  // Layer 4: Content Pillars & Themes
  ContentPillars,
  Pillar,
  Theme,
  ContentMix,
  // Layer 5: Messaging Hierarchy
  MessagingHierarchy,
  Message,
  ProofPoint,
  CallToAction,
  // Layer 6: Product-Market Fit
  ProductMarketFit,
  TractionMetric,
  CustomerQuote,
  // Root
  BrandKnowledge,
  // Versioning
  BrandKnowledgeVersion,
  // Import/Export
  BrandKnowledgeExport,
  ImportValidationResult,
  ImportError,
  ImportWarning,
} from "./types";

/** Current schema version. */
export const SCHEMA_VERSION = "1.0.0" as const;

/** Schema identifier for JSON Schema. */
export const SCHEMA_ID =
  "https://brandos.ai/schemas/brand-knowledge/v1.0.0.json" as const;
