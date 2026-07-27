"use client";

import type { Persona } from "@/types/persona";

interface PersonaCardProps {
  persona: Persona;
  selected?: boolean;
  onSelect?: (persona: Persona) => void;
  onCompare?: (persona: Persona) => void;
}

export function PersonaCard({
  persona,
  selected = false,
  onSelect,
  onCompare,
}: PersonaCardProps) {
  return (
    <article
      className={`group relative flex flex-col rounded-lg border bg-background p-5 transition-all hover:shadow-md ${
        selected
          ? "border-primary ring-2 ring-primary/20"
          : "border-border hover:border-primary/40"
      }`}
      role="button"
      tabIndex={0}
      onClick={() => onSelect?.(persona)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect?.(persona);
        }
      }}
      aria-pressed={selected}
      aria-label={`${persona.name} persona`}
    >
      {/* Header */}
      <div className="flex items-start gap-3">
        <span
          className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full text-2xl"
          style={{ backgroundColor: `${persona.color}18` }}
          aria-hidden="true"
        >
          {persona.avatar}
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-lg font-semibold">{persona.name}</h3>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {persona.tagline}
          </p>
        </div>
        {selected && (
          <span
            className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-xs text-primary-foreground"
            aria-label="Selected for comparison"
          >
            ✓
          </span>
        )}
      </div>

      {/* Voice preview */}
      <p className="mt-4 line-clamp-3 text-sm leading-relaxed text-muted-foreground">
        {persona.voice}
      </p>

      {/* Tone bars */}
      <div className="mt-4 space-y-2">
        {persona.tones.map((tone) => (
          <div key={tone.label} className="flex items-center gap-2">
            <span className="w-20 shrink-0 text-xs text-muted-foreground">
              {tone.label}
            </span>
            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-secondary">
              <div
                className="h-full rounded-full transition-all"
                style={{
                  width: `${tone.intensity}%`,
                  backgroundColor: persona.color,
                }}
                role="progressbar"
                aria-valuenow={tone.intensity}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label={`${tone.label}: ${tone.intensity}%`}
              />
            </div>
            <span className="w-7 text-right text-xs tabular-nums text-muted-foreground">
              {tone.intensity}
            </span>
          </div>
        ))}
      </div>

      {/* Values tags */}
      <div className="mt-4 flex flex-wrap gap-1.5">
        {persona.values.map((value) => (
          <span
            key={value}
            className="rounded-full bg-secondary px-2.5 py-0.5 text-xs text-secondary-foreground"
          >
            {value}
          </span>
        ))}
      </div>

      {/* Channels */}
      <div className="mt-3 flex flex-wrap gap-1">
        {persona.channels.slice(0, 3).map((ch) => (
          <span key={ch} className="text-xs text-muted-foreground">
            {ch}
            {persona.channels.indexOf(ch) <
            Math.min(persona.channels.length, 3) - 1
              ? " · "
              : ""}
          </span>
        ))}
        {persona.channels.length > 3 && (
          <span className="text-xs text-muted-foreground">
            +{persona.channels.length - 3}
          </span>
        )}
      </div>

      {/* Compare button */}
      {onCompare && (
        <button
          type="button"
          className="mt-4 w-full rounded-md border border-border px-3 py-1.5 text-sm font-medium transition-colors hover:bg-accent"
          onClick={(e) => {
            e.stopPropagation();
            onCompare(persona);
          }}
        >
          Compare
        </button>
      )}
    </article>
  );
}
