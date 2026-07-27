"use client";

import type { Persona } from "@/types/persona";

interface PersonaComparisonProps {
  personaA: Persona;
  personaB: Persona;
  onClose: () => void;
}

function ToneComparison({
  personaA,
  personaB,
}: {
  personaA: Persona;
  personaB: Persona;
}) {
  // Collect all unique tone labels across both personas
  const allLabels = Array.from(
    new Set([
      ...personaA.tones.map((t) => t.label),
      ...personaB.tones.map((t) => t.label),
    ])
  );

  const getIntensity = (persona: Persona, label: string) =>
    persona.tones.find((t) => t.label === label)?.intensity ?? 0;

  return (
    <div className="space-y-3">
      {allLabels.map((label) => {
        const aVal = getIntensity(personaA, label);
        const bVal = getIntensity(personaB, label);
        return (
          <div key={label} className="grid grid-cols-[1fr_auto_1fr] items-center gap-3">
            {/* A side (right-aligned bar growing left) */}
            <div className="flex items-center justify-end gap-2">
              <span className="w-7 text-right text-xs tabular-nums text-muted-foreground">
                {aVal}
              </span>
              <div className="h-2 w-24 overflow-hidden rounded-full bg-secondary">
                <div
                  className="ml-auto h-full rounded-full"
                  style={{
                    width: `${aVal}%`,
                    backgroundColor: personaA.color,
                  }}
                />
              </div>
            </div>

            {/* Center label */}
            <span className="w-20 text-center text-xs font-medium text-muted-foreground">
              {label}
            </span>

            {/* B side */}
            <div className="flex items-center gap-2">
              <div className="h-2 w-24 overflow-hidden rounded-full bg-secondary">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${bVal}%`,
                    backgroundColor: personaB.color,
                  }}
                />
              </div>
              <span className="w-7 text-xs tabular-nums text-muted-foreground">
                {bVal}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

interface ComparisonRowProps {
  label: string;
  a: string;
  b: string;
}

function ComparisonRow({ label, a, b }: ComparisonRowProps) {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-[140px_1fr_1fr] md:gap-6">
      <span className="text-sm font-medium text-muted-foreground">
        {label}
      </span>
      <p className="text-sm leading-relaxed">{a}</p>
      <p className="text-sm leading-relaxed">{b}</p>
    </div>
  );
}

export function PersonaComparison({
  personaA,
  personaB,
  onClose,
}: PersonaComparisonProps) {
  return (
    <section
      className="rounded-lg border border-border bg-background"
      aria-label={`Comparing ${personaA.name} and ${personaB.name}`}
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-6 py-4">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <span
              className="flex h-10 w-10 items-center justify-center rounded-full text-xl"
              style={{ backgroundColor: `${personaA.color}18` }}
              aria-hidden="true"
            >
              {personaA.avatar}
            </span>
            <div>
              <h3 className="font-semibold">{personaA.name}</h3>
              <p className="text-xs text-muted-foreground">
                {personaA.tagline}
              </p>
            </div>
          </div>
          <span className="text-sm font-medium text-muted-foreground">
            vs
          </span>
          <div className="flex items-center gap-2">
            <span
              className="flex h-10 w-10 items-center justify-center rounded-full text-xl"
              style={{ backgroundColor: `${personaB.color}18` }}
              aria-hidden="true"
            >
              {personaB.avatar}
            </span>
            <div>
              <h3 className="font-semibold">{personaB.name}</h3>
              <p className="text-xs text-muted-foreground">
                {personaB.tagline}
              </p>
            </div>
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded-md border border-border px-3 py-1.5 text-sm transition-colors hover:bg-accent"
          aria-label="Close comparison"
        >
          Close
        </button>
      </div>

      {/* Tone comparison */}
      <div className="border-b border-border px-6 py-5">
        <h4 className="mb-4 text-sm font-semibold">Tone Comparison</h4>
        <ToneComparison personaA={personaA} personaB={personaB} />
      </div>

      {/* Side-by-side details */}
      <div className="space-y-4 px-6 py-5">
        <ComparisonRow
          label="Voice"
          a={personaA.voice}
          b={personaB.voice}
        />
        <ComparisonRow
          label="Audience"
          a={personaA.audience}
          b={personaB.audience}
        />
        <ComparisonRow
          label="Style Guide"
          a={personaA.styleGuide}
          b={personaB.styleGuide}
        />

        {/* Values */}
        <div className="grid grid-cols-1 gap-4 md:grid-cols-[140px_1fr_1fr] md:gap-6">
          <span className="text-sm font-medium text-muted-foreground">
            Values
          </span>
          <div className="flex flex-wrap gap-1.5">
            {personaA.values.map((v) => (
              <span
                key={v}
                className="rounded-full bg-secondary px-2.5 py-0.5 text-xs text-secondary-foreground"
              >
                {v}
              </span>
            ))}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {personaB.values.map((v) => (
              <span
                key={v}
                className="rounded-full bg-secondary px-2.5 py-0.5 text-xs text-secondary-foreground"
              >
                {v}
              </span>
            ))}
          </div>
        </div>

        {/* Channels */}
        <div className="grid grid-cols-1 gap-4 md:grid-cols-[140px_1fr_1fr] md:gap-6">
          <span className="text-sm font-medium text-muted-foreground">
            Channels
          </span>
          <p className="text-sm text-muted-foreground">
            {personaA.channels.join(", ")}
          </p>
          <p className="text-sm text-muted-foreground">
            {personaB.channels.join(", ")}
          </p>
        </div>

        {/* Languages */}
        <div className="grid grid-cols-1 gap-4 md:grid-cols-[140px_1fr_1fr] md:gap-6">
          <span className="text-sm font-medium text-muted-foreground">
            Languages
          </span>
          <p className="text-sm text-muted-foreground">
            {personaA.languages.join(", ")}
          </p>
          <p className="text-sm text-muted-foreground">
            {personaB.languages.join(", ")}
          </p>
        </div>

        {/* Sample responses */}
        <ComparisonRow
          label="Sample Response"
          a={personaA.sampleResponse}
          b={personaB.sampleResponse}
        />
      </div>
    </section>
  );
}
