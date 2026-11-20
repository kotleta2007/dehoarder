"""GET /api/v1/shops and POST /api/v1/shops/learn."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dehoarder.config import DATA_DIR, settings


@pytest.fixture(autouse=True)
def _shops_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "shops.yaml"
    shutil.copy(DATA_DIR / "shops.yaml", path)
    monkeypatch.setattr(settings, "shops_file", path)
    return path


def test_get_shops_returns_seed_in_file_order(client: TestClient) -> None:
    response = client.get("/api/v1/shops")
    assert response.status_code == 200
    shops = response.json()
    assert [s["slug"] for s in shops][:2] == ["amazon", "abebooks"]
    assert len(shops) == 10
    assert shops[0]["domains"] == ["amazon.com", "amazon.de", "amazon.co.uk", "amazon.fr"]


def test_learn_adds_shop_and_writes_yaml(client: TestClient, _shops_file: Path) -> None:
    response = client.post(
        "/api/v1/shops/learn", json={"domain": "www.labirint.ru", "name": "Labirint"}
    )
    assert response.status_code == 200
    shop = response.json()
    assert shop["slug"] == "labirint"
    assert shop["learned"] is True
    assert shop["kind"] == "bookshop"

    assert "labirint.ru" in _shops_file.read_text(encoding="utf-8")
    slugs = [s["slug"] for s in client.get("/api/v1/shops").json()]
    assert slugs[-1] == "labirint"
    assert len(slugs) == 11


def test_learn_rejects_bad_domain(client: TestClient) -> None:
    response = client.post("/api/v1/shops/learn", json={"domain": "localhost"})
    assert response.status_code == 422
