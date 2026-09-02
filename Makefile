.PHONY: dev check test build-web

dev:
	uv run uvicorn dehoarder.api.app:app --reload --port 8765

check:
	uv run ruff check .
	uv run mypy dehoarder
	uv run pytest
	@if [ -d web ]; then cd web && npm run lint && npm run check; fi

test:
	uv run pytest

build-web:
	cd web && npm install && npm run build
