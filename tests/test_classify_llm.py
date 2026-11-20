"""Unknown-domain classifier: prompt contents and verdict → classification mapping."""

from __future__ import annotations

import json

import httpx
import pytest

from dehoarder.classify.llm import DomainVerdict, classify_domain, to_classification
from dehoarder.db.models import Classification, ShopKind
from dehoarder.llm.client import LlmClient


async def test_classify_domain_sends_at_most_ten_samples() -> None:
    sent: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content)["messages"][0]["content"])
        answer = {
            "is_bookshop": True,
            "shop_name": "Labirint",
            "kind": "bookshop",
            "confidence": 0.95,
        }
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps(answer)}}], "usage": {}}
        )

    samples = [(f"https://www.labirint.ru/books/{i}/", f"Книга {i}") for i in range(15)]
    client = LlmClient(api_key="k", transport=httpx.MockTransport(handler))
    verdict = await classify_domain("labirint.ru", samples, client)

    assert verdict.kind is ShopKind.bookshop
    assert verdict.shop_name == "Labirint"
    [prompt] = sent
    assert "https://www.labirint.ru/books/9/ — Книга 9" in prompt
    assert "/books/10/" not in prompt


@pytest.mark.parametrize(
    ("is_bookshop", "confidence", "expected"),
    [
        (True, 0.9, Classification.unknown_book),
        (True, 0.5, Classification.unknown_book),
        (True, 0.49, Classification.not_book),
        (False, 0.99, Classification.not_book),
        (False, 0.1, Classification.not_book),
    ],
)
def test_to_classification(is_bookshop: bool, confidence: float, expected: Classification) -> None:
    verdict = DomainVerdict(
        is_bookshop=is_bookshop, shop_name="X", kind=ShopKind.bookshop, confidence=confidence
    )
    assert to_classification(verdict) is expected


def test_verdict_rejects_out_of_range_confidence() -> None:
    with pytest.raises(ValueError):
        DomainVerdict(is_bookshop=True, shop_name="X", kind=ShopKind.bookshop, confidence=1.5)
