# Dehoarder

> **Codex will review your work.**

## What this is

Dehoarder is a local tool that turns a hoard of open browser tabs (bookshop pages, ~500 of them) into:

1. **Freed RAM** — tabs are closed, safely, after the operator confirms in the web app.
2. **A local catalogue** — every tab that is a book becomes a `book` record with metadata and one or more `sources` (where to buy it, price when the shop shows one).
3. **A semantic graph** — books linked by author, series, topic, similarity, publisher, shop. Navigable in the web app; each node links back to the original page.
4. **A reading plan** — a non-trivial traversal of that graph: three parallel lanes (fiction / non-fiction / technical) whose combined difficulty stays stable over time.

The underlying blueprint, which everything must serve:

```
unstructured data (tabs)  →  semantic structure (graph)  →  a new way to traverse it (lane walk)
```

**Interaction model.** The operator runs one command in a terminal: `dehoarder serve`. It opens the web app in the browser. Everything else — reviewing tabs, confirming the close, watching progress, exploring the graph, reading the plan — happens in the web app. **The terminal never asks for confirmation.** Order of experience: tabs closed → graph → plan, with navigation between graph and plan.

The first item type is *books from bookshops*. The pipeline is written so that *videos* and *articles* can be added later without rewriting the stages (see "Extensibility"), but **we do not build those now**.

Priority when trading off: free RAM first, catalogue second, graph third, plan fourth. Everything stays **lightweight**: one Python process, one SQLite file, one small extension, no services.

---

## How to work in this repo (rules for Claude Code)

Adapted from Gourze, our orchestration standard. Not optional.

1. **GAMEPLAN.md is the plan. Follow it in order.** Never skip or reorder a step. If a step is wrong, stop and say so — do not improvise around it.
2. **Update `GAMEPLAN.md` in the same commit as the work itself.** Checking off a step (`- [ ]` → `- [x]`) is part of that step's diff. A commit that completes a step but does not tick it is incomplete. A tick without the work is a lie.
3. **Atomic conventional commits.** One logical change per commit. `feat(<area>): …`, `fix(<area>): …`, `test(<area>): …`, `chore(<area>): …`, `docs(<area>): …`. `<area>` ∈ `ingest, classify, extract, graph, plan, api, web, ext, db, cli, jobs, repo`. Use the commit message given in the GAMEPLAN step.
4. **Always read the codebase before writing.** Cite real files, functions, patterns. Match existing style. No placeholders, no `TODO: implement`.
5. **Stop at every STOP marker in the GAMEPLAN.** Present what was done in one paragraph, open the phase PR (see Branching), and wait. The STOP summary and the PR description must include (a) what the operator has to do by hand to validate the phase, in plain terms, and (b) a **reading list** covering every commit in the phase: each file marked **read thoroughly** (logic, anything destructive or byte-level, anything touching the browser or the DB), **skim** (tests, glue, UI markup), or **skip** (lockfiles, fixtures, generated files), with one line on why.
6. **Open questions block implementation.** If a step is tagged `[Qn]` and Qn is unanswered below, ask; record the answer in this file.
7. **Tests are part of the step.** Every behaviour-adding step adds tests in the same commit. Prefer small deterministic tests on saved fixtures (`tests/fixtures/`) over mocking.
8. **Deterministic code does the dangerous things; the LLM never does.** Closing tabs, writing the DB, writing files — plain code behind an explicit operator click. The LLM classifies, extracts, tags, rates. It never gets a handle to the browser or the filesystem.
9. **Do not modify files outside the step's scope.** Note wanted refactors in the GAMEPLAN "Deferred" list.
10. **Codex will review your work.** Small diffs, clear commit messages.
11. **Never lose a tab.** Tabs are written to an append-only archive before they are closed, and `restore` can reopen them. SNSS files are **never written**.
12. **Model assignment.** Cheap model for per-URL classification and extraction fallback (hundreds of calls). Strong model for the few batch reasoning calls: topic vocabulary, difficulty rating. The graph traversal is pure code — no model.
13. **Python only** (plus the Svelte/TS frontend and the ~100-line extension). No Rust.

### Branching

