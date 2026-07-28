export default function PersonasLoading() {
  return (
    <div className="flex flex-col flex-1">
      {/* Header skeleton */}
      <header className="sticky top-0 z-50 border-b border-border bg-background/80 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
          <div className="h-6 w-24 animate-pulse rounded bg-secondary" />
          <div className="h-4 w-16 animate-pulse rounded bg-secondary" />
        </div>
      </header>

      <main className="mx-auto w-full max-w-7xl flex-1 px-6 py-10">
        {/* Title skeleton */}
        <div className="mb-8 space-y-3">
          <div className="h-8 w-56 animate-pulse rounded bg-secondary" />
          <div className="h-4 w-96 max-w-full animate-pulse rounded bg-secondary" />
        </div>

        {/* Search bar skeleton */}
        <div className="flex items-center justify-between">
          <div className="h-9 w-64 animate-pulse rounded-md bg-secondary" />
          <div className="h-9 w-32 animate-pulse rounded-md bg-secondary" />
        </div>

        {/* Card grid skeleton */}
        <div className="mt-6 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className="flex flex-col rounded-lg border border-border bg-background p-5"
            >
              <div className="flex items-start gap-3">
                <div className="h-12 w-12 animate-pulse rounded-full bg-secondary" />
                <div className="flex-1 space-y-2">
                  <div className="h-5 w-32 animate-pulse rounded bg-secondary" />
                  <div className="h-3 w-48 animate-pulse rounded bg-secondary" />
                </div>
              </div>
              <div className="mt-4 space-y-2">
                <div className="h-3 w-full animate-pulse rounded bg-secondary" />
                <div className="h-3 w-3/4 animate-pulse rounded bg-secondary" />
              </div>
              <div className="mt-4 space-y-2">
                {Array.from({ length: 4 }).map((_, j) => (
                  <div key={j} className="flex items-center gap-2">
                    <div className="h-3 w-16 animate-pulse rounded bg-secondary" />
                    <div className="h-1.5 flex-1 animate-pulse rounded-full bg-secondary" />
                  </div>
                ))}
              </div>
              <div className="mt-4 flex gap-1.5">
                <div className="h-5 w-16 animate-pulse rounded-full bg-secondary" />
                <div className="h-5 w-20 animate-pulse rounded-full bg-secondary" />
                <div className="h-5 w-14 animate-pulse rounded-full bg-secondary" />
              </div>
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}
