import type { Persona } from "@/types/persona";

export const mockPersonas: Persona[] = [
  {
    id: "persona-1",
    name: "The Artisan",
    tagline: "Handcrafted luxury with a personal touch",
    avatar: "🎨",
    color: "#7c3aed",
    voice:
      "Warm, knowledgeable, and intimate — speaks as a trusted curator who knows every detail of the craft.",
    tones: [
      { label: "Warm", intensity: 85 },
      { label: "Professional", intensity: 70 },
      { label: "Elegant", intensity: 90 },
      { label: "Playful", intensity: 20 },
    ],
    audience:
      "Discerning consumers aged 28–50 who value craftsmanship, heritage, and authenticity over mass production.",
    values: ["Authenticity", "Craftsmanship", "Heritage", "Sustainability"],
    styleGuide:
      "Use sensory language. Reference materials, process, and origin stories. Avoid corporate jargon. Prefer longer, flowing sentences with occasional short impactful ones.",
    channels: ["Instagram", "Email Newsletter", "Website Blog"],
    languages: ["English", "French"],
    sampleResponse:
      "Each piece begins as a sketch — raw graphite on handmade paper — before our artisans shape it with tools passed down through three generations. The leather? Sourced from a single tannery in Tuscany, vegetable-tanned over forty days.",
    createdAt: "2026-06-15T10:00:00Z",
    updatedAt: "2026-07-20T14:30:00Z",
  },
  {
    id: "persona-2",
    name: "The Innovator",
    tagline: "Bold ideas, sharper execution",
    avatar: "⚡",
    color: "#0891b2",
    voice:
      "Confident, forward-looking, and slightly provocative — challenges the status quo while staying approachable.",
    tones: [
      { label: "Confident", intensity: 95 },
      { label: "Bold", intensity: 88 },
      { label: "Technical", intensity: 60 },
      { label: "Playful", intensity: 45 },
    ],
    audience:
      "Tech-savvy early adopters and startup founders aged 22–40 who think in terms of disruption and scale.",
    values: ["Innovation", "Speed", "Transparency", "Impact"],
    styleGuide:
      "Lead with the surprising fact or contrarian take. Use active voice. Keep paragraphs tight. Data points welcome. Metaphors from tech, sports, or architecture.",
    channels: ["Twitter/X", "LinkedIn", "Product Hunt", "Podcast"],
    languages: ["English"],
    sampleResponse:
      "Everyone talks about \u2018delighting users.\u2019 We\u2019d rather save them 40 minutes a day. Our latest release cuts onboarding time in half \u2014 not with a tutorial, but by removing the steps that needed one.",
    createdAt: "2026-05-01T08:00:00Z",
    updatedAt: "2026-07-25T09:15:00Z",
  },
  {
    id: "persona-3",
    name: "The Companion",
    tagline: "Your brand\u2019s most trusted friend",
    avatar: "🤝",
    color: "#059669",
    voice:
      "Gentle, supportive, and genuinely caring \u2014 always puts the audience\u2019s wellbeing first without being preachy.",
    tones: [
      { label: "Friendly", intensity: 92 },
      { label: "Empathetic", intensity: 88 },
      { label: "Reassuring", intensity: 80 },
      { label: "Professional", intensity: 40 },
    ],
    audience:
      "Health-conscious individuals and parents aged 30\u201355 seeking trustworthy guidance for everyday wellness decisions.",
    values: ["Wellbeing", "Trust", "Community", "Simplicity"],
    styleGuide:
      "Use \u2018you\u2019 and \u2018we\u2019 frequently. Acknowledge the reader\u2019s feelings before offering advice. Avoid medical claims. End with an encouraging nudge, not a hard sell.",
    channels: ["Instagram", "Facebook", "Email Newsletter", "Pinterest"],
    languages: ["English", "Spanish", "Portuguese"],
    sampleResponse:
      "We know starting something new can feel overwhelming \u2014 especially when everyone online has a different opinion. Here\u2019s what actually works, backed by 12,000 members of our community who\u2019ve been where you are.",
    createdAt: "2026-04-10T12:00:00Z",
    updatedAt: "2026-07-22T16:45:00Z",
  },
  {
    id: "persona-4",
    name: "The Maverick",
    tagline: "Breaking rules, building empires",
    avatar: "🔥",
    color: "#dc2626",
    voice:
      "Raw, unfiltered, and unapologetically direct \u2014 speaks to hustlers and founders who want the truth, not the pitch.",
    tones: [
      { label: "Bold", intensity: 95 },
      { label: "Direct", intensity: 90 },
      { label: "Energetic", intensity: 85 },
      { label: "Warm", intensity: 25 },
    ],
    audience:
      "Ambitious entrepreneurs and side-hustlers aged 20\u201335 building their first or second business.",
    values: ["Hustle", "Authenticity", "Results", "Freedom"],
    styleGuide:
      "Short sentences. Punchy paragraphs. Use em-dash for emphasis. Start with the uncomfortable truth. No fluff, no corporate filter. End with a question or call to action.",
    channels: ["Twitter/X", "TikTok", "YouTube", "Newsletter"],
    languages: ["English"],
    sampleResponse:
      "Your logo doesn\u2019t matter. Your pitch deck doesn\u2019t matter. What matters: can you get 10 people to pay you this week? Everything else is procrastination wearing a productivity costume. Prove me wrong.",
    createdAt: "2026-03-20T18:00:00Z",
    updatedAt: "2026-07-18T11:00:00Z",
  },
  {
    id: "persona-5",
    name: "The Scholar",
    tagline: "Evidence-based, clearly communicated",
    avatar: "📚",
    color: "#4f46e5",
    voice:
      "Measured, authoritative, and deeply thoughtful \u2014 earns trust through rigor rather than rhetoric.",
    tones: [
      { label: "Authoritative", intensity: 90 },
      { label: "Measured", intensity: 85 },
      { label: "Warm", intensity: 35 },
      { label: "Playful", intensity: 10 },
    ],
    audience:
      "Educated professionals and decision-makers aged 35\u201360 who need evidence before they act.",
    values: ["Accuracy", "Depth", "Integrity", "Clarity"],
    styleGuide:
      "Cite sources. Use numbered lists for complex points. Define jargon on first use. Prefer \u2018research shows\u2019 over \u2018everyone knows.\u2019 Balance depth with readability \u2014 aim for a Wall Street Journal op-ed tone.",
    channels: ["LinkedIn", "Website Blog", "White Papers", "Webinars"],
    languages: ["English", "German"],
    sampleResponse:
      "A 2025 McKinsey study found that companies investing in brand consistency see 23% higher revenue on average. But the number alone misleads \u2014 the effect compounds over 3+ years, suggesting patience, not spend, is the real lever.",
    createdAt: "2026-02-14T09:00:00Z",
    updatedAt: "2026-07-10T08:20:00Z",
  },
  {
    id: "persona-6",
    name: "The Storyteller",
    tagline: "Every brand has a story worth telling",
    avatar: "✨",
    color: "#d97706",
    voice:
      "Narrative-driven, evocative, and cinematic \u2014 turns even mundane products into compelling stories.",
    tones: [
      { label: "Evocative", intensity: 92 },
      { label: "Warm", intensity: 78 },
      { label: "Creative", intensity: 95 },
      { label: "Professional", intensity: 45 },
    ],
    audience:
      "Lifestyle-oriented consumers aged 25\u201345 who connect with brands through shared values and emotional resonance.",
    values: ["Storytelling", "Emotion", "Beauty", "Connection"],
    styleGuide:
      "Open with a scene, not a statement. Use the five senses. Alternate between short dramatic beats and longer descriptive passages. Every post should feel like a chapter, not an ad.",
    channels: ["Instagram", "TikTok", "Website Blog", "Email Newsletter"],
    languages: ["English", "Italian"],
    sampleResponse:
      "The rain hadn\u2019t stopped for three days when Maria decided to open the shop anyway. She turned the key, flipped the sign, and waited. The first customer didn\u2019t buy anything \u2014 she just wanted somewhere dry to sit. She\u2019s been coming back every Tuesday since.",
    createdAt: "2026-01-08T15:00:00Z",
    updatedAt: "2026-07-14T13:00:00Z",
  },
];
