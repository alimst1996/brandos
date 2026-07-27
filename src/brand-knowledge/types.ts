/**
 * Brand Knowledge Layer — TypeScript type definitions
 *
 * Task: BOS-68 / BRAND-001
 * Schema Version: 1.0.0
 *
 * This is the canonical type definition for the Brand Knowledge data model.
 * All types are designed for JSON serialization and database mapping.
 */

// ---------------------------------------------------------------------------
// Shared types
// ---------------------------------------------------------------------------

/**
 * Every field that can be user-provided or inferred carries a source discriminator.
 * Enables the platform to:
 * - Display user-provided data with higher confidence
 * - Allow users to override inferred data
 * - Track which data came from AI analysis vs. manual input
 */
export type DataOrigin = "user" | "inferred";

/**
 * Status of a brand knowledge record.
 */
export type BrandKnowledgeStatus = "draft" | "active" | "archived";

/**
 * Aggregate source when a record mixes user and inferred data.
 */
export type AggregateSource = "user" | "inferred" | "mixed";

/**
 * Audience segment priority levels.
 */
export type SegmentPriority = "primary" | "secondary" | "tertiary";

/**
 * Theme frequency for content scheduling.
 */
export type ThemeFrequency = "daily" | "weekly" | "monthly" | "seasonal";

/**
 * Proof point evidence types.
 */
export type ProofPointType =
  | "statistic"
  | "testimonial"
  | "case-study"
  | "award"
  | "certification";

/**
 * Traction metric trend direction.
 */
export type TrendDirection = "growing" | "stable" | "declining";

/**
 * Font source specification.
 */
export type FontSource = "google" | "adobe" | "custom" | "system";

// ---------------------------------------------------------------------------
// Layer 1: Brand Identity
// ---------------------------------------------------------------------------

export interface VoiceExample {
  /** Where this example applies (e.g. "social media", "email subject"). */
  context: string;
  /** The example copy demonstrating the brand voice. */
  text: string;
  /** Whether this example was provided by the user or inferred by AI. */
  source: DataOrigin;
}

export interface BrandVoice {
  /** Overall tone (e.g. "professional yet approachable"). */
  tone: string;
  /** Brand personality traits. */
  personality: string[];
  /** Primary language code (e.g. "en", "fa"). */
  language: string;
  /** Words/phrases the brand uses. */
  doSay?: string[];
  /** Words/phrases the brand avoids. */
  dontSay?: string[];
  /** Sample copy demonstrating the voice. */
  examples?: VoiceExample[];
}

export interface ValueItem {
  /** Value name (e.g. "Sustainability", "Innovation"). */
  name: string;
  /** What this value means in the brand context. */
  description: string;
  /** Whether this value was provided by the user or inferred by AI. */
  source: DataOrigin;
}

export interface BrandValues {
  /** Core brand values. */
  core: ValueItem[];
  /** Mission statement. */
  mission?: string;
  /** Vision statement. */
  vision?: string;
}

export interface BrandPositioning {
  /** Full positioning statement. */
  statement: string;
  /** Market category (e.g. "luxury fragrance", "SaaS productivity"). */
  category: string;
  /** Key differentiator from competitors. */
  differentiator: string;
  /** Who the brand serves. */
  targetAudience: string;
  /** Whether this was provided by the user or inferred by AI. */
  source: DataOrigin;
}

export interface FontSpec {
  /** Font family name (e.g. "Inter", "Playfair Display"). */
  name: string;
  /** Where used (heading, body, accent, etc.). */
  usage: string;
  /** Font weight(s) (e.g. "400-700"). */
  weight?: string;
  /** Font source/provider. */
  source: FontSource;
}

export interface BrandVisual {
  /** Primary brand color as hex (e.g. "#1a1a2e"). */
  primaryColor?: string;
  /** Secondary brand color as hex. */
  secondaryColor?: string;
  /** URL or path to the brand logo. */
  logoUrl?: string;
  /** Typography specifications. */
  fonts?: FontSpec[];
  /** Description of imagery style (e.g. "minimalist, high-contrast"). */
  imageryStyle?: string;
}

export interface BrandIdentity {
  /** Brand voice and communication style. */
  voice: BrandVoice;
  /** Brand values and mission. */
  values: BrandValues;
  /** Market positioning. */
  positioning: BrandPositioning;
  /** Visual identity specifications. */
  visual: BrandVisual;
}

// ---------------------------------------------------------------------------
// Layer 2: Audience Segmentation
// ---------------------------------------------------------------------------

