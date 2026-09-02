# dehoarder web

Svelte 5 + Vite + TypeScript. No SvelteKit, no component library.

- `npm run dev` — dev server with `/api` proxied to `127.0.0.1:8765` (use `make dev` from the repo root to also start the API).
- `npm run build` — builds to `dist/`, served by the FastAPI app in production.
- `npm run check` — svelte-check + tsc.
- `npm run test` — vitest.
- `npm run lint` — eslint + prettier.
