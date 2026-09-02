# Game Plan — Dehoarder

> **Spec**: `CLAUDE.md` (read it fully before every session)
> **Base branch**: `main` · one branch per phase `feature/<phase>-<slug>` · merge to `main` after the phase STOP is approved
> **Date**: 2026-09-02

_Ordered steps. Each step is one committable unit. Tick a step **in the same commit** as the work. Do not skip. Do not reorder. Stop at every **STOP**. Nothing in this project prompts in the terminal._

---

## Pre-flight

- [x] Read `CLAUDE.md` end to end
- [x] `uv`, Python 3.12, Node 20+ available
- [x] `~/.config/thorium/` exists on the operator's machine (confirm; set default in `config.py`)
- [x] `.env` has `OPENROUTER_API_KEY`; models default to the ids in CLAUDE.md

---

## Phase 0 — Skeleton `feature/0-skeleton`

### Step 0.1 — Project scaffold
**What**: `pyproject.toml` (uv; fastapi, uvicorn, sqlalchemy, pydantic-settings, typer, httpx, selectolax, extruct, polars, pyyaml, pytest, pytest-asyncio, respx, ruff, mypy), `dehoarder/config.py` (db path, thorium dir, page cache, archive dir, OpenRouter key + model ids, language modifiers, link thresholds, plan weights, port), `Makefile` (`dev`, `check`, `test`, `build-web`), `.env.example`, `.gitignore`, `README.md` stub.
**Commit**: `chore(repo): scaffold uv project, config, makefile`
- [x] Done

### Step 0.2 — SQLite schema
**What**: `db/session.py` (WAL, FK on), `db/models.py` with **all** tables from CLAUDE.md incl. `job` and `bridge`, `db/migrate.py` (`create_all()` + `schema_version`), `dehoarder db init`.
**Tests**: fresh DB creates all tables; round-trips; `migrate()` idempotent.
**Commit**: `feat(db): sqlite models and schema init`
- [x] Done

### Step 0.3 — CLI + `status`
**What**: `cli.py`: `serve` (stub), `status` (implemented: counts per stage), `db init`, `run <stage>` (stubs, exit 2). No prompts anywhere.
**Tests**: `status` on empty DB; `--help`.
**Commit**: `feat(cli): typer app with status command`
- [x] Done

### Step 0.4 — FastAPI shell + job runner
**What**: `api/app.py` (bind `127.0.0.1`, static mount of `web/dist`), `GET /api/v1/status`; `jobs/runner.py`: run a stage function in a background thread, persist `job` rows with `progress` JSON, `POST /jobs/{stage}`, `GET /jobs/{id}`, `GET /jobs`; one job at a time. `serve` opens the browser (`webbrowser.open`) unless `--no-open`.
**Tests**: TestClient; a fake stage reports progress and completes; second job while one runs → 409.
**Commit**: `feat(api): app shell, status route, background job runner`
- [x] Done

### Step 0.5 — Web scaffold + navigation
**What**: `web/` Vite + Svelte 5 + TS; `npm run build` → `web/dist`; `make dev` runs vite + uvicorn with proxy. Top bar with stage stepper (driven by `/status`) and nav Tabs · Progress · Graph · Plan (empty pages). Minimal styling, no component library.
**Tests**: vitest for the API client; eslint/prettier in `make check`.
**Commit**: `feat(web): svelte scaffold, stepper, navigation`
- [x] Done

**STOP** — `dehoarder serve` opens an empty app. `make check` green. Merge.

---

## Phase 1 — Ingest `feature/1-ingest`

### Step 1.1 — Extension + bridge hello
**What**: `extension/manifest.json` (MV3; `tabs`, `storage`; `externally_connectable.matches: ["http://127.0.0.1:8765/*"]`; host permission same origin), `background.js`: on install/startup `POST /bridge/hello {extension_id, version}`; `chrome.runtime.onMessageExternal` handling `list_tabs` (`chrome.tabs.query({})` → normalised list), `close_tabs`, `open_tabs` (batch sizes and gaps per CLAUDE.md). Server: `POST /bridge/hello`, `GET /bridge/status` (`bridge` table). README: load-unpacked steps.
**Tests**: API tests for hello/status; extension logic isolated into pure functions unit-tested with a fake `chrome` object (vitest under `extension/tests/`).
**Commit**: `feat(ext): mv3 extension with external messaging and bridge hello`
- [ ] Done

### Step 1.2 — Scan from extension (API + Tabs view)
**What**: `POST /scans` accepts the tab list → `scan(source=extension)` + `tab` rows (domain via `urlparse().hostname` minus `www.`); Tabs view: extension-detected banner, **Scan now** → `sendMessage(list_tabs)` → `POST /scans` → renders raw inventory with counts. Not-detected banner with install steps.
**Tests**: API test; vitest for payload normalisation.
**Commit**: `feat(ingest): scan from extension and tabs view`
- [ ] Done