export interface Demographics {
  /** Age range (e.g. "25-44"). */
  ageRange?: string;
  /** Gender focus. */
  gender?: string;
  /** Income bracket (e.g. "$75k-$150k"). */
  income?: string;
  /** Geographic regions. */
  location?: string[];
  /** Education level. */
  education?: string;
}

export interface Psychographics {
  /** Core values that drive behavior. */
  values?: string[];
  /** Hobbies and interests. */
  interests?: string[];
  /** Lifestyle description. */
  lifestyle?: string;
  /** Buying/usage behavior patterns. */
  behaviorPatterns?: string[];
}

export interface AudienceSegment {
  /** Unique segment identifier (UUID). */
  id: string;
  /** Segment name (e.g. "Young Professionals"). */
  name: string;
  /** Who they are. */
  description: string;
  /** Demographic profile. */
  demographics?: Demographics;
  /** Psychographic profile. */
  psychographics?: Psychographics;
  /** Problems this segment faces. */
  painPoints: string[];
  /** What this segment wants to achieve. */
  goals: string[];
  /** Where to reach them (channels, platforms). */
  channels?: string[];
  /** Whether this segment was provided by the user or inferred by AI. */
  source: DataOrigin;
  /** Segment priority level. */
  priority: SegmentPriority;
}

// ---------------------------------------------------------------------------
// Layer 3: Competitive Landscape
// ---------------------------------------------------------------------------

export interface Competitor {
  /** Unique competitor identifier (UUID). */
  id: string;
  /** Competitor name. */
  name: string;
  /** Competitor website URL. */
  url?: string;
  /** What they do. */
  description: string;
  /** Their strengths. */
  strengths?: string[];
  /** Their weaknesses. */
  weaknesses?: string[];
  /** Where they overlap with this brand. */
  overlap?: string;
  /** Whether this was provided by the user or inferred by AI. */
  source: DataOrigin;
}

export interface Differentiator {
  /** Differentiator name. */
  name: string;
  /** What makes the brand unique. */
  description: string;
  /** Supporting evidence for this differentiator. */
  evidence?: string[];
  /** Whether this was provided by the user or inferred by AI. */
  source: DataOrigin;
}

export interface CompetitiveLandscape {
  /** Known competitors. */
  competitors: Competitor[];
  /** Brand's unique advantages. */
  differentiators: Differentiator[];
  /** Where the brand sits in the market landscape. */
  marketPosition?: string;
}

// ---------------------------------------------------------------------------
// Layer 4: Content Pillars & Themes
// ---------------------------------------------------------------------------

export interface Pillar {
  /** Unique pillar identifier (UUID). */
  id: string;
  /** Pillar name (e.g. "Education", "Behind the Scenes"). */
  name: string;
  /** What this pillar covers. */
  description: string;
  /** Associated keywords for content matching. */
  keywords?: string[];
  /** Priority (1 = highest). */
  priority: number;
  /** Whether this pillar was provided by the user or inferred by AI. */
  source: DataOrigin;
}

export interface Theme {
  /** Unique theme identifier (UUID). */
  id: string;
  /** Theme name (e.g. "Sustainability Monday"). */
  name: string;
  /** What this theme is about. */
  description: string;
  /** Pillar IDs this theme supports. */
  relatedPillars: string[];
  /** How often this theme recurs. */
  frequency: ThemeFrequency;
  /** Whether this theme was provided by the user or inferred by AI. */
  source: DataOrigin;
}

export interface ContentMix {
  /**
   * Content type distribution.
   * Keys are content types, values are percentages (0-100).
   * Example: { "educational": 40, "promotional": 20, "entertaining": 40 }
   */
  distribution: Record<string, number>;
  /** Target platforms for content distribution. */
  platforms?: string[];
}

export interface ContentPillars {
  /** Content pillars organizing the strategy. */
  pillars: Pillar[];
  /** Recurring content themes. */
  themes: Theme[];
  /** Content type distribution (optional). */
  contentMix?: ContentMix;
}

// ---------------------------------------------------------------------------
// Layer 5: Messaging Hierarchy
// ---------------------------------------------------------------------------

export interface Message {
  /** Unique message identifier (UUID). */
  id: string;
  /** The message text. */
  text: string;
  /** Target audience segment ID (optional). */
  audience?: string;
  /** When/where to use this message. */
  context?: string;
  /** Whether this message was provided by the user or inferred by AI. */
  source: DataOrigin;
}

export interface ProofPoint {
  /** Unique proof point identifier (UUID). */
  id: string;
  /** The claim being supported. */
  claim: string;
  /** Supporting evidence. */
  evidence: string;
  /** Type of evidence. */
  type: ProofPointType;
  /** Whether this was provided by the user or inferred by AI. */
  source: DataOrigin;
}

