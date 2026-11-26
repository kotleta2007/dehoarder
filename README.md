# dehoarder

Declutter your browser from book tabs.

Dehoarder is a local tool for people who keep hundreds of bookshop tabs open
"for later". It turns that hoard into something you can actually use, and
frees the RAM those tabs were holding.

```
unstructured data (tabs)  →  semantic structure (graph)  →  a new way to traverse it (lane walk)
```

## What it does

1. **Frees RAM.** It lists every tab in your browser profile, sorts out
   the ones that are books, and closes them only after you confirm in the web
   app. Every closed tab is first written to an append-only archive, and any
   batch can be reopened later. Your browser's session files are never
   written.
2. **Builds a local catalogue.** Each book tab becomes a `book` record (title,
   authors, ISBN, publisher, language, pages, …) with one or more sources: the
   shops where you found it, with the price when the shop shows one.
3. **Draws a semantic graph.** Books are linked by author, series, topic,
   embedding similarity, publisher and shop. You can explore the graph in the
   web app, and each node links back to the original page.
4. **Makes a reading plan.** Three parallel lanes (fiction, non-fiction,
   technical) are walked through the graph so that the combined difficulty
   of the three books you are reading stays steady over time.

Priorities, in order: free RAM, then the catalogue, then the graph, then the
plan.

### How you use it

You run one command, `dehoarder serve`, and everything else happens in
the web app it opens: scanning tabs, reviewing which to close, confirming the
close, watching progress, exploring the graph and reading the plan. The
terminal never asks you anything.

### Design principles

- **Lightweight.** One Python process, one SQLite file, one small browser
  extension, no services or containers. Everything runs locally and binds to
  `127.0.0.1` only.
- **Never lose a tab.** Tabs are archived before they are closed, and the
  **Reopen closed tabs** action can bring them back.
- **Deterministic code does the dangerous things.** Plain code closes tabs and
  writes the database, and only after you click to confirm. The LLM only
  classifies, extracts, tags and rates; it never has access to the browser or
  the filesystem.
- **Pure-code planning.** The reading plan is a deterministic graph traversal,
  so the same inputs always give the same plan.

## Status

Under active development, phase by phase (see [`GAMEPLAN.md`](GAMEPLAN.md)).
These parts work so far:

- the browser extension, which lists, closes and reopens tabs on request from
  the web app;
- scanning tabs into the local database, shown in the **Tabs** view;
- a read-only fallback scan from the browser's session file, for when the
  extension is not installed.

Classification, closing, fetching, tagging, the graph and the plan are coming
in later phases.

## Installation

### Requirements

- Linux with a Chromium-based browser. Dehoarder is built around
  [Thorium](https://thorium.rocks/), and its profiles are read from
  `~/.config/thorium/`.
- Python 3.12 and [`uv`](https://docs.astral.sh/uv/)
- Node.js 20+ and npm, to build the web app
- An [OpenRouter](https://openrouter.ai/keys) API key. Later stages use it
  for classification, tagging and embeddings; scanning works without it.

### 1. Get the code and install dependencies

```sh
git clone https://github.com/kotleta2007/dehoarder.git
cd dehoarder
uv sync
```

### 2. Configure

```sh
cp .env.example .env
```

Put your `OPENROUTER_API_KEY` in `.env`. The model ids already have defaults.
If your browser profiles are not in `~/.config/thorium`, set `THORIUM_DIR` in
`.env`.

### 3. Build the web app

```sh
make build-web        # npm install + vite build → web/dist
```

### 4. Create the database

```sh
uv run dehoarder db init
```

This creates `dehoarder.db` (SQLite) in the current directory.

### 5. Load the browser extension (once)

1. Open `chrome://extensions` in your browser.
2. Turn on **Developer mode** (top right).
3. Click **Load unpacked** and select the `extension/` directory of this
   repository.

The extension only sees the profile it is installed in. Without it, Dehoarder
can still read your tabs from the session file, but it cannot close them.
See [`extension/README.md`](extension/README.md) for details.

### 6. Run

```sh
uv run dehoarder serve
```

This starts the server on `http://127.0.0.1:8765` and opens the browser. Use
`--port` to change the port, or `--no-open` to stop it from opening the browser.
Then go to the **Tabs** view and click **Scan now**.

## Development

```sh
make check    # ruff, mypy, pytest, plus eslint/prettier/svelte-check/vitest for web/ and the extension
make dev      # Vite dev server + uvicorn with reload
```

Other CLI commands, mainly for development:

| Command | Purpose |
|---|---|
| `dehoarder status` | Read-only overview of stages and counts |
| `dehoarder db init` | Create the SQLite file |
| `dehoarder run <stage> [--limit N]` | Run one pipeline stage without the UI (no prompts) |

Architecture, data model and pipeline details are in
[`CLAUDE.md`](CLAUDE.md). The step-by-step build plan is in
[`GAMEPLAN.md`](GAMEPLAN.md).

## License

[GNU Affero General Public License v3.0](LICENSE).
