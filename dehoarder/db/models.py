"""SQLAlchemy 2 models for every table in CLAUDE.md's data model.

One `Base` per process; `migrate.py` turns this into a live schema. Enum
columns use `native_enum=False` since SQLite has no native enum type — they
store as plain TEXT with Python-side validation.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import JSON, Enum, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ScanSource(enum.StrEnum):
    extension = "extension"
    snss = "snss"


class Classification(enum.StrEnum):
    known_shop = "known_shop"
    unknown_book = "unknown_book"
    not_book = "not_book"


class Decision(enum.StrEnum):
    close = "close"
    keep = "keep"
    pending = "pending"


class ProcessStatus(enum.StrEnum):
    pending = "pending"
    fetched = "fetched"
    extracted = "extracted"
    failed = "failed"
    skipped = "skipped"


class ShopKind(enum.StrEnum):
    bookshop = "bookshop"
    publisher = "publisher"
    marketplace = "marketplace"


class BookKind(enum.StrEnum):
    fiction = "fiction"
    nonfiction = "nonfiction"
    technical = "technical"


class BookStatus(enum.StrEnum):
    unread = "unread"
    reading = "reading"
    read = "read"
    abandoned = "abandoned"


class EdgeType(enum.StrEnum):
    author = "author"
    series = "series"
    topic = "topic"
    similar = "similar"
    publisher = "publisher"
    shop = "shop"


class JobKind(enum.StrEnum):
    chain = "chain"
    scan = "scan"
    close = "close"
    process = "process"
    tag = "tag"
    link = "link"
    plan = "plan"


class JobStatus(enum.StrEnum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"


class SchemaVersion(Base):
    __tablename__ = "schema_version"

    version: Mapped[int] = mapped_column(primary_key=True)


class Scan(Base):
    __tablename__ = "scan"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    source: Mapped[ScanSource] = mapped_column(Enum(ScanSource, native_enum=False))
    profile_name: Mapped[str | None] = mapped_column(default=None)
    tab_count: Mapped[int] = mapped_column(default=0)


class Shop(Base):
    __tablename__ = "shop"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str]
    domains: Mapped[list[str]] = mapped_column(JSON, default=list)
    kind: Mapped[ShopKind] = mapped_column(Enum(ShopKind, native_enum=False))
    currency: Mapped[str | None] = mapped_column(default=None)
    min_interval_s: Mapped[float] = mapped_column(default=2.0)
    extractor: Mapped[str | None] = mapped_column(default=None)
    learned: Mapped[bool] = mapped_column(default=False)
    blocked_until: Mapped[datetime | None] = mapped_column(default=None)


class Book(Base):
    __tablename__ = "book"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    subtitle: Mapped[str | None] = mapped_column(default=None)
    authors: Mapped[list[str]] = mapped_column(JSON, default=list)
    isbn13: Mapped[str | None] = mapped_column(default=None)
    isbn10: Mapped[str | None] = mapped_column(default=None)
    publisher: Mapped[str | None] = mapped_column(default=None)
    year: Mapped[int | None] = mapped_column(default=None)
    language: Mapped[str | None] = mapped_column(default=None)
    pages: Mapped[int | None] = mapped_column(default=None)
    series: Mapped[str | None] = mapped_column(default=None)
    series_index: Mapped[float | None] = mapped_column(default=None)
    description: Mapped[str | None] = mapped_column(default=None)
    cover_url: Mapped[str | None] = mapped_column(default=None)
    merge_key: Mapped[str] = mapped_column(unique=True)
    selection_count: Mapped[int] = mapped_column(default=1)
    kind: Mapped[BookKind | None] = mapped_column(Enum(BookKind, native_enum=False), default=None)
    topics: Mapped[list[str]] = mapped_column(JSON, default=list)
    base_difficulty: Mapped[float | None] = mapped_column(default=None)
    difficulty: Mapped[float | None] = mapped_column(default=None)
    difficulty_reason: Mapped[str | None] = mapped_column(default=None)
    est_hours: Mapped[float | None] = mapped_column(default=None)
    interest: Mapped[int] = mapped_column(default=3)
    embedding: Mapped[list[float] | None] = mapped_column(JSON, default=None)
    needs_review: Mapped[bool] = mapped_column(default=False)
    status: Mapped[BookStatus] = mapped_column(
        Enum(BookStatus, native_enum=False), default=BookStatus.unread
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class BookPropertyOverride(Base):
    __tablename__ = "book_property_override"
    __table_args__ = (UniqueConstraint("book_id", "field"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("book.id"))
    field: Mapped[str]
    value: Mapped[object] = mapped_column(JSON)
    set_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Tab(Base):
    __tablename__ = "tab"

    id: Mapped[int] = mapped_column(primary_key=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("scan.id"))
    browser_tab_id: Mapped[int | None] = mapped_column(default=None)
    window_id: Mapped[int | None] = mapped_column(default=None)
    url: Mapped[str]
    title: Mapped[str | None] = mapped_column(default=None)
    discarded: Mapped[bool] = mapped_column(default=False)
    last_accessed: Mapped[datetime | None] = mapped_column(default=None)
    domain: Mapped[str]
    classification: Mapped[Classification | None] = mapped_column(
        Enum(Classification, native_enum=False), default=None
    )
    shop_id: Mapped[int | None] = mapped_column(ForeignKey("shop.id"), default=None)
    decision: Mapped[Decision] = mapped_column(
        Enum(Decision, native_enum=False), default=Decision.pending
    )
    archived_at: Mapped[datetime | None] = mapped_column(default=None)
    closed_at: Mapped[datetime | None] = mapped_column(default=None)
    close_error: Mapped[str | None] = mapped_column(default=None)
    book_id: Mapped[int | None] = mapped_column(ForeignKey("book.id"), default=None)
    process_status: Mapped[ProcessStatus] = mapped_column(
        Enum(ProcessStatus, native_enum=False), default=ProcessStatus.pending
    )
    process_error: Mapped[str | None] = mapped_column(default=None)


class Source(Base):
    __tablename__ = "source"

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("book.id"))
    tab_id: Mapped[int | None] = mapped_column(ForeignKey("tab.id"), default=None)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shop.id"))
    url: Mapped[str]
    price: Mapped[float | None] = mapped_column(default=None)
    currency: Mapped[str | None] = mapped_column(default=None)
    availability: Mapped[str | None] = mapped_column(default=None)
    format: Mapped[str | None] = mapped_column(default=None)
    fetched_at: Mapped[datetime | None] = mapped_column(default=None)


class Edge(Base):
    __tablename__ = "edge"

    id: Mapped[int] = mapped_column(primary_key=True)
    src_book_id: Mapped[int] = mapped_column(ForeignKey("book.id"))
    dst_book_id: Mapped[int] = mapped_column(ForeignKey("book.id"))
    type: Mapped[EdgeType] = mapped_column(Enum(EdgeType, native_enum=False))
    weight: Mapped[float]
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    cross_lane: Mapped[bool] = mapped_column(default=False)


class ReadingPlan(Base):
    __tablename__ = "reading_plan"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    target: Mapped[float]
    tol: Mapped[float]
    horizon: Mapped[int]
    seeds: Mapped[list[int]] = mapped_column(JSON, default=list)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)


class PlanItem(Base):
    __tablename__ = "plan_item"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("reading_plan.id"))
    lane: Mapped[str]
    position: Mapped[int]
    book_id: Mapped[int] = mapped_column(ForeignKey("book.id"))
    reason: Mapped[str]


class Job(Base):
    __tablename__ = "job"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[JobKind] = mapped_column(Enum(JobKind, native_enum=False))
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, native_enum=False), default=JobStatus.pending
    )
    stage: Mapped[str | None] = mapped_column(default=None)
    progress: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(default=None)
    started_at: Mapped[datetime | None] = mapped_column(default=None)
    finished_at: Mapped[datetime | None] = mapped_column(default=None)


class LlmCall(Base):
    __tablename__ = "llm_call"

    id: Mapped[int] = mapped_column(primary_key=True)
    stage: Mapped[str]
    model: Mapped[str]
    prompt_hash: Mapped[str] = mapped_column(index=True)
    input_tokens: Mapped[int]
    output_tokens: Mapped[int]
    cost_usd: Mapped[float]
    # Raw completion text; a later call with the same prompt_hash reuses it.
    # NULL for embedding calls, which are logged for spend only.
    response: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Bridge(Base):
    __tablename__ = "bridge"

    extension_id: Mapped[str] = mapped_column(primary_key=True)
    version: Mapped[str]
    last_seen: Mapped[datetime] = mapped_column(server_default=func.now())