Single repository, single developer. Base branch `main`. One branch per GAMEPLAN phase: `feature/<phase>-<slug>`. **Nothing is pushed to `main` directly.**

At the phase STOP, Claude pushes the branch and opens **one PR per phase** against `main` (`gh pr create`), with the STOP summary, the manual-validation steps, and the reading list as the description. **Claude never merges.** The operator reviews the PR on GitHub, leaves comments, and merges it themselves once the manual validation passes — as a **merge commit, no squash**, so the atomic per-step history survives. Review comments on the PR are addressed with follow-up commits on the same branch (`fix(<area>): …`), never by force-push. No issues, no project board.

GitHub setup that enforces this (repo → Settings → Rules → Rulesets → New branch ruleset, target `main`): enable *Restrict deletions*, *Block force pushes*, and *Require a pull request before merging* with **required approvals = 0** — GitHub does not let a PR author approve their own PR, and the operator is the author of record, so a non-zero approval count would lock the solo workflow out; the review happens by reading the PR, not by a formal approval. Leave the bypass list **empty** so the rule applies to the admin too — otherwise direct pushes to `main` still go through. Optionally, once CI exists, add *Require status checks to pass* on `make check`.

---

## Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Language | Python 3.12 | Everything except UI and extension. |
| Package/env | `uv` | `uv sync`, `uv run`. |
| API | FastAPI + uvicorn | `127.0.0.1:8765`; JSON API + built Svelte app. Pipeline stages run as in-process background jobs (`jobs/`), progress polled by the UI. No websockets, no task queue. |
| DB | **SQLite** (`dehoarder.db`, WAL) via SQLAlchemy 2 (sync) | `metadata.create_all()` + `schema_version` table + `migrate()` scaffold. No Alembic, no Docker. Embeddings stored as JSON float arrays, compared in-process. |
| Tabular | polars | Batch dedup/normalisation. Not in the request path. |
| HTTP | httpx (async) | Fetching, per-domain rate limiting, backoff. |
| HTML | selectolax + extruct | Parsing, JSON-LD/OpenGraph. |
| LLM | **OpenRouter**, OpenAI-compatible, via `dehoarder/llm/client.py` | `.env`: `OPENROUTER_API_KEY`, `LLM_STRONG_MODEL=z-ai/glm-5.3` (reasoning always on; send `reasoning: {effort: "low"}` for tagging), `LLM_CHEAP_MODEL=deepseek/deepseek-v4-flash`, `EMBEDDING_MODEL=qwen/qwen3-embedding-8b` (4096-dim, `/v1/embeddings`). No local models. Prompts in `dehoarder/llm/prompts/*.md`, never inline. |
| CLI | typer | Only `serve`, `status`, `db init`, and non-interactive `run <stage>` for development/tests. |
| Frontend | Svelte 5 + Vite (no SvelteKit), TypeScript | `sigma.js` + `graphology`. Built to `web/dist`. |
| Browser bridge | Manifest V3 extension (vanilla JS) | Lists, closes, reopens tabs in the running Thorium without loading them. Driven by the web app through `externally_connectable`. |
| Lint/test | ruff, mypy, pytest, pytest-asyncio, respx; eslint + prettier + vitest for `web/` | `make check` runs all. |

Not used, by decision: Rust, Capacitor, Postgres, Django, SvelteKit, local models, sentence-transformers.

---

## Repository layout

```
dehoarder/
├── CLAUDE.md · GAMEPLAN.md · README.md
├── pyproject.toml · Makefile · .env.example
├── data/
│   ├── shops.yaml                ← known bookshop/publisher registry (seed + learned)
│   └── topics.yaml               ← controlled topic vocabulary (generated, operator-edited)
├── dehoarder/
│   ├── cli.py                    ← serve, status, db init, run <stage>
│   ├── config.py                 ← pydantic-settings: paths, models, language modifiers, thresholds, weights
│   ├── db/{models.py, session.py, migrate.py}
│   ├── jobs/runner.py            ← background job runner with progress records
│   ├── ingest/{profiles.py, snss.py, bridge.py, archive.py}
│   ├── classify/{registry.py, rules.py, llm.py, classify.py}
│   ├── extract/{base.py, fetch.py, generic.py, llm_fallback.py, process.py, shops/*.py}
│   ├── queue/scheduler.py
│   ├── graph/{properties.py, embed.py, dedup.py, link.py}
│   ├── plan/lanes.py
│   ├── llm/{client.py, prompts/*.md}
│   └── api/{app.py, routes/*.py}
├── extension/{manifest.json, background.js}
├── web/                          ← Svelte 5 + Vite
└── tests/{fixtures/, ...}
```