### Step 1.3 — Profile detection (fallback)
**What**: `ingest/profiles.py`: Thorium dir; `Local State` → `profile.last_used`, `profile.info_cache` (dir → human name); `list_profiles()`, `current_profile()`; lookup by name only.
**Tests**: fixture `Local State` with three named profiles.
**Commit**: `feat(ingest): thorium profile detection by name`
- [ ] Done

### Step 1.4 — SNSS read-only parser + fallback scan
**What**: `ingest/snss.py`: newest `Sessions/Session_*` (+ `Tabs_*`), magic/version check, iterate commands (UpdateTabNavigation, SetSelectedNavigationIndex, TabClosed, WindowClosed, SetTabWindow) → open tabs with selected entry. Read whole file into memory; retry once on short read; **never opens for writing**. `POST /scans/snss {profile_name?}` and `run scan-snss`; Tabs view: "Read session file" with profile dropdown by name, shown when no extension is detected, with a note that closing needs the extension.
**Tests**: synthetic fixture built in-test + anonymised real session (ask at STOP); open-mode assertion (`mock.patch("builtins.open")` sees only `"rb"`).
**Commit**: `feat(ingest): read-only snss parser and fallback scan`
- [ ] Done

**STOP** — real scan on the operator's machine via extension; compare with SNSS count. Merge.

---

## Phase 2 — Classify, review, close, restore `feature/2-close`

### Step 2.1 — Shop registry
**What**: `data/shops.yaml` seed; `classify/registry.py`: load, match hostname + parent domains, sync to `shop` table, `add_learned(domain, name)` writes YAML back preserving order; `GET /shops`, `POST /shops/learn`.
**Tests**: `www.amazon.de` → amazon; unknown → None; learned round-trip.
**Commit**: `feat(classify): shop registry`
- [ ] Done

### Step 2.2 — Deterministic rules
**What**: `classify/rules.py`: URL patterns (`/dp/`, `/book/`, `/product/`, ISBN with checksum), title patterns (` — `, ` | `, "купить", "книга", "by "), non-book domain allowlist → `known_shop | unknown_book_candidate | not_book`.
**Tests**: table-driven, 30+ cases incl. RU/FR/DE.
**Commit**: `feat(classify): url/title heuristics`
- [ ] Done

### Step 2.3 — OpenRouter client + unknown-domain classifier
**What**: `llm/client.py`: OpenAI-compatible chat + embeddings against OpenRouter; `complete(prompt_name, variables, tier, schema, effort=None)`; prompts from `llm/prompts/*.md`; cache by prompt hash in `llm_call` with tokens/cost; `embed(texts)` batched 50. `classify/llm.py`: one cheap call per unknown domain over ≤10 samples → `{is_bookshop, shop_name, kind, confidence}`. Prompt `classify_domain.md`.
**Tests**: fake transport; cache hit skips call; classifier mapping.
**Commit**: `feat(classify): openrouter client and unknown-domain classifier`
- [ ] Done

### Step 2.4 — Classify stage + review UI
**What**: `classify/classify.py::classify_scan()` (registry → rules → LLM) as a job (`POST /jobs/classify`, auto-triggered after a scan); sets `classification` and default `decision` (known → close, unknown → pending, not_book → keep). `PATCH /tabs/{id}`, `PATCH /tabs?scan=&shop=`. Tabs view: three groups, per-shop keep toggle, per-unknown-domain **Learn & close** / **Keep**, collapsed non-book group, **Close approved (N)** button (disabled until no `pending` remain).
**Tests**: API over fixture scan; vitest for grouping and button state.
**Commit**: `feat(classify): classify job and review ui`
- [ ] Done

### Step 2.5 — Archive
**What**: `ingest/archive.py`: `archive(scan_id)` appends to `archive/closed-<scan_id>.jsonl`, sets `archived_at`; append-only, idempotent; `POST /scans/{id}/archive`.
**Tests**: re-run appends nothing; never truncates.
**Commit**: `feat(ingest): append-only archive of closed tabs`
- [ ] Done

### Step 2.6 — Close
**What**: Tabs view **Close approved**: `POST /scans/{id}/archive` → `sendMessage(close_tabs {ids})` → `POST /scans/{id}/closed {closed, missing}`; server sets `closed_at` / `close_error=missing`; Progress view shows "closed N · failed M · kept K". Refuse if archive step failed.
**Tests**: API; vitest for the sequence with a fake extension.
**Commit**: `feat(ingest): close flow from the web app`
- [ ] Done

