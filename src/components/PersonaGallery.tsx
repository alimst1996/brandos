"use client";

import { useState, useMemo } from "react";
import type { Persona } from "@/types/persona";
import { PersonaCard } from "./PersonaCard";
import { PersonaComparison } from "./PersonaComparison";

interface PersonaGalleryProps {
  personas: Persona[];
}

type SortOption = "name" | "newest" | "updated";

export function PersonaGallery({ personas }: PersonaGalleryProps) {
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortOption>("name");
  const [selectedForCompare, setSelectedForCompare] = useState<Persona[]>([]);
  const [comparing, setComparing] = useState<
    { a: Persona; b: Persona } | null
  >(null);

  // Filter + sort
  const filtered = useMemo(() => {
    const q = search.toLowerCase().trim();
    let result = personas.filter(
      (p) =>
        !q ||
        p.name.toLowerCase().includes(q) ||
        p.tagline.toLowerCase().includes(q) ||
        p.values.some((v) => v.toLowerCase().includes(q)) ||
        p.channels.some((c) => c.toLowerCase().includes(q))
    );

    switch (sort) {
      case "name":
        result.sort((a, b) => a.name.localeCompare(b.name));
        break;
      case "newest":
        result.sort(
          (a, b) =>
            new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
        );
        break;
      case "updated":
        result.sort(
          (a, b) =>
            new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()
        );
        break;
    }
    return result;
  }, [personas, search, sort]);

  const handleSelect = (persona: Persona) => {
    setSelectedForCompare((prev) => {
      const exists = prev.find((p) => p.id === persona.id);
      if (exists) return prev.filter((p) => p.id !== persona.id);
      if (prev.length >= 2) return [prev[1], persona];
      return [...prev, persona];
    });
  };

  const handleCompare = (persona: Persona) => {
    setSelectedForCompare((prev) => {
      const next =
        prev.length >= 2
          ? [prev[1], persona]
          : prev.some((p) => p.id === persona.id)
            ? prev
            : [...prev, persona];

      // If we have 2, open comparison
      if (next.length === 2) {
        setComparing({ a: next[0], b: next[1] });
      }
      return next;
    });
  };

  const startComparison = () => {
    if (selectedForCompare.length === 2) {
      setComparing({ a: selectedForCompare[0], b: selectedForCompare[1] });
    }
  };

  const closeComparison = () => {
    setComparing(null);
    setSelectedForCompare([]);
  };

  return (
    <div>
      {/* Comparison view */}
      {comparing && (
        <div className="mb-8">
          <PersonaComparison
            personaA={comparing.a}
            personaB={comparing.b}
            onClose={closeComparison}
          />
        </div>
      )}

      {/* Search + sort bar */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative flex-1 sm:max-w-sm">
          <svg
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z"
            />
          </svg>
          <input
            type="search"
            placeholder="Search personas..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-9 w-full rounded-md border border-border bg-background pl-9 pr-3 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            aria-label="Search personas"
          />
        </div>
        <div className="flex items-center gap-3">
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as SortOption)}
            className="h-9 rounded-md border border-border bg-background px-3 text-sm"
            aria-label="Sort personas"
          >
            <option value="name">Name A–Z</option>
            <option value="newest">Newest first</option>
            <option value="updated">Recently updated</option>
          </select>

          {selectedForCompare.length === 2 && (
            <button
              type="button"
              onClick={startComparison}
              className="inline-flex h-9 items-center gap-1.5 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
            >
              Compare {selectedForCompare[0].name} &{" "}
              {selectedForCompare[1].name}
            </button>
          )}
          {selectedForCompare.length === 1 && (
            <span className="text-sm text-muted-foreground">
              Select one more to compare
            </span>
          )}
        </div>
      </div>

      {/* Empty state */}
      {filtered.length === 0 && (
        <div className="mt-16 flex flex-col items-center gap-3 text-center">
          <span className="text-4xl" aria-hidden="true">
            🔍
          </span>
          <h3 className="text-lg font-semibold">No personas found</h3>
          <p className="max-w-sm text-sm text-muted-foreground">
            {search
              ? `No results for "${search}". Try a different search term.`
              : "No personas have been created yet. Start by defining your first brand persona."}
          </p>
        </div>
      )}

      {/* Gallery grid */}
      {filtered.length > 0 && (
        <div className="mt-6 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((persona) => (
            <PersonaCard
              key={persona.id}
              persona={persona}
              selected={selectedForCompare.some((p) => p.id === persona.id)}
              onSelect={handleSelect}
              onCompare={handleCompare}
            />
          ))}
        </div>
      )}

      {/* Selection hint */}
      {filtered.length > 0 && !comparing && (
        <p className="mt-6 text-center text-sm text-muted-foreground">
          Click cards to select two personas, then compare them side by side.
        </p>
      )}
    </div>
  );
}
