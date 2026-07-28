import type { Metadata } from "next";
import { mockPersonas } from "@/lib/mockPersonas";
import { PersonaGallery } from "@/components/PersonaGallery";

export const metadata: Metadata = {
  title: "Persona Gallery",
  description:
    "Browse and compare your brand personas — find the perfect voice for every audience and channel.",
};

export default function PersonasPage() {
  // In production, this will be fetched from the BrandOS API.
  // Using mock data until the API endpoint is ready.
  const personas = mockPersonas;

  return (
    <div className="flex flex-col flex-1">
      {/* Header */}
      <header className="sticky top-0 z-50 border-b border-border bg-background/80 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
          <a
            href="/"
            className="flex items-center gap-2"
          >
            <span className="text-xl font-bold tracking-tight text-primary">
              BrandOS
            </span>
          </a>
          <nav className="flex items-center gap-4">
            <a
              href="/personas"
              className="text-sm font-medium text-primary"
              aria-current="page"
            >
              Personas
            </a>
          </nav>
        </div>
      </header>

      {/* Page content */}
      <main className="mx-auto w-full max-w-7xl flex-1 px-6 py-10">
        <div className="mb-8">
          <h1 className="text-3xl font-bold tracking-tight">
            Persona Gallery
          </h1>
          <p className="mt-2 text-muted-foreground">
            Browse your brand personas and compare them side by side. Each
            persona defines a unique voice, tone, audience, and content style.
          </p>
        </div>
        <PersonaGallery personas={personas} />
      </main>

      {/* Footer */}
      <footer className="border-t border-border px-6 py-8">
        <div className="mx-auto flex max-w-7xl items-center justify-between">
          <span className="text-sm text-muted-foreground">
            &copy; {new Date().getFullYear()} BrandOS. All rights reserved.
          </span>
          <span className="text-xs text-muted-foreground/60">v0.1.0</span>
        </div>
      </footer>
    </div>
  );
}
