"""Deterministic tab classification: the step between the shop registry and
the cheap LLM.

`classify_tab(url, title, entries)` returns one of:

- `known_shop` — the hostname (or a parent domain) is in the registry;
- `not_book` — not an http(s) page, or a domain on the non-book allowlist,
  or no book signal at all;
- `unknown_book_candidate` — an unknown domain with a book signal. The
  classify stage groups these by domain and asks the LLM once per domain.

Book signals, any one of which is enough:

- **URL**: a valid ISBN-10/13 (checksum verified), or a product path such
  as `/dp/`, `/book/`, `/books/`, `/product/`, `/livre/`, `/buch/`;
- **title keyword**: "купить", "книга", "isbn", "livre", "broché",
  "Buch", "Taschenbuch", "gebundene Ausgabe", …;
- **title shape**: `… by Name` (a capitalised word after "by"), or both
  separators of the classic shop title `Title — Author | Shop`.

A lone ` — ` or ` | ` is not enough: half the web titles its pages
`Page | Site`.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass
from urllib.parse import unquote, urlparse

from dehoarder.classify.registry import ShopEntry, match, normalise_host


class RuleOutcome(enum.StrEnum):
    known_shop = "known_shop"
    unknown_book_candidate = "unknown_book_candidate"
    not_book = "not_book"


@dataclass(frozen=True)
class RuleVerdict:
    outcome: RuleOutcome
    shop_slug: str | None = None
    signal: str | None = None  # which rule fired, for the review UI and debugging


# Domains that are never bookshops. Subdomains match too (mail.google.com).
NON_BOOK_DOMAINS = frozenset(
    {
        "google.com",
        "google.de",
        "google.ru",
        "yandex.ru",
        "ya.ru",
        "duckduckgo.com",
        "bing.com",
        "youtube.com",
        "youtu.be",
        "github.com",
        "gitlab.com",
        "stackoverflow.com",
        "stackexchange.com",
        "wikipedia.org",
        "reddit.com",
        "twitter.com",
        "x.com",
        "facebook.com",
        "instagram.com",
        "linkedin.com",
        "vk.com",
        "t.me",
        "telegram.org",
        "chatgpt.com",
        "openai.com",
        "claude.ai",
        "anthropic.com",
        "openrouter.ai",
        "medium.com",
        "news.ycombinator.com",
        "localhost",
        "127.0.0.1",
    }
)

_PATH_SIGNALS = re.compile(r"/(dp|gp/product|book|books|product|products|livre|livres|buch)/", re.I)

_TITLE_KEYWORDS = re.compile(
    r"\b(isbn|купить|книга|книги|livre|broché|relié|buch|taschenbuch|gebundene ausgabe)\b",
    re.I,
)

# "by" followed by a capitalised (Latin or Cyrillic) word: "SICP by Harold Abelson".
_BY_AUTHOR = re.compile(r"\bby\s+[A-ZА-ЯЁ]")

_ISBN_CANDIDATE = re.compile(r"(?<![\dX])(97[89][\d-]{10,14}|[\d-]{9,12}[\dX])(?![\dX])", re.I)


def is_valid_isbn10(isbn: str) -> bool:
    if not re.fullmatch(r"\d{9}[\dX]", isbn, re.I):
        return False
    total = sum((10 - i) * int(c) for i, c in enumerate(isbn[:9]))
    total += 10 if isbn[9] in "xX" else int(isbn[9])
    return total % 11 == 0


def is_valid_isbn13(isbn: str) -> bool:
    if not re.fullmatch(r"97[89]\d{10}", isbn):
        return False
    total = sum((1 if i % 2 == 0 else 3) * int(c) for i, c in enumerate(isbn[:12]))
    return (10 - total % 10) % 10 == int(isbn[12])


def find_isbns(text: str) -> list[str]:
    """Checksum-valid ISBN-10/13s in `text`, hyphens removed, in order."""
    found: list[str] = []
    for m in _ISBN_CANDIDATE.finditer(text):
        digits = m.group(1).replace("-", "").upper()
        if (is_valid_isbn13(digits) or is_valid_isbn10(digits)) and digits not in found:
            found.append(digits)
    return found


def _is_non_book_domain(host: str) -> bool:
    labels = host.split(".")
    return any(".".join(labels[i:]) in NON_BOOK_DOMAINS for i in range(len(labels)))


def book_signal(url: str, title: str) -> str | None:
    """Name of the first book signal in `url`/`title`, or None."""
    parsed = urlparse(url)
    path = unquote(parsed.path)
    if find_isbns(path + " " + unquote(parsed.query)):
        return "url_isbn"
    if _PATH_SIGNALS.search(path + "/"):
        return "url_path"
    if _TITLE_KEYWORDS.search(title):
        return "title_keyword"
    if _BY_AUTHOR.search(title):
        return "title_by_author"
    if " — " in title and " | " in title:
        return "title_shape"
    return None


def classify_tab(url: str, title: str, entries: list[ShopEntry]) -> RuleVerdict:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return RuleVerdict(RuleOutcome.not_book, signal="not_web")

    host = normalise_host(parsed.hostname)
    shop = match(host, entries)
    if shop is not None:
        return RuleVerdict(RuleOutcome.known_shop, shop_slug=shop.slug, signal="registry")

    if _is_non_book_domain(host):
        return RuleVerdict(RuleOutcome.not_book, signal="non_book_domain")

    signal = book_signal(url, title or "")
    if signal is not None:
        return RuleVerdict(RuleOutcome.unknown_book_candidate, signal=signal)
    return RuleVerdict(RuleOutcome.not_book, signal="no_signal")
