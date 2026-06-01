# Vibing Web

React + Vite + TypeScript + Tailwind frontend for Vibing. It is a separate
client of the Control Plane over `/api/v1`; in dev, Vite proxies that prefix to
the backend on `http://localhost:8000`.

## Local Development

```bash
pnpm install
pnpm dev
```

Dev server: `http://localhost:5173`.

## Checks

```bash
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

## Conventions

- Backend calls go through `src/lib/api/`.
- Use relative `/api/v1/...` paths only.
- Keep frontend DTOs in `src/lib/api/types.ts` aligned with backend Pydantic schemas.
