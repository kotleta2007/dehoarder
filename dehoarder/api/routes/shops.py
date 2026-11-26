"""Shop routes: list the registry, and learn a new shop from an unknown
domain ("Learn & close" in the Tabs view). Learning also re-files that
domain's `unknown_book` tabs as `known_shop`; the Tabs view then sets their
decision with `PATCH /tabs?scan=&shop=`.

Both sync `data/shops.yaml` into the `shop` table first, so operator edits
to the YAML show up without a restart.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

import dehoarder.db.session as db_session
from dehoarder.classify import registry
from dehoarder.classify.classify import attach_learned_shop
from dehoarder.db.models import Shop, ShopKind

router = APIRouter(prefix="/api/v1/shops", tags=["shops"])


class ShopOut(BaseModel):
    id: int
    slug: str
    name: str
    domains: list[str]
    kind: ShopKind
    currency: str | None
    extractor: str | None
    learned: bool


class LearnIn(BaseModel):
    domain: str
    name: str = ""
    kind: ShopKind = ShopKind.bookshop


def _serialize(shop: Shop) -> ShopOut:
    return ShopOut(
        id=shop.id,
        slug=shop.slug,
        name=shop.name,
        domains=list(shop.domains),
        kind=shop.kind,
        currency=shop.currency,
        extractor=shop.extractor,
        learned=shop.learned,
    )


@router.get("", response_model=list[ShopOut])
def list_shops() -> list[ShopOut]:
    entries = registry.load()
    order = {entry.slug: i for i, entry in enumerate(entries)}
    with db_session.SessionLocal() as session:
        registry.sync(session, entries)
        session.commit()
        shops = list(session.scalars(select(Shop)))
        shops.sort(key=lambda s: (order.get(s.slug, len(order)), s.slug))
        return [_serialize(s) for s in shops]


@router.post("/learn", response_model=ShopOut)
def learn_shop(payload: LearnIn) -> ShopOut:
    try:
        entry = registry.add_learned(payload.domain, payload.name, payload.kind)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    with db_session.SessionLocal() as session:
        registry.sync(session, registry.load())
        session.commit()
    attach_learned_shop(entry)
    with db_session.SessionLocal() as session:
        shop = session.scalars(select(Shop).where(Shop.slug == entry.slug)).one()
        return _serialize(shop)