### Step 2.7 — Restore
**What**: Tabs view → past scans list → **Reopen closed tabs** (+ "only failed"): `GET /scans/{id}/restore-list` → `sendMessage(open_tabs {urls})` → `POST /scans/{id}/restored`; clears `closed_at`, appends `restored` lines.
**Tests**: API; vitest with fake extension.
**Commit**: `feat(ingest): restore flow`
- [ ] Done

**STOP** — on the operator's machine: scan → review → close a **small subset** (keep-toggle everything except one small shop) → restore → verify → full close. Merge.

---

## Phase 3 — Fetch queue `feature/3-queue`

### Step 3.1 — Scheduler
**What**: `queue/scheduler.py`: async priority queue by shop size then learned then FIFO; per-domain lock + min interval; global semaphore 4; 429/503 → domain paused with backoff, items moved to back; 403 → blocked for run. Injectable clock; progress callback.
**Tests**: fake fetcher 429 twice then 200; ordering and backoff without sleeping.
**Commit**: `feat(queue): per-domain rate-limited priority scheduler`
- [ ] Done

### Step 3.2 — Fetcher + page cache
**What**: `extract/fetch.py`: httpx async, realistic UA, `Accept-Language: en,ru,fr,de`, timeouts, redirects; `page_cache/<sha256>.html` + `.meta.json`; cache hit skips network.
**Tests**: respx; cache round-trip.
**Commit**: `feat(extract): fetcher with on-disk page cache`
- [ ] Done

### Step 3.3 — Process stage (fetch only) + Progress view
**What**: `extract/process.py` as a job: `decision=close`, `process_status=pending` tabs → scheduler → fetcher; `fetched`/`failed`; resumable; `run process --limit`. Progress view: per-stage bars, per-shop fetched/failed, paused/blocked domains.
**Tests**: end-to-end mocked; vitest for progress rendering.
**Commit**: `feat(extract): process job fetching pages, progress view`
- [ ] Done

**STOP** — `run process --limit 30` on real tabs; save 2–3 real pages per shop into `tests/fixtures/pages/<shop>/`. Merge.

---

## Phase 4 — Extract + dedup `feature/4-extract`

### Step 4.1 — BookMetadata + generic extractor
**What**: `extract/base.py`, `extract/generic.py` (JSON-LD, OpenGraph, `<meta isbn>`, ISBN regex + checksum, `<title>` heuristics EN/RU). Price/currency only when present.
**Tests**: fixtures from 3.3.
**Commit**: `feat(extract): metadata schema and generic extractor`
- [ ] Done

### Step 4.2 — Shop extractors
**What**: `extract/shops/{amazon,abebooks,chitai_gorod,bookvoed,manning}.py`; amazon detects bot walls → `None`.
**Tests**: one fixture per shop + amazon bot wall.
**Commit**: `feat(extract): shop-specific extractors`
- [ ] Done

### Step 4.3 — LLM fallback extractor
**What**: visible text ≤ 4k tokens + URL + title → cheap model → `BookMetadata` (strict JSON). Runs only when no title or no author so far. Prompt `extract_book.md`.
**Tests**: fake transport; schema violations rejected.
**Commit**: `feat(extract): llm fallback extractor`
- [ ] Done

### Step 4.4 — Dedup + persistence
**What**: `graph/dedup.py`: polars → `merge_key` (isbn13 else normalised title + first author, RU→LAT) → one `book` per key, `source` per tab, `selection_count`; idempotent; `needs_review` for title-only.
**Tests**: same ISBN two shops → one book, two sources, `selection_count=2`; RU/LAT merge; re-run idempotent.
**Commit**: `feat(graph): dedup books across shops`
- [ ] Done

### Step 4.5 — Wire process end to end + chain
**What**: fetch → shop → generic → LLM fallback → title-only → dedup/persist; `POST /jobs/chain` runs close-follow-up stages 4→5→6→7 sequentially (5–7 are stubs until their phases land; chain records which stages ran); Close button starts the chain after `closed` is posted.
**Tests**: end-to-end over 10 fixtures; chain ordering.
**Commit**: `feat(extract): full process pipeline and job chain`
- [ ] Done

**STOP** — full real run; per-shop success, `needs_review` count, LLM cost in Progress view. Merge.

---

## Phase 5 — Tag `feature/5-tag`

### Step 5.1 — Topic vocabulary
**What**: `graph/properties.py::build_vocabulary()`: one strong call (`effort: low`) over all titles/authors → `data/topics.yaml`; re-runs only propose additions (written to `topics.proposed.yaml`, shown in Progress view).
**Tests**: fake transport; existing entries preserved.
**Commit**: `feat(graph): topic vocabulary builder`
- [ ] Done

