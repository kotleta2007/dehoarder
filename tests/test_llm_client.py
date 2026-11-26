"""OpenRouter client against a fake transport: request shape, logging,
prompt-hash cache, embeddings batching."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

import dehoarder.db.session as db_session
from dehoarder.config import settings
from dehoarder.db.models import LlmCall
from dehoarder.llm.client import LlmClient, LlmError, Tier, render_prompt


class Verdict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_bookshop: bool
    shop_name: str
    kind: str
    confidence: float


class FakeOpenRouter:
    """Records requests; answers chat with `content`, embeddings with index vectors."""

    def __init__(self, content: str = "") -> None:
        self.content = content
        self.requests: list[dict[str, Any]] = []
        self.paths: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        self.paths.append(request.url.path)
        assert request.headers["Authorization"] == "Bearer test-key"
        usage = {"prompt_tokens": 100, "completion_tokens": 20, "cost": 0.0012}
        if request.url.path.endswith("/embeddings"):
            data = [
                {"index": i, "embedding": [float(len(text)), float(i)]}
                for i, text in reversed(list(enumerate(body["input"])))
            ]
            return httpx.Response(200, json={"data": data, "usage": usage})
        return httpx.Response(
            200, json={"choices": [{"message": {"content": self.content}}], "usage": usage}
        )

    def client(self) -> LlmClient:
        return LlmClient(api_key="test-key", transport=httpx.MockTransport(self))


GOOD = json.dumps(
    {"is_bookshop": True, "shop_name": "Labirint", "kind": "bookshop", "confidence": 0.9}
)
VARS = {"domain": "labirint.ru", "samples": "- https://labirint.ru/books/1 — Книга"}


def _calls() -> list[LlmCall]:
    with db_session.SessionLocal() as session:
        return list(session.scalars(select(LlmCall).order_by(LlmCall.id)))


async def test_complete_sends_schema_and_logs_spend() -> None:
    fake = FakeOpenRouter(GOOD)
    result = await fake.client().complete(
        "classify_domain", VARS, Tier.cheap, Verdict, stage="classify"
    )

    assert result == Verdict(
        is_bookshop=True, shop_name="Labirint", kind="bookshop", confidence=0.9
    )
    body = fake.requests[0]
    assert fake.paths == ["/api/v1/chat/completions"]
    assert body["model"] == settings.llm_cheap_model
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["schema"]["additionalProperties"] is False
    assert "reasoning" not in body
    assert "labirint.ru" in body["messages"][0]["content"]

    [call] = _calls()
    assert (call.stage, call.model, call.input_tokens, call.output_tokens) == (
        "classify",
        settings.llm_cheap_model,
        100,
        20,
    )
    assert call.cost_usd == pytest.approx(0.0012)
    assert call.response == GOOD


async def test_strong_tier_with_effort() -> None:
    fake = FakeOpenRouter(GOOD)
    await fake.client().complete("classify_domain", VARS, Tier.strong, Verdict, effort="low")
    assert fake.requests[0]["model"] == settings.llm_strong_model
    assert fake.requests[0]["reasoning"] == {"effort": "low"}


async def test_cache_hit_skips_call() -> None:
    fake = FakeOpenRouter(GOOD)
    client = fake.client()
    first = await client.complete("classify_domain", VARS, Tier.cheap, Verdict)
    second = await client.complete("classify_domain", VARS, Tier.cheap, Verdict)

    assert first == second
    assert len(fake.requests) == 1
    assert len(_calls()) == 1


async def test_cache_is_keyed_by_prompt_model_and_effort() -> None:
    fake = FakeOpenRouter(GOOD)
    client = fake.client()
    await client.complete("classify_domain", VARS, Tier.cheap, Verdict)
    await client.complete("classify_domain", {**VARS, "domain": "ozon.ru"}, Tier.cheap, Verdict)
    await client.complete("classify_domain", VARS, Tier.strong, Verdict)
    await client.complete("classify_domain", VARS, Tier.strong, Verdict, effort="low")
    assert len(fake.requests) == 4


async def test_fenced_json_is_accepted() -> None:
    fake = FakeOpenRouter(f"```json\n{GOOD}\n```")
    result = await fake.client().complete("classify_domain", VARS, Tier.cheap, Verdict)
    assert result.shop_name == "Labirint"


async def test_invalid_answer_raises_logs_spend_and_is_not_cached() -> None:
    fake = FakeOpenRouter('{"is_bookshop": "maybe"}')
    client = fake.client()
    with pytest.raises(LlmError):
        await client.complete("classify_domain", VARS, Tier.cheap, Verdict)
    [call] = _calls()
    assert call.response is None

    fake.content = GOOD
    result = await client.complete("classify_domain", VARS, Tier.cheap, Verdict)
    assert result.is_bookshop
    assert len(fake.requests) == 2


async def test_http_error_raises() -> None:
    client = LlmClient(
        api_key="test-key",
        transport=httpx.MockTransport(lambda r: httpx.Response(429, text="rate limited")),
    )
    with pytest.raises(LlmError, match="429"):
        await client.complete("classify_domain", VARS, Tier.cheap, Verdict)
    assert _calls() == []


async def test_missing_api_key_raises_before_any_request() -> None:
    fake = FakeOpenRouter(GOOD)
    client = LlmClient(api_key="", transport=httpx.MockTransport(fake))
    with pytest.raises(LlmError, match="OPENROUTER_API_KEY"):
        await client.complete("classify_domain", VARS, Tier.cheap, Verdict)
    assert fake.requests == []


async def test_embed_batches_fifty_and_keeps_order() -> None:
    fake = FakeOpenRouter()
    texts = [f"book {i}" for i in range(120)]
    vectors = await fake.client().embed(texts, stage="tag")

    assert [len(r["input"]) for r in fake.requests] == [50, 50, 20]
    assert all(r["model"] == settings.embedding_model for r in fake.requests)
    assert vectors[0] == [6.0, 0.0]
    assert vectors[119] == [8.0, 19.0]  # index within the third batch
    assert len(vectors) == 120
    calls = _calls()
    assert len(calls) == 3
    assert all(c.response is None for c in calls)


def test_render_prompt_fills_and_keeps_literal_braces() -> None:
    text = render_prompt("classify_domain", VARS)
    assert "`labirint.ru`" in text
    assert '{"is_bookshop": true' in text
    assert "{{" not in text


def test_render_prompt_missing_variable() -> None:
    with pytest.raises(KeyError, match="samples"):
        render_prompt("classify_domain", {"domain": "x.ru"})
