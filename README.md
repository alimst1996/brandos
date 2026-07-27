# BrandOS Web

Brand Intelligence Platform — Next.js frontend application.

## Tech Stack

- **Framework:** Next.js 16 (App Router)
- **Language:** TypeScript (strict)
- **Styling:** Tailwind CSS v4
- **Fonts:** Geist Sans + Geist Mono
- **Linting:** ESLint 9
- **Design System:** CSS custom properties with light/dark mode

## Getting Started

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

## Scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Start development server |
| `npm run build` | Production build |
| `npm start` | Start production server |
| `npm run lint` | Run ESLint |
| `npm run typecheck` | Run TypeScript type checking |

## Project Structure

```
src/
  app/
    globals.css      # Design tokens + Tailwind config
    layout.tsx       # Root layout with metadata + fonts
    page.tsx         # Landing page
public/              # Static assets
```

## Design Tokens

BrandOS uses CSS custom properties for theming with automatic dark mode
via `prefers-color-scheme`. Tokens are defined in `globals.css` and
registered with Tailwind via `@theme inline`.

Key colors: `--background`, `--foreground`, `--primary`, `--secondary`,
`--muted`, `--accent`, `--destructive`, `--border`, `--ring`.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `NEXT_PUBLIC_APP_URL` | App base URL | `http://localhost:3000` |