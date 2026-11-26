"""Shop registry: the known bookshops and publishers in `data/shops.yaml`.

`load()` reads the YAML, `match()` maps a hostname to a shop by checking the
hostname and each parent domain (so `www.amazon.de` and `smile.amazon.de`
both match `amazon.de`), and `sync()` upserts the entries into the `shop`
table by slug.

`add_learned()` is how "Learn & close" in the Tabs view grows the registry.
It **appends** one line to the YAML file and never rewrites it, so the seed
order, alignment and comments survive.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from dehoarder.config import settings
from dehoarder.db.models import Shop, ShopKind


@dataclass(frozen=True)
class ShopEntry:
    slug: str
    name: str
    domains: list[str]
    kind: ShopKind
    currency: str | None = None
    min_interval_s: float = field(default_factory=lambda: settings.default_min_interval_s)
    extractor: str | None = None
    learned: bool = False


def normalise_host(host: str) -> str:
    """Lowercase, strip a trailing dot and a leading `www.`."""
    return host.strip().lower().rstrip(".").removeprefix("www.")


def _name_from_slug(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").title()


def _entry_from_raw(raw: dict[str, Any]) -> ShopEntry:
    slug = str(raw["slug"])
    return ShopEntry(
        slug=slug,
        name=str(raw.get("name") or _name_from_slug(slug)),
        domains=[normalise_host(str(d)) for d in raw["domains"]],
        kind=ShopKind(raw["kind"]),
        currency=raw.get("currency"),
        min_interval_s=float(raw.get("min_interval_s", settings.default_min_interval_s)),
        extractor=raw.get("extractor"),
        learned=bool(raw.get("learned", False)),
    )


def load(path: Path | None = None) -> list[ShopEntry]:
    """Read the registry, in file order. A missing file is an empty registry."""
    path = path or settings.shops_file
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    return [_entry_from_raw(item) for item in raw]


def match(host: str, entries: list[ShopEntry]) -> ShopEntry | None:
    """Return the shop owning `host` or one of its parent domains.

    The most specific domain wins: `biblio.mccme.ru` is tried before
    `mccme.ru`. A bare TLD (`ru`) is never tried.
    """
    by_domain = {domain: entry for entry in entries for domain in entry.domains}
    labels = normalise_host(host).split(".")
    for i in range(len(labels) - 1):
        entry = by_domain.get(".".join(labels[i:]))
        if entry is not None:
            return entry
    return None


def sync(session: Session, entries: list[ShopEntry]) -> None:
    """Upsert every entry into the `shop` table by slug. Does not commit.

    `blocked_until` is runtime state owned by the fetcher and is left alone.
    """
    existing = {shop.slug: shop for shop in session.scalars(select(Shop))}
    for entry in entries:
        shop = existing.get(entry.slug)
        if shop is None:
            shop = Shop(slug=entry.slug)
            session.add(shop)
        shop.name = entry.name
        shop.domains = list(entry.domains)
        shop.kind = entry.kind
        shop.currency = entry.currency
        shop.min_interval_s = entry.min_interval_s
        shop.extractor = entry.extractor
        shop.learned = entry.learned


# Two-label public suffixes common for shops; enough for slug naming only.
_TWO_LABEL_SUFFIXES = {"co.uk", "org.uk", "com.au", "co.jp", "co.nz", "com.br", "com.ua"}


def _slug_for(domain: str, taken: set[str]) -> str:
    """`labirint.ru` → `labirint`, `foo.co.uk` → `foo`; on a clash, the
    whole domain dashed."""
    labels = domain.split(".")
    suffix_len = 2 if ".".join(labels[-2:]) in _TWO_LABEL_SUFFIXES else 1
    candidate = labels[-suffix_len - 1] if len(labels) > suffix_len else labels[0]
    if candidate in taken:
        candidate = domain.replace(".", "-")
    n = 2
    base = candidate
    while candidate in taken:
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def add_learned(
    domain: str,
    name: str,
    kind: ShopKind = ShopKind.bookshop,
    path: Path | None = None,
) -> ShopEntry:
    """Append a learned shop for `domain` to the registry file.

    Idempotent: if `domain` (or a parent of it) already belongs to a shop,
    that shop is returned and the file is not touched.
    """
    path = path or settings.shops_file
    domain = normalise_host(domain)
    if "." not in domain:
        raise ValueError(f"not a domain: {domain!r}")

    entries = load(path)
    existing = match(domain, entries)
    if existing is not None:
        return existing

    slug = _slug_for(domain, {e.slug for e in entries})
    raw: dict[str, Any] = {
        "slug": slug,
        "name": name.strip() or _name_from_slug(slug),
        "domains": [domain],
        "kind": kind.value,
        "learned": True,
    }
    line = yaml.safe_dump(
        raw, default_flow_style=True, sort_keys=False, allow_unicode=True, width=10_000
    ).strip()

    path.parent.mkdir(parents=True, exist_ok=True)
    prefix = ""
    if path.exists():
        text = path.read_text(encoding="utf-8")
        if text and not text.endswith("\n"):
            prefix = "\n"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"{prefix}- {line}\n")

    return _entry_from_raw(raw)
