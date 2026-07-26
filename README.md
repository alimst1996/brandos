# BrandOS API

NestJS backend API for the BrandOS platform — workspace management, billing, content operations, and multi-agent orchestration.

## Quick Start

```bash
# Install dependencies
npm install

# Development
npm run start:dev

# Production build
npm run build
npm run start:prod
```

The API runs on `http://localhost:3000` by default.

## API Documentation

Swagger UI is available at `http://localhost:3000/api/docs` when running in development mode.

## Health Checks

| Endpoint | Purpose | K8s Probe |
|----------|---------|-----------|
| `GET /api/v1/health` | Full health check (memory, disk, etc.) | - |
| `GET /api/v1/health/live` | Liveness probe | `livenessProbe` |
| `GET /api/v1/health/ready` | Readiness probe | `readinessProbe` |

## Testing

```bash
# Unit tests
npm test

# Unit tests with coverage
npm run test:cov

# End-to-end tests
npm run test:e2e

# Watch mode
npm run test:watch
```

## Linting & Formatting

```bash
# Lint
npm run lint

# Format
npm run format

# Type check
npm run typecheck
```

## Docker

```bash
# Build image
docker build -t brandos-api .

# Run container
docker run -p 3000:3000 brandos-api

# Using docker-compose
docker-compose up
```

## Project Structure

```
src/
├── main.ts                    # Application entry point
├── app.module.ts              # Root module
├── config/
│   └── env.validation.ts      # Environment variable validation
├── common/
│   ├── filters/
│   │   └── global-exception.filter.ts   # Global error handling
│   └── interceptors/
│       └── transform.interceptor.ts     # Response transformation
└── health/
    ├── health.module.ts       # Health check module
    ├── health.controller.ts   # Health check endpoints
    └── health.controller.spec.ts  # Unit tests
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `NODE_ENV` | `development` | Environment (development/production/test) |
| `PORT` | `3000` | Server port |
| `CORS_ORIGIN` | `*` | CORS allowed origins |
| `LOG_LEVEL` | `info` | Logging level |

## CI/CD

GitHub Actions CI runs on push/PR to `main`:

1. **Test** — lint, typecheck, unit tests, e2e tests (Node 18.x + 20.x)
2. **Security** — npm audit, secret scanning
3. **Docker** — build and test container

## Architecture Decisions

- **Global prefix**: All API routes under `/api/v1/`
- **Response envelope**: All successful responses wrapped in `{ success, data, timestamp, path }`
- **Validation**: Automatic request validation with `class-validator`
- **Error handling**: Structured error responses with request ID tracking
- **Graceful shutdown**: Enabled for container orchestration

## License

UNLICENSED — BrandOS internal use only.
