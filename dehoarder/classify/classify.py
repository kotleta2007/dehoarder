"""Classify stage: registry → rules → cheap LLM, for every unclassified tab
of a scan.

1. `rules.classify_tab()` settles most tabs: registry hits become
   `known_shop` (default decision `close`), non-web pages, allowlisted
   domains and tabs without any book signal become `not_book` (`keep`).
2. The remaining `unknown_book_candidate` tabs are grouped by domain and the
   cheap model is asked once per domain (`classify/llm.py`). A confident yes
   → `unknown_book` (`pending`: the operator decides with "Learn & close" or
   "Keep"); anything else → `not_book` (`keep`).

If the LLM is unavailable (no API key) or fails for a domain, the domain is
treated as `unknown_book`: the operator reviews it rather than the tool
silently deciding. Nothing here closes a tab; `keep` and `pending` both
leave it open.

Only tabs with `classification IS NULL` are touched, so re-running is safe
and never overrides a decision the operator already made.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

import httpx
from sqlalchemy import select

import dehoarder.db.session as db_session
from dehoarder.classify import registry
from dehoarder.classify.llm import MAX_SAMPLES, classify_domain, to_classification
from dehoarder.classify.rules import RuleOutcome, classify_tab
from dehoarder.config import settings
from dehoarder.db.models import Classification, Decision, Shop, Tab
from dehoarder.jobs.runner import JobContext
from dehoarder.llm.client import LlmClient, LlmError

DEFAULT_DECISION = {
    Classification.known_shop: Decision.close,
    Classification.unknown_book: Decision.pending,
    Classification.not_book: Decision.keep,
}


async def _classify_domains(
    groups: dict[str, list[tuple[str, str]]], client: LlmClient
) -> dict[str, Classification]:
    """LLM verdict per domain; domains whose call failed are left out."""
    semaphore = asyncio.Semaphore(settings.global_concurrency)

    async def one(domain: str, samples: list[tuple[str, str]]) -> tuple[str, Classification | None]:
        async with semaphore:
            try:
                verdict = await classify_domain(domain, samples, client)
            except (LlmError, httpx.HTTPError):
                return domain, None
            return domain, to_classification(verdict)

    results = await asyncio.gather(*(one(d, s) for d, s in groups.items()))
    return {domain: cls for domain, cls in results if cls is not None}


def classify_scan(
    scan_id: int, ctx: JobContext | None = None, client: LlmClient | None = None
) -> dict[str, Any]:
    """Classify the scan's unclassified tabs; returns the counts it reports."""
    client = client or LlmClient()
    entries = registry.load()
    progress: dict[str, Any] = {"scan_id": scan_id, "phase": "rules"}

    def report() -> None:
        if ctx is not None:
            ctx.report(dict(progress))

    with db_session.SessionLocal() as session:
        registry.sync(session, entries)
        session.flush()
        shop_ids = {shop.slug: shop.id for shop in session.scalars(select(Shop))}

        tabs = list(
            session.scalars(
                select(Tab)
                .where(Tab.scan_id == scan_id, Tab.classification.is_(None))
                .order_by(Tab.id)
            )
        )
        candidates: dict[str, list[Tab]] = defaultdict(list)
        counts = dict.fromkeys(Classification, 0)

        def settle(tab: Tab, cls: Classification) -> None:
            tab.classification = cls
            tab.decision = DEFAULT_DECISION[cls]
            counts[cls] += 1

        for tab in tabs:
            verdict = classify_tab(tab.url, tab.title or "", entries)
            if verdict.outcome is RuleOutcome.known_shop:
                assert verdict.shop_slug is not None
                tab.shop_id = shop_ids[verdict.shop_slug]
                settle(tab, Classification.known_shop)
            elif verdict.outcome is RuleOutcome.not_book:
                settle(tab, Classification.not_book)
            else:
                candidates[tab.domain].append(tab)
        session.commit()

        progress.update(
            phase="llm",
            tabs=len(tabs),
            unknown_domains=len(candidates),
            known_shop=counts[Classification.known_shop],
            not_book=counts[Classification.not_book],
        )
        report()

        verdicts: dict[str, Classification] = {}
        if candidates and client.api_key:
            groups = {
                domain: [(t.url, t.title or "") for t in domain_tabs[:MAX_SAMPLES]]
                for domain, domain_tabs in candidates.items()
            }
            verdicts = asyncio.run(_classify_domains(groups, client))
        elif candidates:
            progress["warning"] = "OPENROUTER_API_KEY not set: unknown domains left for review"

        for domain, domain_tabs in candidates.items():
            cls = verdicts.get(domain, Classification.unknown_book)
            for tab in domain_tabs:
                settle(tab, cls)
        session.commit()

    progress.update(
        phase="done",
        known_shop=counts[Classification.known_shop],
        unknown_book=counts[Classification.unknown_book],
        not_book=counts[Classification.not_book],
        llm_failed=len(candidates) - len(verdicts) if client.api_key else 0,
    )
    report()
    return progress


def attach_learned_shop(entry: registry.ShopEntry) -> int:
    """After "Learn & close": re-file that domain's `unknown_book` tabs (in
    any scan) under the new shop. Decisions are left to the caller."""
    with db_session.SessionLocal() as session:
        shop = session.scalars(select(Shop).where(Shop.slug == entry.slug)).one()
        tabs = session.scalars(
            select(Tab).where(
                Tab.classification == Classification.unknown_book, Tab.closed_at.is_(None)
            )
        )
        moved = 0
        for tab in tabs:
            if registry.match(tab.domain, [entry]) is not None:
                tab.classification = Classification.known_shop
                tab.shop_id = shop.id
                moved += 1
        session.commit()
        return moved
