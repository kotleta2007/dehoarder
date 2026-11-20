"""OpenRouter client: OpenAI-compatible chat completions and embeddings.

`complete()` renders a prompt from `llm/prompts/<name>.md`, asks the model
for JSON matching a pydantic schema, validates the answer, and logs the call
(model, tokens, cost) in `llm_call`. Identical requests are answered from
`llm_call.response` without hitting the network: the cache key is a SHA-256
over model, messages, schema and reasoning effort.

`embed()` batches texts 50 per request and logs spend only (embeddings are
stored on the book by the tag stage, so caching them here would duplicate
megabytes for nothing).

This module only talks HTTP to OpenRouter and writes `llm_call` rows. It has
no access to the browser and touches no other table or file.
"""

from __future__ import annotations

import enum
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError
from sqlalchemy import select

import dehoarder.db.session as db_session
from dehoarder.config import settings
from dehoarder.db.models import LlmCall

PROMPTS_DIR = Path(__file__).parent / "prompts"
EMBED_BATCH = 50
TIMEOUT_S = 120.0

_PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")
_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.S)


class Tier(enum.StrEnum):
    cheap = "cheap"
    strong = "strong"


class LlmError(RuntimeError):
    pass


def render_prompt(name: str, variables: dict[str, Any]) -> str:
    """Load `prompts/<name>.md` and fill its `{{ var }}` placeholders.

    Plain substitution, not `str.format`, so prompts can show JSON examples
    with literal braces. A placeholder without a value is an error.
    """
    template = (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")

    def fill(m: re.Match[str]) -> str:
        key = m.group(1)
        if key not in variables:
            raise KeyError(f"prompt {name!r} needs variable {key!r}")
        value = variables[key]
        return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)

    return _PLACEHOLDER.sub(fill, template)


def _model_for(tier: Tier) -> str:
    return settings.llm_strong_model if tier is Tier.strong else settings.llm_cheap_model


def _hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _parse_json(content: str) -> Any:
    m = _FENCE.match(content)
    return json.loads(m.group(1) if m else content)


class LlmClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.openrouter_api_key
        self.base_url = (base_url or settings.openrouter_base_url).rstrip("/")
        self._transport = transport

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        if not self.api_key:
            raise LlmError("OPENROUTER_API_KEY is not set (see .env.example)")
        async with httpx.AsyncClient(transport=self._transport, timeout=TIMEOUT_S) as http:
            response = await http.post(
                f"{self.base_url}{path}",
                json=body,
                headers={"Authorization": f"Bearer {self.api_key}", "X-Title": "dehoarder"},
            )
        if response.status_code != 200:
            raise LlmError(
                f"OpenRouter {path} → HTTP {response.status_code}: {response.text[:300]}"
            )
        data: dict[str, Any] = response.json()
        if "error" in data:
            raise LlmError(f"OpenRouter {path} error: {data['error']}")
        return data

    @staticmethod
    def _log(
        stage: str, model: str, prompt_hash: str, usage: dict[str, Any], response: str | None
    ) -> None:
        with db_session.SessionLocal() as session:
            session.add(
                LlmCall(
                    stage=stage,
                    model=model,
                    prompt_hash=prompt_hash,
                    input_tokens=int(usage.get("prompt_tokens", 0)),
                    output_tokens=int(usage.get("completion_tokens", 0)),
                    cost_usd=float(usage.get("cost", 0.0)),
                    response=response,
                )
            )
            session.commit()

    @staticmethod
    def _cached(prompt_hash: str) -> str | None:
        with db_session.SessionLocal() as session:
            return session.scalars(
                select(LlmCall.response)
                .where(LlmCall.prompt_hash == prompt_hash, LlmCall.response.is_not(None))
                .order_by(LlmCall.id.desc())
                .limit(1)
            ).first()

    async def complete[T: BaseModel](
        self,
        prompt_name: str,
        variables: dict[str, Any],
        tier: Tier,
        schema: type[T],
        effort: str | None = None,
        stage: str = "",
    ) -> T:
        model = _model_for(tier)
        messages = [{"role": "user", "content": render_prompt(prompt_name, variables)}]
        json_schema = schema.model_json_schema()
        prompt_hash = _hash(
            {"model": model, "messages": messages, "schema": json_schema, "effort": effort}
        )

        cached = self._cached(prompt_hash)
        if cached is not None:
            try:
                return schema.model_validate(_parse_json(cached))
            except (ValueError, ValidationError):
                pass  # stale or corrupt cache entry: ask again

        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema.__name__, "strict": True, "schema": json_schema},
            },
            "usage": {"include": True},
        }
        if effort is not None:
            body["reasoning"] = {"effort": effort}

        data = await self._post("/chat/completions", body)
        try:
            content = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError) as exc:
            raise LlmError(f"unexpected completion shape: {str(data)[:300]}") from exc

        try:
            result = schema.model_validate(_parse_json(content))
        except (ValueError, ValidationError) as exc:
            # Log the spend, but do not cache an answer we could not use.
            self._log(stage, model, prompt_hash, data.get("usage", {}), None)
            raise LlmError(f"{prompt_name}: model returned invalid JSON: {exc}") from exc

        self._log(stage, model, prompt_hash, data.get("usage", {}), content)
        return result

    async def embed(self, texts: list[str], stage: str = "") -> list[list[float]]:
        model = settings.embedding_model
        vectors: list[list[float]] = []
        for start in range(0, len(texts), EMBED_BATCH):
            batch = texts[start : start + EMBED_BATCH]
            data = await self._post(
                "/embeddings", {"model": model, "input": batch, "usage": {"include": True}}
            )
            items = sorted(data["data"], key=lambda d: d["index"])
            if len(items) != len(batch):
                raise LlmError(f"embeddings: sent {len(batch)} texts, got {len(items)} vectors")
            vectors.extend(item["embedding"] for item in items)
            self._log(
                stage, model, _hash({"model": model, "input": batch}), data.get("usage", {}), None
            )
        return vectors
