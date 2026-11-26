"""Classify stage end to end over a fixture scan, plus the review API:
GET /tabs, PATCH /tabs/{id}, PATCH /tabs?scan=&shop=|domain=, learn re-filing,
and the classify job started by a scan."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

import dehoarder.db.session as db_session
from dehoarder.classify.classify import classify_scan
from dehoarder.db.models import Tab
from dehoarder.jobs.stages import register_all
from dehoarder.llm.client import LlmClient

FIXTURE_TABS = [
    ("https://www.amazon.de/dp/3446264628", "Der Process"),
    ("https://www.amazon.com/dp/0262510871", "SICP"),
    ("https://github.com/books/repo", "books/repo"),
    ("https://example.com/", "Example Domain"),
    ("https://www.labirint.ru/books/1/", "Мастер и Маргарита"),
    ("https://www.labirint.ru/books/2/", "Война и мир"),
    ("https://reviews.example.org/post", "Dune review by Jane Critic"),
    ("https://www.ozon.ru/product/123/", "Something"),
]

# What the fake cheap model says, per domain; ozon.ru fails with HTTP 500.
ANSWERS = {
    "labirint.ru": {
        "is_bookshop": True,
        "shop_name": "Labirint",
        "kind": "bookshop",
        "confidence": 0.9,
    },
    "reviews.example.org": {
        "is_bookshop": False,
        "shop_name": "Reviews",
        "kind": "bookshop",
        "confidence": 0.8,
    },
}


class FakeModel:
    def __init__(self) -> None:
        self.domains: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        prompt = json.loads(request.content)["messages"][0]["content"]
        domain = prompt.split("domain `", 1)[1].split("`", 1)[0]
        self.domains.append(domain)
        if domain not in ANSWERS:
            return httpx.Response(500, text="upstream error")
        content = json.dumps(ANSWERS[domain])
        return httpx.Response(
            200, json={"choices": [{"message": {"content": content}}], "usage": {}}
        )


def _scan(client: TestClient) -> int:
    tabs = [
        {
            "windowId": 1,
            "id": i,
            "url": url,
            "title": title,
            "discarded": True,
            "lastAccessed": None,
        }
        for i, (url, title) in enumerate(FIXTURE_TABS)
    ]
    response = client.post("/api/v1/scans", json={"tabs": tabs})
    assert response.status_code == 201
    return int(response.json()["id"])


def _by_url(client: TestClient, scan_id: int) -> dict[str, dict[str, Any]]:
    return {t["url"]: t for t in client.get(f"/api/v1/tabs?scan={scan_id}").json()}


@pytest.fixture
def classified(client: TestClient) -> tuple[int, FakeModel]:
    scan_id = _scan(client)
    fake = FakeModel()
    classify_scan(scan_id, client=LlmClient(api_key="k", transport=httpx.MockTransport(fake)))
    return scan_id, fake


def test_registry_rules_and_llm(client: TestClient, classified: tuple[int, FakeModel]) -> None:
    scan_id, fake = classified
    tabs = _by_url(client, scan_id)

    def state(url: str) -> tuple[str, str]:
        return tabs[url]["classification"], tabs[url]["decision"]

    assert state("https://www.amazon.de/dp/3446264628") == ("known_shop", "close")
    assert tabs["https://www.amazon.de/dp/3446264628"]["shop"] == "amazon"
    assert tabs["https://www.amazon.de/dp/3446264628"]["shop_name"] == "Amazon"
    assert state("https://github.com/books/repo") == ("not_book", "keep")
    assert state("https://example.com/") == ("not_book", "keep")
    assert state("https://www.labirint.ru/books/1/") == ("unknown_book", "pending")
    assert state("https://www.labirint.ru/books/2/") == ("unknown_book", "pending")
    assert state("https://reviews.example.org/post") == ("not_book", "keep")
    # LLM failed for ozon.ru → left for the operator, not silently decided
    assert state("https://www.ozon.ru/product/123/") == ("unknown_book", "pending")

    assert sorted(fake.domains) == ["labirint.ru", "ozon.ru", "reviews.example.org"]


def test_without_api_key_candidates_go_to_review(client: TestClient) -> None:
    scan_id = _scan(client)
    result = classify_scan(scan_id, client=LlmClient(api_key=""))
    assert "OPENROUTER_API_KEY" in result["warning"]
    tabs = _by_url(client, scan_id)
    assert tabs["https://reviews.example.org/post"]["classification"] == "unknown_book"
    assert result["unknown_book"] == 4


def test_rerun_keeps_operator_decisions(
    client: TestClient, classified: tuple[int, FakeModel]
) -> None:
    scan_id, _ = classified
    amazon = _by_url(client, scan_id)["https://www.amazon.de/dp/3446264628"]
    client.patch(f"/api/v1/tabs/{amazon['id']}", json={"decision": "keep"})

    result = classify_scan(scan_id, client=LlmClient(api_key=""))
    assert result["tabs"] == 0
    assert _by_url(client, scan_id)[amazon["url"]]["decision"] == "keep"


def test_get_tabs_filters_by_classification(
    client: TestClient, classified: tuple[int, FakeModel]
) -> None:
    scan_id, _ = classified
    known = client.get(f"/api/v1/tabs?scan={scan_id}&classification=known_shop").json()
    assert {t["shop"] for t in known} == {"amazon"}
    assert len(known) == 2


def test_patch_single_tab(client: TestClient, classified: tuple[int, FakeModel]) -> None:
    scan_id, _ = classified
    tabs = _by_url(client, scan_id)

    amazon = tabs["https://www.amazon.de/dp/3446264628"]
    response = client.patch(f"/api/v1/tabs/{amazon['id']}", json={"decision": "keep"})
    assert response.status_code == 200
    assert response.json()["decision"] == "keep"

    github = tabs["https://github.com/books/repo"]
    response = client.patch(f"/api/v1/tabs/{github['id']}", json={"decision": "close"})
    assert response.status_code == 422

    assert client.patch("/api/v1/tabs/9999", json={"decision": "keep"}).status_code == 404
    assert client.patch(f"/api/v1/tabs/{amazon['id']}", json={"decision": "x"}).status_code == 422


def test_patch_closed_tab_is_refused(client: TestClient, classified: tuple[int, FakeModel]) -> None:
    from datetime import UTC, datetime

    scan_id, _ = classified
    amazon = _by_url(client, scan_id)["https://www.amazon.de/dp/3446264628"]
    with db_session.SessionLocal() as session:
        tab = session.get(Tab, amazon["id"])
        assert tab is not None
        tab.closed_at = datetime.now(UTC)
        session.commit()

    response = client.patch(f"/api/v1/tabs/{amazon['id']}", json={"decision": "keep"})
    assert response.status_code == 409


def test_patch_by_shop_and_domain(client: TestClient, classified: tuple[int, FakeModel]) -> None:
    scan_id, _ = classified
    base = f"/api/v1/tabs?scan={scan_id}"

    response = client.patch(f"{base}&shop=amazon", json={"decision": "keep"})
    assert response.json() == {"updated": 2}
    response = client.patch(f"{base}&domain=labirint.ru", json={"decision": "keep"})
    assert response.json() == {"updated": 2}
    tabs = _by_url(client, scan_id)
    assert tabs["https://www.amazon.com/dp/0262510871"]["decision"] == "keep"
    assert tabs["https://www.labirint.ru/books/1/"]["decision"] == "keep"

    # closing an unknown domain needs "Learn" first
    assert client.patch(f"{base}&domain=labirint.ru", json={"decision": "close"}).status_code == 422
    assert client.patch(f"{base}&shop=nope", json={"decision": "keep"}).status_code == 404
    assert client.patch(base, json={"decision": "keep"}).status_code == 422
    both = client.patch(f"{base}&shop=amazon&domain=x.ru", json={"decision": "keep"})
    assert both.status_code == 422


def test_learn_refiles_unknown_tabs_then_close(
    client: TestClient, classified: tuple[int, FakeModel]
) -> None:
    scan_id, _ = classified
    learned = client.post("/api/v1/shops/learn", json={"domain": "labirint.ru", "name": "Labirint"})
    assert learned.status_code == 200

    tabs = _by_url(client, scan_id)
    labirint = tabs["https://www.labirint.ru/books/1/"]
    assert (labirint["classification"], labirint["shop"], labirint["decision"]) == (
        "known_shop",
        "labirint",
        "pending",
    )
    response = client.patch(
        f"/api/v1/tabs?scan={scan_id}&shop=labirint", json={"decision": "close"}
    )
    assert response.json() == {"updated": 2}
    # ozon.ru was not learned and stays pending
    assert _by_url(client, scan_id)["https://www.ozon.ru/product/123/"]["decision"] == "pending"


def _wait_job(client: TestClient, job_id: int) -> dict[str, Any]:
    for _ in range(200):
        job: dict[str, Any] = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["status"] in ("done", "failed"):
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_scan_starts_classify_job(client: TestClient) -> None:
    register_all()
    tabs = [
        {
            "windowId": 1,
            "id": 1,
            "url": "https://www.amazon.de/dp/x",
            "title": "x",
            "discarded": False,
            "lastAccessed": None,
        }
    ]
    body = client.post("/api/v1/scans", json={"tabs": tabs}).json()
    assert body["classify_job_id"] is not None

    job = _wait_job(client, body["classify_job_id"])
    assert job["status"] == "done", job["error"]
    assert job["kind"] == "classify"
    assert job["progress"]["known_shop"] == 1
    [tab] = client.get(f"/api/v1/tabs?scan={body['id']}").json()
    assert (tab["classification"], tab["decision"]) == ("known_shop", "close")


def test_scan_without_registered_stage_has_no_job(client: TestClient) -> None:
    body = client.post("/api/v1/scans", json={"tabs": []}).json()
    assert body["classify_job_id"] is None


def test_classify_job_without_scan_fails(client: TestClient) -> None:
    register_all()
    job = client.post("/api/v1/jobs/classify").json()
    final = _wait_job(client, job["id"])
    assert final["status"] == "failed"
    assert "scan first" in final["error"]