### Step 5.2 — Per-book tagging with difficulty
**What**: `tag_books()` batches of 20 → `{kind, topics, language, base_difficulty + reason, est_hours}`; validate topics; `difficulty = min(10, base + modifier)` with `{ru:0, en:0, fr:2, de:4, other:4}`; `est_hours` from pages when known; overrides win. Progress view shows estimated cost before the stage starts (computed from token counts of the batch prompts) and actual after.
**Tests**: fake transport; FR +2, DE +4; override wins; invalid topic rejected.
**Commit**: `feat(graph): llm tagging with language-adjusted difficulty`
- [ ] Done

### Step 5.3 — Embeddings via OpenRouter
**What**: `graph/embed.py`: `client.embed()` with `qwen/qwen3-embedding-8b`, text = title + authors + description + topics, only for books without one; stored as JSON.
**Tests**: fake transport; batching; idempotency.
**Commit**: `feat(graph): embeddings via openrouter`
- [ ] Done

**STOP** — Progress view lists 20 tagged books with difficulty reasons; operator corrects a few in the (temporary) list to validate overrides. Merge.

---

## Phase 6 — Link + Graph view `feature/6-graph`

### Step 6.1 — Edge builder
**What**: `graph/link.py` implementing the hierarchy table exactly; `cross_lane`; full rebuild in one transaction; `link` stage in the chain.
**Tests**: hand-built 8-book graph.
**Commit**: `feat(graph): edge builder by property hierarchy`
- [ ] Done

### Step 6.2 — Books + graph API
**What**: `GET /books`, `GET /books/{id}` (sources + edges), `PATCH /books/{id}` (→ overrides), `GET /graph?edge_types=`.
**Tests**: TestClient over seeded DB.
**Commit**: `feat(api): books and graph routes`
- [ ] Done

### Step 6.3 — Graph view
**What**: sigma.js + graphology, ForceAtlas2 then frozen; colour = kind, size = `selection_count`, edge toggles (publisher/shop off), search; side panel with metadata, difficulty + reason, language, sources with price/currency and outbound link, editable properties (PATCH). Graph nav item unlocks when `link` has run.
**Tests**: vitest for graph transform; manual checklist in README.
**Commit**: `feat(web): graph view with sigma.js`
- [ ] Done

**STOP** — operator explores the real graph; tune thresholds in `config.py` if needed. Merge.

---

## Phase 7 — Plan + Plan view `feature/7-plan`

### Step 7.1 — Balanced Lane Walk
**What**: `plan/lanes.py`: pure `walk(graph, books, target, tol, horizon, seeds, exclusions, beam=5, lookahead=6) -> Plan` per CLAUDE.md stage 7 (band on the mean of the three current difficulties, technical-first seeding, timeline simulation, score terms, 2-hop half weight, beam search, tolerance widening with warning, deterministic ties, `reason` strings).
**Tests**: hand-built 15-book graph with known walk; determinism; widening; seeds/exclusions; beam beats greedy on a trap.
**Commit**: `feat(plan): balanced lane walk`
- [ ] Done

### Step 7.2 — Plan stage + API
**What**: `plan` stage in the chain (default target/tol) → `reading_plan` + `plan_item`; `GET /plans`, `GET /plans/{id}`, `POST /plans {target, tol, horizon, seeds}`; `run plan`.
**Tests**: API over seeded DB.
**Commit**: `feat(plan): plan stage and routes`
- [ ] Done

### Step 7.3 — Plan view
**What**: three lanes on a shared timeline (width = `est_hours`), cards with difficulty and `reason`; target and tolerance sliders + Regenerate; warnings shown. Plan nav item unlocks when a plan exists.
**Tests**: vitest for lane layout math.
**Commit**: `feat(web): reading plan view`
- [ ] Done

**STOP** — operator reads the plan; tune weights in `config.py`, record reasoning in the commit. Merge.

---

## Phase 8 — Polish `feature/8-polish`

### Step 8.1 — README
**What**: quick start (`db init`, load extension, `serve`), what each view does, safety (archive, restore), cost notes, troubleshooting (bot walls, 429s, extension not detected).
**Commit**: `docs(repo): operator readme`
- [ ] Done

### Step 8.2 — Full `status` + Progress polish
**What**: `status` and Progress view: per-stage progress, per-shop extraction success, LLM spend, paused/blocked domains, last plan date; error surfaces are readable.
**Commit**: `feat(cli): full status report`
- [ ] Done

### Step 8.3 — Final checklist
- [ ] `make check` green
- [ ] Full real run end to end from `serve` with no terminal interaction
- [ ] `restore` verified on a small batch
- [ ] No unrelated changes in any phase
- [ ] CLAUDE.md decisions section still accurate

---

## Deferred

_Out-of-scope things noticed while implementing. Add here instead of fixing in place._

- (empty)
