# BrandOS Frontend Agent Rules

<!-- This file defines project-specific AI agent instructions for BrandOS Web (Next.js). -->

## This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.

## Project Scope

BrandOS Web is a **frontend-only** Next.js application. It does NOT handle:
- Persistent data storage (use BrandOS API)
- Direct PII storage or consent management logic
- Payment processing, webhook ingestion, or delivery provider integration

## Conventions

- **Framework:** Next.js 16 App Router (TypeScript strict, `@/*` alias)
- **Styling:** Tailwind CSS v4 with CSS custom properties in `globals.css`
- **Fonts:** Geist Sans + Geist Mono via `next/font/google`
- **Theming:** CSS `--color-*` tokens registered with `@theme inline`; automatic dark mode via `prefers-color-scheme`
- **Layout:** All pages inherit from `src/app/layout.tsx` (metadata template: `%s | BrandOS`)
- **Components:** Place shared UI in `src/components/`; route-level UI stays in `src/app/`

## File Naming

- React components: `PascalCase.tsx` (e.g., `BrandCard.tsx`)
- Utility / hook files: `camelCase.ts` (e.g., `useBrand.ts`)
- Route files: Next.js conventions (`page.tsx`, `layout.tsx`, `loading.tsx`, `error.tsx`)
- Test files: `*.test.tsx` alongside the component

## Design Tokens

Defined in `src/app/globals.css` as CSS custom properties:
- `--background`, `--foreground` — base
- `--primary`, `--primary-foreground` — brand blue
- `--secondary`, `--secondary-foreground` — subtle surfaces
- `--muted`, `--muted-foreground` — de-emphasized text/surfaces
- `--accent`, `--accent-foreground` — interactive highlights
- `--destructive`, `--destructive-foreground` — error/danger
- `--border`, `--ring` — borders and focus rings
- `--radius` — border radius base

All tokens have light and dark variants via `prefers-color-scheme`.

## Commands

| Command | Description |
|---------|-------------|
| `npm run dev` | Dev server (Turbopack) |
| `npm run build` | Production build + TypeScript check |
| `npm run typecheck` | TypeScript type checking only |
| `npm run lint` | ESLint |

## Do NOT

- Add a CSS-in-JS library (use Tailwind)
- Add a state management library (use React Server Components + Context)
- Store secrets or PII in client-side code
- Commit `node_modules/`, `.next/`, or env files