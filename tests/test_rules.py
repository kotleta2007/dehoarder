"""Deterministic URL/title rules, table-driven."""

from __future__ import annotations

import pytest

from dehoarder.classify import registry
from dehoarder.classify.rules import (
    RuleOutcome,
    classify_tab,
    find_isbns,
    is_valid_isbn10,
    is_valid_isbn13,
)
from dehoarder.config import DATA_DIR

ENTRIES = registry.load(DATA_DIR / "shops.yaml")

K = RuleOutcome.known_shop
U = RuleOutcome.unknown_book_candidate
N = RuleOutcome.not_book

CASES: list[tuple[str, str, RuleOutcome, str]] = [
    # --- known shops (registry wins, whatever the page) ---
    ("https://www.amazon.de/dp/3446264628", "Der Process: Roman", K, "registry"),
    ("https://www.amazon.com/gp/cart/view.html", "Amazon.com Shopping Cart", K, "registry"),
    ("https://www.chitai-gorod.ru/product/master-i-margarita-2836593", "Мастер и Маргарита", K,
     "registry"),
    ("https://biblio.mccme.ru/node/5432", "Задачи по геометрии", K, "registry"),
    ("https://www.manning.com/books/grokking-algorithms", "Grokking Algorithms", K, "registry"),
    ("https://www.taschen.com/en/books/art/01234/", "Hokusai", K, "registry"),
    # --- not web pages ---
    ("chrome://settings/", "Settings", N, "not_web"),
    ("file:///home/mark/book.pdf", "book.pdf", N, "not_web"),
    ("about:blank", "", N, "not_web"),
    # --- non-book allowlist, even with book-ish titles ---
    ("https://www.google.com/search?q=buy+book", "buy book — Google Search", N, "non_book_domain"),
    ("https://mail.google.com/mail/u/0/", "Inbox | Gmail", N, "non_book_domain"),
    ("https://github.com/books/repo", "books/repo", N, "non_book_domain"),
    ("https://en.wikipedia.org/wiki/The_Master_and_Margarita", "The Master and Margarita by "
     "Mikhail Bulgakov - Wikipedia", N, "non_book_domain"),
    ("https://www.youtube.com/watch?v=abc", "Book review | Channel", N, "non_book_domain"),
    ("https://ya.ru/search/?text=книга", "книга — Яндекс", N, "non_book_domain"),
    # --- URL signals ---
    ("https://www.labirint.ru/books/912345/", "Лабиринт", U, "url_path"),
    ("https://shop.example.com/product/123", "Something", U, "url_path"),
    ("https://www.decitre.fr/livres/l-etranger-9782070360024.html", "L'Étranger", U, "url_isbn"),
    ("https://www.fnac.com/a123/livre/x", "Fnac", U, "url_path"),
    ("https://www.thalia.de/shop/home/artikeldetails/A1/buch/x", "Thalia", U, "url_path"),
    ("https://www.blackwells.co.uk/bookshop/product/9780262510875", "SICP", U, "url_isbn"),
    ("https://example.org/item?isbn=978-0-262-51087-5", "Item", U, "url_isbn"),
    ("https://example.org/x/0262510871", "Item", U, "url_isbn"),
    # --- title keywords: RU / FR / DE / EN ---
    ("https://www.moscowbooks.ru/item/123", "Война и мир — купить в интернет-магазине", U,
     "title_keyword"),
    ("https://www.ozon.ru/x/12345/", "Книга Мастер и Маргарита", U, "title_keyword"),
    ("https://www.gibert.com/x-123", "L'Étranger - Albert Camus - Livre", U, "title_keyword"),
    ("https://www.gibert.com/y-456", "Madame Bovary (broché)", U, "title_keyword"),
    ("https://www.hugendubel.de/de/x", "Der Zauberberg - Thomas Mann - Taschenbuch", U,
     "title_keyword"),
    ("https://www.buecher.de/x", "Faust: Gebundene Ausgabe", U, "title_keyword"),
    ("https://www.osiander.de/x", "Die Verwandlung | Buch", U, "title_keyword"),
    ("https://example.com/x", "ISBN 9780262510875 details", U, "title_keyword"),
    # --- title shapes ---
    ("https://www.bookdepository.com/x", "Structure and Interpretation by Harold Abelson", U,
     "title_by_author"),
    ("https://www.indiebound.org/x", "Dune — Frank Herbert | IndieBound", U, "title_shape"),
    # --- unknown, no signal ---
    ("https://news.example.com/article/1", "Election results | News", N, "no_signal"),
    ("https://blog.example.com/post", "My trip — Blog", N, "no_signal"),
    ("https://example.com/", "Stand by me", N, "no_signal"),
    ("https://example.com/", "", N, "no_signal"),
    ("https://example.com/x/1234567890", "Order 1234567890", N, "no_signal"),
]


@pytest.mark.parametrize(("url", "title", "outcome", "signal"), CASES)
def test_classify_tab(url: str, title: str, outcome: RuleOutcome, signal: str) -> None:
    verdict = classify_tab(url, title, ENTRIES)
    assert (verdict.outcome, verdict.signal) == (outcome, signal)


def test_known_shop_carries_slug() -> None:
    verdict = classify_tab("https://smile.amazon.co.uk/dp/x", "x", ENTRIES)
    assert verdict.shop_slug == "amazon"


@pytest.mark.parametrize(
    ("isbn", "valid"),
    [("0262510871", True), ("080442957X", True), ("0262510872", False), ("12345", False)],
)
def test_isbn10(isbn: str, valid: bool) -> None:
    assert is_valid_isbn10(isbn) is valid


@pytest.mark.parametrize(
    ("isbn", "valid"),
    [("9780262510875", True), ("9782070360024", True), ("9780262510876", False),
     ("1234567890123", False)],
)
def test_isbn13(isbn: str, valid: bool) -> None:
    assert is_valid_isbn13(isbn) is valid


def test_find_isbns_strips_hyphens_and_dedups() -> None:
    text = "978-0-262-51087-5 and 9780262510875 and 0262510871 and 1111111111111"
    assert find_isbns(text) == ["9780262510875", "0262510871"]