---

## Pipeline

Seven stages, fixed order. Each is a function callable by the job runner (and by `dehoarder run <stage>` for tests). The only destructive stage, `close`, happens behind an explicit click in the web app.

```
1 scan     extension lists tabs → inventory                     read-only
2 review   classify → operator decides in the Tabs view          writes decisions
3 close    archive → extension closes approved tabs → verify     destructive, click-confirmed
4 process  queue (known shops first) → fetch → extract → dedup   → books + sources
5 tag      LLM: kind, topics, difficulty, language; embeddings
6 link     edges by property hierarchy → graph view
7 plan     three-lane walk with stable difficulty → plan view
```

After the operator clicks **Close approved**, stages 3→4→5→6→7 run automatically as one job chain; the Progress view shows each stage; the Graph view unlocks after 6, the Plan view after 7.

### Stage 1 — scan

**Extension.** Loaded once (`chrome://extensions` → Developer mode → Load unpacked → `extension/`). `manifest.json`: permissions `tabs`, `storage`; `externally_connectable.matches = ["http://127.0.0.1:8765/*"]`; host permission for the same origin. On install/startup the service worker `POST`s `{extension_id, version}` to `/bridge/hello` so the app knows how to reach it. The web app talks to it with `chrome.runtime.sendMessage(extension_id, {type, payload})`:

| Message | Extension does | Notes |
|---|---|---|
| `list_tabs` | `chrome.tabs.query({})` → returns `{windowId, id, url, title, discarded, lastAccessed, pinned}[]` | Discarded tabs included, **never loaded**. |
| `close_tabs {ids}` | `chrome.tabs.remove` in batches of 50 → returns `{closed, missing}` | Closing does not load tabs. |
| `open_tabs {urls}` | `chrome.tabs.create({url, active:false})` in batches of 20, 500 ms apart | For `restore`. |

The extension only sees the profile it is installed in, which is the currently open one — that is the point. The web app `POST`s the list to `/api/v1/scans` → `scan` + `tab` rows.

**SNSS fallback (read-only, inventory only).** When no extension has said hello, the Tabs view offers "Read from session file": `~/.config/thorium/<ProfileDir>/Sessions/Session_<ts>` + `Tabs_<ts>`, profile = `Local State → profile.last_used`, other profiles selectable by their **human-readable name** from `profile.info_cache`. Parser reference: Chromium `session_service_commands.cc`; Python reference `ccl_chromium_reader/ccl_chromium_snss2.py`. Handles UpdateTabNavigation, SetSelectedNavigationIndex, TabClosed, WindowClosed, SetTabWindow. **Read-only, always.** Without the extension the app can catalogue but cannot close; the UI says so.

### Stage 2 — review (Tabs view)

Classification per tab: registry → deterministic rules → cheap LLM for unknown domains. The Tabs view shows three groups with counts and per-shop breakdown:

- **Known shops** — decision `close` by default; per-shop toggle to keep.
- **Looks like a book, unknown shop** — per-domain card: **Learn & close** (adds to `shops.yaml` with `learned: true`) or **Keep**.
- **Not a book** — always `keep`; shown collapsed.

Decisions saved on `tab.decision` via `PATCH /tabs/{id}` / `PATCH /tabs?shop=`. A single **Close approved (N tabs)** button starts stage 3.

### Stage 3 — close

1. Append every `decision=close` tab to `archive/closed-<scan_id>.jsonl`; set `tab.archived_at`. Append-only, never truncated.
2. Web app sends `close_tabs` to the extension; posts the result to `POST /scans/{id}/closed`; server sets `closed_at` / `close_error=missing`.
3. Progress view: "closed N · failed M · kept K". The job chain continues into stage 4 immediately.

