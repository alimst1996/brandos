"""10+ real business test fixtures for BIZ-005 validation.

Each fixture is a dict ready for BusinessProfile.from_dict().
These are real businesses with realistic data — not invented.
"""

FIXTURES: list[dict] = [
    # 1. Evardly 1909 — luxury minimalist perfume (user's own brand)
    {
        "id": "evardly-1909",
        "name": "Evardly 1909",
        "industry": "Luxury Fragrance",
        "description": "Luxury minimalist perfume house blending Persian heritage with modern aesthetics. Hand-crafted scents using rare ingredients sourced from Iran and the Middle East.",
        "products": ["Eau de Parfum", "Cologne", "Discovery Set", "Gift Box"],
        "target_audience": "Affluent 25-45 who value artisanal quality and cultural depth over mass-market brands",
        "unique_value_proposition": "Persian-inspired luxury fragrances with 100+ years of heritage storytelling, minimalist packaging, and rare natural ingredients unavailable in Western perfumery",
        "competitors": ["Le Labo", "Byredo", "Maison Francis Kurkdjian", "Diptyque"],
        "brand_voice": "Elegant, understated, culturally rich, poetic",
        "channels": ["instagram", "website", "email", "podcast"],
        "pricing_tier": "premium",
        "geographic_focus": "Global — strongest in Middle East and Europe",
        "stage": "growth",
    },
    # 2. Allbirds — sustainable footwear
    {
        "id": "allbirds",
        "name": "Allbirds",
        "industry": "Sustainable Footwear",
        "description": "Eco-friendly footwear brand using natural materials like merino wool, eucalyptus fiber, and sugarcane-based soles. Carbon-neutral certified.",
        "products": ["Wool Runners", "Tree Dashers", "Mizzle (weather-resistant)", "Kids shoes"],
        "target_audience": "Environmentally conscious professionals 25-45 who want comfort without sacrificing sustainability",
        "unique_value_proposition": "The world's most comfortable shoes made from the world's most sustainable materials — carbon footprint labeled on every product",
        "competitors": ["Nike (Move to Zero)", "Veja", "On Running", "Rothy's"],
        "brand_voice": "Friendly, transparent, approachable, earnest",
        "channels": ["instagram", "tiktok", "email", "website", "paid_ads"],
        "pricing_tier": "mid",
        "geographic_focus": "US, UK, Australia, EU",
        "stage": "established",
    },
    # 3. Notion — productivity software
    {
        "id": "notion",
        "name": "Notion",
        "industry": "Productivity Software",
        "description": "All-in-one workspace combining notes, docs, wikis, project management, and databases. Highly customizable with templates and integrations.",
        "products": ["Notion Free", "Notion Plus", "Notion Business", "Notion Enterprise", "Notion AI"],
        "target_audience": "Knowledge workers, startups, and teams who want a unified workspace instead of juggling 5+ tools",
        "unique_value_proposition": "Replace your docs, wiki, project manager, and database with one infinitely flexible tool — build the workspace you actually need",
        "competitors": ["Confluence", "Coda", "Obsidian", "Monday.com", "Asana"],
        "brand_voice": "Clean, empowering, creative, slightly nerdy",
        "channels": ["twitter", "youtube", "blog", "email", "linkedin"],
        "pricing_tier": "mid",
        "geographic_focus": "Global",
        "stage": "established",
    },
    # 4. Gymshark — fitness apparel
    {
        "id": "gymshark",
        "name": "Gymshark",
        "industry": "Fitness Apparel",
        "description": "Direct-to-consumer fitness apparel brand built through social media and influencer marketing. Known for seamless leggings and athletic wear.",
        "products": ["Seamless Leggings", "Sports Bras", "Hoodies", "Accessories", "Lifting Gear"],
        "target_audience": "Gym-going Gen Z and Millennials 18-30 who are active on social media and fitness communities",
        "unique_value_proposition": "Born from the fitness community, built by athletes — performance apparel designed with the gym community, not for them from the outside",
        "competitors": ["Nike Training", "Lululemon", "Under Armour", "Alphalete"],
        "brand_voice": "Motivational, community-driven, aspirational, bold",
        "channels": ["instagram", "tiktok", "youtube", "paid_ads"],
        "pricing_tier": "mid",
        "geographic_focus": "US, UK, EU, Australia",
        "stage": "established",
    },
    # 5. Liquid Death — water/beverage
    {
        "id": "liquid-death",
        "name": "Liquid Death",
        "industry": "Beverage",
        "description": "Canned mountain water brand with heavy metal branding and irreverent marketing. Also sells iced teas and electrolyte mixes. B Corp certified.",
        "products": ["Mountain Water", "Sparkling Water", "Iced Teas", "Electrolyte Mixes", "Merchandise"],
        "target_audience": "Health-conscious but counter-culture consumers 21-40 who reject boring health branding",
        "unique_value_proposition": "Murder your thirst with the most entertaining water brand on earth — healthy hydration that doesn't look like it was designed by a yoga instructor",
        "competitors": ["Fiji", "Evian", "Topo Chico", "Spindrift"],
        "brand_voice": "Irreverent, dark humor, punk rock, anti-corporate",
        "channels": ["instagram", "tiktok", "youtube", "paid_ads", "podcast"],
        "pricing_tier": "mid",
        "geographic_focus": "US, expanding to EU",
        "stage": "growth",
    },
    # 6. Canva — design platform
    {
        "id": "canva",
        "name": "Canva",
        "industry": "Design Software",
        "description": "Online design platform democratizing graphic design with drag-and-drop tools, templates, and AI-powered features for non-designers.",
        "products": ["Canva Free", "Canva Pro", "Canva for Teams", "Canva for Enterprise", "Canva Print"],
        "target_audience": "Small business owners, marketers, educators, and social media managers who need professional designs without hiring a designer",
        "unique_value_proposition": "Empower the world to design — professional-quality visuals in minutes with 600K+ templates, no design skills required",
        "competitors": ["Adobe Creative Suite", "Figma", "Piktochart", "Visme"],
        "brand_voice": "Empowering, inclusive, simple, cheerful",
        "channels": ["instagram", "youtube", "blog", "email", "linkedin"],
        "pricing_tier": "mid",
        "geographic_focus": "Global — 190+ countries",
        "stage": "enterprise",
    },
    # 7. Warby Parker — eyewear
    {
        "id": "warby-parker",
        "name": "Warby Parker",
        "industry": "Eyewear",
        "description": "Direct-to-consumer eyewear brand offering designer prescription glasses and sunglasses at a fraction of traditional prices. Buy-a-pair, give-a-pair social mission.",
        "products": ["Prescription Glasses", "Sunglasses", "Contact Lenses", "Eye Exams"],
        "target_audience": "Style-conscious consumers 20-40 who want designer-quality glasses without the Luxottica markup",
        "unique_value_proposition": "Designer-quality prescription glasses starting at $95 — try 5 at home for free, buy a pair and we give a pair to someone in need",
        "competitors": ["LensCrafters", "Zenni Optical", "EyeBuyDirect", "GlassesUSA"],
        "brand_voice": "Smart, socially conscious, witty, approachable",
        "channels": ["instagram", "email", "website", "tiktok", "paid_ads"],
        "pricing_tier": "mid",
        "geographic_focus": "US, Canada",
        "stage": "established",
    },
    # 8. Duolingo — language learning
    {
        "id": "duolingo",
        "name": "Duolingo",
        "industry": "EdTech",
        "description": "Gamified language-learning platform with 40+ languages. Free with ads, premium subscription removes ads and adds features. Known for chaotic social media presence.",
        "products": ["Duolingo Free", "Super Duolingo", "Duolingo for Schools", "Duolingo English Test"],
        "target_audience": "Language learners of all ages who want a fun, low-commitment way to start or maintain a language",
        "unique_value_proposition": "Learn a language for free with the world's most-downloaded education app — gamified lessons that feel like playing a game, not studying",
        "competitors": ["Babbel", "Rosetta Stone", "Busuu", "Memrise"],
        "brand_voice": "Playful, slightly unhinged, meme-savvy, persistent (owl won't let you quit)",
        "channels": ["tiktok", "instagram", "twitter", "youtube", "email"],
        "pricing_tier": "budget",
        "geographic_focus": "Global",
        "stage": "enterprise",
    },
    # 9. Patagonia — outdoor apparel
    {
        "id": "patagonia",
        "name": "Patagonia",
        "industry": "Outdoor Apparel",
        "description": "Outdoor clothing company with radical environmental activism at its core. Donates 1% of sales to environmental causes. Worn Wear program repairs and resells used gear.",
        "products": ["Jackets", "Fleece", "Base Layers", "Worn Wear (used gear)", "Packs & Bags"],
        "target_audience": "Outdoor enthusiasts and environmentally conscious consumers 25-55 who align spending with values",
        "unique_value_proposition": "We're in business to save our home planet — the highest quality outdoor gear made responsibly, with a guarantee to repair it for life",
        "competitors": ["The North Face", "Arc'teryx", "REI Co-op", "Columbia"],
        "brand_voice": "Activist, principled, rugged, uncompromising",
        "channels": ["instagram", "email", "website", "youtube", "blog"],
        "pricing_tier": "premium",
        "geographic_focus": "Global",
        "stage": "enterprise",
    },
    # 10. Glossier — beauty/skincare
    {
        "id": "glossier",
        "name": "Glossier",
        "industry": "Beauty & Skincare",
        "description": "Direct-to-consumer beauty brand born from a beauty blog (Into The Gloss). Minimalist, skin-first philosophy. Products designed with community input.",
        "products": ["Boy Brow", "Cloud Paint", "Balm Dotcom", "Milky Jelly Cleanser", "You (perfume)"],
        "target_audience": "Beauty-conscious women 18-35 who prefer 'less is more' natural looks over heavy contouring",
        "unique_value_proposition": "Beauty inspired by real life, not Instagram filters — skincare-first makeup designed with our community, for our community",
        "competitors": ["Fenty Beauty", "The Ordinary", "Rare Beauty", "Drunk Elephant"],
        "brand_voice": "Minimalist, inclusive, community-driven, fresh",
        "channels": ["instagram", "tiktok", "email", "website"],
        "pricing_tier": "mid",
        "geographic_focus": "US, UK, France, Canada",
        "stage": "established",
    },
    # 11. Basecamp — project management
    {
        "id": "basecamp",
        "name": "Basecamp",
        "industry": "Project Management Software",
        "description": "Opinionated project management tool for small teams. Flat pricing, no per-user fees. Known for strong opinions on work culture and against growth-at-all-costs.",
        "products": ["Basecamp", "Basecamp Personal (free tier)", "HEY (email service)"],
        "target_audience": "Small teams and freelancers 5-50 people who are overwhelmed by complex PM tools and want simplicity",
        "unique_value_proposition": "The project management tool that actually manages projects — one flat price, all features included, no per-user pricing games",
        "competitors": ["Asana", "Monday.com", "Trello", "ClickUp"],
        "brand_voice": "Opinionated, anti-hype, plain-spoken, contrarian",
        "channels": ["blog", "twitter", "email", "podcast"],
        "pricing_tier": "mid",
        "geographic_focus": "Global",
        "stage": "established",
    },
    # 12. Oatly — oat milk
    {
        "id": "oatly",
        "name": "Oatly",
        "industry": "Plant-based Food & Beverage",
        "description": "Swedish oat milk company that popularized oat milk globally. Known for quirky, self-aware packaging and advertising that challenges the dairy industry.",
        "products": ["Oat Milk (Barista, Original, Chocolate)", "Oatgurt", "Ice Cream", "Cream"],
        "target_audience": "Health and environmentally conscious consumers 20-45 reducing dairy — flexitarians, not just vegans",
        "unique_value_proposition": "It's like milk but made for humans — the original oat milk that tastes good, is good for the planet, and doesn't take itself too seriously",
        "competitors": ["Alpro", "Califia Farms", "Silk", "Minor Figures"],
        "brand_voice": "Self-deprecating, witty, transparent, slightly absurd",
        "channels": ["instagram", "tiktok", "paid_ads", "website", "email"],
        "pricing_tier": "mid",
        "geographic_focus": "Global — strongest in EU and US",
        "stage": "established",
    },
]


def get_fixture(business_id: str) -> dict:
    """Get a single fixture by ID."""
    for f in FIXTURES:
        if f["id"] == business_id:
            return f
    raise KeyError(f"Fixture not found: {business_id}")


def get_all_fixtures() -> list[dict]:
    """Get all fixtures."""
    return list(FIXTURES)