export interface CallToAction {
  /** CTA text (e.g. "Get Started", "Learn More"). */
  text: string;
  /** Where it leads (URL or route). */
  target: string;
  /** Display priority (1 = highest). */
  priority: number;
}

export interface MessagingHierarchy {
  /** The single most important message. */
  primaryMessage: Message;
  /** Supporting messages. */
  supportingMessages: Message[];
  /** Evidence backing the messages. */
  proofPoints: ProofPoint[];
  /** Primary calls to action. */
  callsToAction?: CallToAction[];
}

// ---------------------------------------------------------------------------
// Layer 6: Product-Market Fit
// ---------------------------------------------------------------------------

export interface TractionMetric {
  /** Metric name (e.g. "Monthly Active Users"). */
  metric: string;
  /** Current value (e.g. "10,000"). */
  value: string;
  /** Trend direction. */
  trend: TrendDirection;
  /** Time period (e.g. "Q2 2026"). */
  period?: string;
}

export interface CustomerQuote {
  /** Customer quote text. */
  quote: string;
  /** Author name. */
  author?: string;
  /** Author role/title. */
  role?: string;
  /** Whether this was provided by the user or inferred by AI. */
  source: DataOrigin;
}

export interface ProductMarketFit {
  /** The problem being solved. */
  problemStatement: string;
  /** How the brand solves it. */
  solution: string;
  /** Who benefits most. */
  targetMarket: string;
  /** The unique value proposition. */
  uniqueValue: string;
  /** Evidence of product-market fit. */
  traction?: TractionMetric[];
  /** Customer testimonials. */
  customerQuotes?: CustomerQuote[];
  /** Whether this was provided by the user or inferred by AI. */
  source: DataOrigin;
}

// ---------------------------------------------------------------------------
// Root: BrandKnowledge
// ---------------------------------------------------------------------------

export interface BrandKnowledge {
  /** Schema version (semantic versioning). */
  schemaVersion: string;
  /** Brand UUID. */
  brandId: string;
  /** Workspace UUID (tenant isolation). */
  workspaceId: string;
  /** Monotonic version counter (incremented on every save). */
  version: number;
  /** Creation timestamp (ISO 8601). */
  createdAt: string;
  /** Last update timestamp (ISO 8601). */
  updatedAt: string;
  /** Actor UUID or "system". */
  createdBy: string;
  /** Aggregate source: user, inferred, or mixed. */
  source: AggregateSource;
  /** Record status. */
  status: BrandKnowledgeStatus;
  /** Layer 1: Brand Identity. */
  brandIdentity: BrandIdentity;
  /** Layer 2: Audience Segmentation. */
  audienceSegments: AudienceSegment[];
  /** Layer 3: Competitive Landscape. */
  competitiveLandscape: CompetitiveLandscape;
  /** Layer 4: Content Pillars & Themes. */
  contentPillars: ContentPillars;
  /** Layer 5: Messaging Hierarchy. */
  messagingHierarchy: MessagingHierarchy;
  /** Layer 6: Product-Market Fit Narrative. */
  productMarketFit: ProductMarketFit;
  /** Extensible metadata (not validated against schema). */
  metadata?: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Version history types
// ---------------------------------------------------------------------------

export interface BrandKnowledgeVersion {
  /** Version number (matches BrandKnowledge.version). */
  version: number;
  /** Full snapshot of the BrandKnowledge record at this version. */
  snapshot: BrandKnowledge;
  /** Who made this change. */
  changedBy: string;
  /** When the change was made (ISO 8601). */
  changedAt: string;
  /** Optional description of what changed. */
  changeDescription?: string;
}

// ---------------------------------------------------------------------------
// Import/Export types
// ---------------------------------------------------------------------------

export interface BrandKnowledgeExport {
  /** Export format version. */
  exportVersion: "1.0";
  /** Export timestamp (ISO 8601). */
  exportedAt: string;
  /** The brand knowledge record. */
  brandKnowledge: BrandKnowledge;
  /** Version history (optional, included in full exports). */
  versions?: BrandKnowledgeVersion[];
}

export interface ImportValidationResult {
  /** Whether the import is valid. */
  valid: boolean;
  /** Validation errors (if any). */
  errors: ImportError[];
  /** Validation warnings (non-blocking). */
  warnings: ImportWarning[];
}

export interface ImportError {
  /** JSON path to the error. */
  path: string;
  /** Error message. */
  message: string;
  /** Error code for programmatic handling. */
  code: string;
}

export interface ImportWarning {
  /** JSON path to the warning. */
  path: string;
  /** Warning message. */
  message: string;
}