**Restore** (Tabs view → "Reopen closed tabs" for a scan, optional `only failed`): server returns archived URLs, web app sends `open_tabs`, server clears `closed_at` and appends `restored` lines to the jsonl.

### Stage 4 — process

**Queue order (RAM-first):** known shops first, largest first; learned shops after; FIFO within a shop.

**Scheduler:** per-domain concurrency 1 and min interval (default 2 s, per-shop override); global concurrency 4. 429/503 → pause the domain with exponential backoff (30 s·2ⁿ, cap 30 min) and **move its remaining items to the back of the queue**; continue with the next domain. 403/bot wall → domain blocked for the run; those tabs fall back to title-only books. Raw HTML cached in `page_cache/<sha256(url)>.html`; re-runs never re-fetch.

**Extraction, first success wins:** (1) shop-specific extractor (`extract/shops/<shop>.py`, CSS selectors, one fixture test each); (2) generic: JSON-LD `schema.org/Book|Product`, OpenGraph, `<meta name="isbn">`, ISBN-10/13 with checksum on URL and text, `<title>` heuristics (`Title — Author | Shop`, RU `Название. Автор — купить`); (3) cheap-LLM fallback on visible text ≤ 4k tokens, strict JSON; (4) tab title only → `needs_review=true`.

`BookMetadata`: `title, subtitle, authors[], isbn13, isbn10, publisher, year, language, pages, series, series_index, description, cover_url, price, currency, availability, format`. Only `title` required. **Price**: native currency of the shop (CHF, RUB, EUR, USD, …), stored only when the page shows it; never looked up elsewhere.

**Dedup (polars):** one `book` per work. Merge key: `isbn13`, else normalised `(title, first_author)` (lowercase, strip punctuation/diacritics, RU→LAT transliteration for matching only). Every tab becomes a `source`; `book.selection_count` = number of tabs that pointed at it (the operator hoarded it more than once; node size in the graph).

### Stage 5 — tag

`build_vocabulary()`: one strong-model call over all titles/authors → 15–40 topic slugs into `data/topics.yaml` (operator-editable; re-runs only propose additions).

`tag_books()`: batches of 20, strong model (`effort: low`), JSON:

| Property | Values | Used for |
|---|---|---|
| `kind` | `fiction` \| `nonfiction` \| `technical` | Lane |
| `topics[]` | 1–4 slugs from the vocabulary | Topic edges, colouring |
| `language` | ISO code of the edition as sold | Difficulty modifier, filter |
| `base_difficulty` | 1–10, content only (1 airport paperback … 10 graduate textbook), one-line reason | Difficulty |
| `est_hours` | `pages/30 · (0.7 + 0.05·difficulty)` when pages known, else model estimate | Plan timeline |
| `interest` | operator-set 1–5, default 3 (Graph view) | Plan scoring |

**Difficulty** = `min(10, base_difficulty + language_modifier)`; modifiers in `config.py`: `{ru: 0, en: 0, fr: +2, de: +4, other: +4}`. Operator overrides (Graph view side panel) are stored in `book_property_override` and never overwritten by re-tagging.

Embedding: `title + authors + description + topics` → `qwen/qwen3-embedding-8b` via OpenRouter `/v1/embeddings`, batched 50 per call, stored on the book.

### Stage 6 — link

Edges built by walking the property hierarchy, most important first.

| Rank | Property | Edge type | Weight | Rule |
|---|---|---|---|---|
| 0 | identity | — | — | Same work → merged in dedup. |
| 1 | author | `author` | 1.0 | Shared author. |
| 2 | series | `series` | 0.9 | Same series; carries `order`. |
| 3 | topic | `topic` | 0.6 × Jaccard | Shared topic slugs. |
| 4 | similarity | `similar` | cos − 0.65 if cos ≥ 0.75 | Embedding cosine, top-5 per node. |
| 5 | publisher | `publisher` | 0.2 | Off by default in UI. |
| 6 | shop | `shop` | 0.1 | Off by default in UI. |

Cross-kind edges are flagged `cross_lane`; the planner rewards them. `GET /graph` returns `{nodes, edges}`.

