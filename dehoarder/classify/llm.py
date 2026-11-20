"""Unknown-domain classifier: one cheap-model call per domain.

The classify stage gathers the tabs that `rules.py` marked
`unknown_book_candidate`, groups them by domain, and calls
`classify_domain()` once per domain with up to ten sample tabs. The answer
only labels the domain; the operator still decides in the Tabs view
("Learn & close" or "Keep").
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from dehoarder.config import settings
from dehoarder.db.models import Classification, ShopKind
from dehoarder.llm.client import LlmClient, Tier

MAX_SAMPLES = 10


class DomainVerdict(BaseModel):
    # Strict structured output needs `additionalProperties: false`.
    model_config = ConfigDict(extra="forbid")

    is_bookshop: bool
    shop_name: str
    kind: ShopKind
    confidence: float = Field(ge=0.0, le=1.0)


def format_samples(samples: list[tuple[str, str]]) -> str:
    return "\n".join(f"- {url} — {title}" for url, title in samples[:MAX_SAMPLES])


async def classify_domain(
    domain: str, samples: list[tuple[str, str]], client: LlmClient
) -> DomainVerdict:
    """Ask the cheap model whether `domain` is a bookshop, from (url, title) samples."""
    return await client.complete(
        "classify_domain",
        {"domain": domain, "samples": format_samples(samples)},
        Tier.cheap,
        DomainVerdict,
        stage="classify",
    )


def to_classification(verdict: DomainVerdict) -> Classification:
    """`unknown_book` only for a confident yes; anything else stays open as `not_book`."""
    if verdict.is_bookshop and verdict.confidence >= settings.classify_min_confidence:
        return Classification.unknown_book
    return Classification.not_book
