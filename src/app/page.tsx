export default function Home() {
  return (
    <div className="flex flex-col flex-1">
      {/* Header */}
      <header className="sticky top-0 z-50 border-b border-border bg-background/80 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
          <div className="flex items-center gap-2">
            <span className="text-xl font-bold tracking-tight text-primary">
              BrandOS
            </span>
          </div>
          <nav className="flex items-center gap-4">
            <a
              href="#features"
              className="text-sm text-muted-foreground transition-colors hover:text-foreground"
            >
              Features
            </a>
            <a
              href="/onboarding"
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
            >
              Get Started
            </a>
          </nav>
        </div>
      </header>

      {/* Hero */}
      <section className="flex flex-1 flex-col items-center justify-center px-6 py-24 text-center">
        <div className="mx-auto max-w-2xl space-y-6">
          <h1 className="text-4xl font-bold tracking-tight sm:text-6xl">
            Your Brand, <span className="text-primary">Intelligently</span>{" "}
            Managed
          </h1>
          <p className="text-lg leading-8 text-muted-foreground">
            BrandOS is your brand intelligence platform — discover opportunities,
            manage brand presence, and make data-driven decisions to grow your
            business.
          </p>
          <div className="flex flex-col items-center gap-4 sm:flex-row sm:justify-center">
            <a
              href="/onboarding"
              className="inline-flex h-11 items-center justify-center rounded-md bg-primary px-8 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
            >
              Start Building
            </a>
            <a
              href="#features"
              className="inline-flex h-11 items-center justify-center rounded-md border border-border px-8 text-sm font-medium transition-colors hover:bg-accent"
            >
              Learn More
            </a>
          </div>
        </div>
      </section>

      {/* Features */}
      <section
        id="features"
        className="border-t border-border bg-secondary/50 px-6 py-24"
      >
        <div className="mx-auto max-w-5xl">
          <h2 className="text-center text-3xl font-bold tracking-tight">
            Everything you need
          </h2>
          <p className="mx-auto mt-4 max-w-2xl text-center text-muted-foreground">
            A comprehensive suite of tools designed to help you understand,
            grow, and manage your brand effectively.
          </p>
          <div className="mt-16 grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
            {[
              {
                title: "Opportunity Inbox",
                description:
                  "AI-curated opportunities tailored to your brand — partnerships, press, and growth signals delivered daily.",
              },
              {
                title: "Brand Intelligence",
                description:
                  "Deep insights into market trends, competitor moves, and audience sentiment, all in one dashboard.",
              },
              {
                title: "Persona Replies",
                description:
                  "On-brand responses generated with your unique voice and tone, ready to review and publish.",
              },
              {
                title: "Text Studio",
                description:
                  "Write, refine, and optimize brand copy with AI assistance that knows your style guide.",
              },
              {
                title: "Onboarding Flows",
                description:
                  "Guided setup that captures your brand DNA — values, voice, visual identity, and goals.",
              },
              {
                title: "API Integration",
                description:
                  "Connect your existing tools and workflows with a clean, documented REST API.",
              },
            ].map((feature) => (
              <div
                key={feature.title}
                className="rounded-lg border border-border bg-background p-6"
              >
                <h3 className="text-lg font-semibold">{feature.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                  {feature.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border px-6 py-8">
        <div className="mx-auto flex max-w-7xl items-center justify-between">
          <span className="text-sm text-muted-foreground">
            &copy; {new Date().getFullYear()} BrandOS. All rights reserved.
          </span>
          <span className="text-xs text-muted-foreground/60">
            v0.1.0
          </span>
        </div>
      </footer>
    </div>
  );
}