### Stage 7 — plan: Balanced Lane Walk

Three lanes read concurrently; **the mean difficulty of the three open books stays within a band around a target.**

Inputs: graph; books with `kind, difficulty, est_hours, interest, status`; target `T` (default: mean difficulty of all unread books, rounded to 0.5; slider in Plan view); tolerance `tol` (default 1.0; slider); optional seeds; exclusions (`status ∈ {read, abandoned}`); `horizon` (default 30).

Feasible candidate `c` for lane `l`: `|mean(difficulty(c), difficulty(other two)) − T| ≤ tol`.

1. **Seed** empty lanes (technical first, least slack): highest-`interest` feasible book; ties → difficulty closest to `T`, then title.
2. **Simulate**: the lane with the smallest `remaining_hours` finishes next; append that book to the plan.
3. **Choose next** among feasible unread books of its kind, maximising
   `score(c) = 3·w(prev_l, c) + 2·Σ_o w(current[o], c) + interest(c) − penalty(c)`
   (`w` = max edge weight, 2-hop at half weight, 0 if none; `penalty` +1 same author as last two in lane, +1 all three lanes share a topic). Terms: continuity, cross-pollination, priority.
4. **Beam search** width 5 over the next 6 transitions.
5. Nothing feasible → widen `tol` by 0.5 for that pick and record a warning.
6. Stop at `horizon` or when a lane runs out.

Output: `reading_plan` + ordered `plan_item(lane, position, book, reason)`; `reason` says which term won. Pure, deterministic code; same inputs → same plan. Re-running regenerates from scratch (incremental replan is deferred).

---

## Data model (SQLite, `dehoarder/db/models.py`)

```
schema_version   version
scan             id, started_at, source (extension|snss), profile_name, tab_count
tab              id, scan_id, browser_tab_id?, window_id?, url, title, discarded, last_accessed?,
                 domain, classification (known_shop|unknown_book|not_book), shop_id?,
                 decision (close|keep|pending), archived_at?, closed_at?, close_error?,
                 book_id?, process_status (pending|fetched|extracted|failed|skipped), process_error?
shop             id, slug, name, domains (json), kind (bookshop|publisher|marketplace), currency?,
                 min_interval_s, extractor?, learned, blocked_until?
book             id, title, subtitle, authors (json), isbn13, isbn10, publisher, year, language, pages,
                 series, series_index, description, cover_url, merge_key, selection_count,
                 kind?, topics (json), base_difficulty?, difficulty?, difficulty_reason?, est_hours?,
                 interest (default 3), embedding (json)?, needs_review, status (unread|reading|read|abandoned),
                 created_at, updated_at
book_property_override   book_id, field, value, set_at
source           id, book_id, tab_id?, shop_id, url, price?, currency?, availability?, format?, fetched_at
edge             id, src_book_id, dst_book_id, type, weight, meta (json), cross_lane
reading_plan     id, created_at, target, tol, horizon, seeds (json), warnings (json)
plan_item        id, plan_id, lane, position, book_id, reason
job              id, kind (chain|scan|classify|close|process|tag|link|plan), status, stage, progress (json), error?, started_at, finished_at
llm_call         id, stage, model, prompt_hash, input_tokens, output_tokens, cost_usd, response?, created_at
bridge           extension_id, version, last_seen
```

`shops.yaml` seed (learned entries appended with `learned: true`):

```yaml
- {slug: amazon,       domains: [amazon.com, amazon.de, amazon.co.uk, amazon.fr], kind: marketplace, extractor: amazon}
- {slug: abebooks,     domains: [abebooks.com, abebooks.de, abebooks.co.uk],       kind: marketplace, extractor: abebooks}
- {slug: bookvoed,     domains: [bookvoed.ru],                                      kind: bookshop,    currency: RUB, extractor: bookvoed}
- {slug: chitai-gorod, domains: [chitai-gorod.ru],                                  kind: bookshop,    currency: RUB, extractor: chitai_gorod}
- {slug: manning,      domains: [manning.com],                                      kind: publisher,   currency: USD, extractor: manning}
- {slug: mccme,        domains: [biblio.mccme.ru, mccme.ru],                        kind: publisher,   currency: RUB}
- {slug: azbooka,      domains: [azbooka.ru],                                       kind: publisher,   currency: RUB}
- {slug: nordlux,      domains: [nordlux.org],                                      kind: bookshop}
- {slug: totenburg,    domains: [totenburg.org],                                    kind: bookshop}
- {slug: taschen,      domains: [taschen.com],                                      kind: publisher,   currency: EUR}
```

