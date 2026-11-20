"""Shop registry: hostname matching, DB sync, and the learned-shop round-trip."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from sqlalchemy import select

import dehoarder.db.session as db_session
from dehoarder.classify import registry
from dehoarder.config import DATA_DIR
from dehoarder.db.models import Shop, ShopKind


@pytest.fixture
def shops_file(tmp_path: Path) -> Path:
    path = tmp_path / "shops.yaml"
    shutil.copy(DATA_DIR / "shops.yaml", path)
    return path


def test_seed_loads_in_file_order(shops_file: Path) -> None:
    entries = registry.load(shops_file)
    assert [e.slug for e in entries][:3] == ["amazon", "abebooks", "bookvoed"]
    assert len(entries) == 10
    chitai = next(e for e in entries if e.slug == "chitai-gorod")
    assert chitai.name == "Chitai Gorod"
    assert chitai.currency == "RUB"
    assert chitai.extractor == "chitai_gorod"
    assert chitai.kind is ShopKind.bookshop
    assert not chitai.learned


@pytest.mark.parametrize(
    ("host", "slug"),
    [
        ("www.amazon.de", "amazon"),
        ("amazon.co.uk", "amazon"),
        ("smile.amazon.com", "amazon"),
        ("WWW.Manning.COM", "manning"),
        ("biblio.mccme.ru", "mccme"),
        ("shop.mccme.ru", "mccme"),
        ("www.chitai-gorod.ru.", "chitai-gorod"),
    ],
)
def test_match_known_host(shops_file: Path, host: str, slug: str) -> None:
    entry = registry.match(host, registry.load(shops_file))
    assert entry is not None
    assert entry.slug == slug


@pytest.mark.parametrize("host", ["example.com", "notamazon.de", "ru", "", "amazon.es"])
def test_match_unknown_host(shops_file: Path, host: str) -> None:
    assert registry.match(host, registry.load(shops_file)) is None


def test_missing_file_is_empty_registry(tmp_path: Path) -> None:
    assert registry.load(tmp_path / "nope.yaml") == []


def test_sync_upserts_by_slug(shops_file: Path) -> None:
    entries = registry.load(shops_file)
    with db_session.SessionLocal() as session:
        registry.sync(session, entries)
        registry.sync(session, entries)
        session.commit()
        shops = list(session.scalars(select(Shop)))
    assert len(shops) == 10
    assert {s.slug for s in shops} == {e.slug for e in entries}


def test_learned_round_trip_appends_and_preserves_seed(shops_file: Path) -> None:
    before = shops_file.read_text(encoding="utf-8")

    entry = registry.add_learned("www.labirint.ru", "Лабиринт", path=shops_file)

    after = shops_file.read_text(encoding="utf-8")
    assert after.startswith(before)
    assert after.count("\n") == before.count("\n") + 1
    assert entry.slug == "labirint"
    assert entry.domains == ["labirint.ru"]
    assert entry.learned

    reloaded = registry.load(shops_file)
    seed_slugs = [e.slug for e in registry.load(DATA_DIR / "shops.yaml")]
    assert [e.slug for e in reloaded][:10] == seed_slugs
    learned = reloaded[-1]
    assert learned == entry
    assert learned.name == "Лабиринт"
    assert registry.match("labirint.ru", reloaded) == learned


def test_add_learned_is_idempotent(shops_file: Path) -> None:
    first = registry.add_learned("labirint.ru", "Labirint", path=shops_file)
    text = shops_file.read_text(encoding="utf-8")

    again = registry.add_learned("www.labirint.ru", "Labirint", path=shops_file)
    known = registry.add_learned("amazon.de", "Amazon DE", path=shops_file)

    assert again == first
    assert known.slug == "amazon"
    assert shops_file.read_text(encoding="utf-8") == text


def test_add_learned_avoids_slug_clash(shops_file: Path) -> None:
    entry = registry.add_learned("manning.co.uk", "Manning UK", path=shops_file)
    assert entry.slug == "manning-co-uk"


def test_add_learned_rejects_non_domain(shops_file: Path) -> None:
    with pytest.raises(ValueError):
        registry.add_learned("localhost", "x", path=shops_file)
