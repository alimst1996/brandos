"use client";

export default function PersonasError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex flex-col flex-1">
      {/* Header */}
      <header className="sticky top-0 z-50 border-b border-border bg-background/80 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
          <a href="/" className="text-xl font-bold tracking-tight text-primary">
            BrandOS
          </a>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col items-center justify-center px-6 py-10 text-center">
        <span className="text-5xl" aria-hidden="true">
          ⚠️
        </span>
        <h2 className="mt-4 text-xl font-semibold">
          Something went wrong
        </h2>
        <p className="mt-2 max-w-md text-sm text-muted-foreground">
          We couldn&apos;t load your personas. This might be a temporary issue.
          Please try again.
        </p>
        <button
          type="button"
          onClick={reset}
          className="mt-6 inline-flex h-10 items-center justify-center rounded-md bg-primary px-6 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
        >
          Try again
        </button>
        {process.env.NODE_ENV === "development" && (
          <details className="mt-6 max-w-lg text-left">
            <summary className="cursor-pointer text-sm text-muted-foreground">
              Error details
            </summary>
            <pre className="mt-2 overflow-auto rounded-md bg-secondary p-4 text-xs">
              {error.message}
            </pre>
          </details>
        )}
      </main>
    </div>
  );
}