---

## Interfaces

### CLI

| Command | Purpose |
|---|---|
| `serve [--port 8765] [--no-open]` | Start API + UI, open the browser. The only command the operator normally runs. |
| `status` | Read-only overview (stages, counts, LLM spend). |
| `db init` | Create the SQLite file. |
| `run <scan-snss\|classify\|process\|tag\|link\|plan> [--limit N]` | Non-interactive stage runner for development and tests. No prompts, ever. |

### API (`/api/v1`)

Scans/tabs: `POST /scans` (tab list from extension) · `POST /scans/snss` · `GET /scans` · `GET /tabs?scan=&classification=` · `PATCH /tabs/{id}` · `PATCH /tabs?scan=&shop=` · `POST /scans/{id}/archive` · `POST /scans/{id}/closed` · `GET /scans/{id}/restore-list` · `POST /scans/{id}/restored`.
Shops: `GET /shops` · `POST /shops/learn`.
Jobs: `POST /jobs/chain` (close-and-process chain) · `POST /jobs/{stage}` · `GET /jobs/{id}` · `GET /jobs`.
Books/graph/plan: `GET /books` · `GET /books/{id}` · `PATCH /books/{id}` · `GET /graph?edge_types=` · `GET /plans` · `GET /plans/{id}` · `POST /plans`.
Bridge: `POST /bridge/hello` · `GET /bridge/status` · `GET /status`.
Everything binds to `127.0.0.1` only.

### Web app (English)

Top bar: stage stepper (Scan · Review · Close · Process · Tag · Link · Plan) + navigation **Tabs · Progress · Graph · Plan**.

1. **Tabs** — "Scan now" (extension) / "Read session file" (fallback); grouped inventory with decisions; **Close approved (N)**; "Reopen closed tabs" per past scan; extension-not-detected banner with install steps.
2. **Progress** — current job chain: per-stage progress bars, per-shop fetch counts, paused/blocked domains, LLM spend; errors inline.
3. **Graph** — sigma.js canvas: colour = kind, size = `selection_count`, edge-type toggles, search; click → side panel: metadata, difficulty (+ reason), language, sources with price/currency and outbound link, editable kind/topics/difficulty/interest/status.
4. **Plan** — three lanes on a shared timeline (width = `est_hours`), cards with difficulty and `reason`; target and tolerance sliders regenerate; "Regenerate" button.

---

## Extensibility (constraint, not v1 work)

`book.kind` and `tab.classification` are the only places "book" is assumed. Videos/articles later = a generalised `item` table, a new registry entry type, a new extractor, a new lane definition. Keep stage boundaries clean; do not generalise now.

## Non-goals (v1)

Shopping carts (future; web agent with the operator watching), purchasing, non-book tabs, videos/articles, ISBN enrichment via Open Library/Google Books, Obsidian export, incremental replan, price watch, interactive profile picker beyond the fallback dropdown, Rust, Capacitor, Postgres, cloud anything.

---

## Decisions (all questions resolved)

Extension lists/closes/reopens, driven from the web app; SNSS read-only fallback for inventory · current profile = whatever the extension runs in; SNSS fallback uses last-used, names from `Local State` · SQLite · OpenRouter models as in the stack table · carts deferred · non-book tabs always left open · one node per book + `selection_count` · branch per phase, merge to `main`, no PRs · native currency when shown · English UI, language is a property feeding difficulty (`fr +2`, `de +4`, other `+4`) · tolerance default ±1.0, slider in UI · `restore` kept · no terminal confirmations · LLM completions cached in `llm_call.response` keyed by `prompt_hash` (schema v2; embedding calls log spend only, no response).

## Deferred

ISBN enrichment · Obsidian export · incremental replan · price watch · shopping carts via web agent · videos and articles · owned/read-book import.
