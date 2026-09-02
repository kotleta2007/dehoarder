"""Schema tests: table creation, round-trips, `migrate()` idempotency."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import inspect, select

from dehoarder.db.migrate import CURRENT_VERSION, migrate
from dehoarder.db.models import (
    Base,
    Book,
    Scan,
    ScanSource,
    SchemaVersion,
    Shop,
    ShopKind,
    Tab,
)
from dehoarder.db.session import SessionLocal, make_engine


def test_migrate_creates_all_tables(tmp_path: Path) -> None:
    engine = make_engine(str(tmp_path / "test.db"))
    migrate(engine)

    tables = set(inspect(engine).get_table_names())
    expected = {t.name for t in Base.metadata.sorted_tables}
    assert expected <= tables


def test_migrate_sets_schema_version(tmp_path: Path) -> None:
    engine = make_engine(str(tmp_path / "test.db"))
    migrate(engine)

    with SessionLocal(bind=engine) as session:
        rows = session.execute(select(SchemaVersion)).scalars().all()
        assert len(rows) == 1
        assert rows[0].version == CURRENT_VERSION


def test_migrate_is_idempotent(tmp_path: Path) -> None:
    engine = make_engine(str(tmp_path / "test.db"))
    migrate(engine)
    migrate(engine)
    migrate(engine)

    tables_after_first = set(inspect(engine).get_table_names())
    with SessionLocal(bind=engine) as session:
        rows = session.execute(select(SchemaVersion)).scalars().all()
        assert len(rows) == 1
        assert rows[0].version == CURRENT_VERSION
    assert tables_after_first == set(inspect(engine).get_table_names())


def test_round_trip_book_shop_scan_tab(tmp_path: Path) -> None:
    engine = make_engine(str(tmp_path / "test.db"))
    migrate(engine)

    with SessionLocal(bind=engine) as session:
        shop = Shop(slug="amazon", name="Amazon", domains=["amazon.com"], kind=ShopKind.marketplace)
        scan = Scan(source=ScanSource.extension, profile_name="Default", tab_count=1)
        book = Book(title="Test Book", authors=["Jane Doe"], merge_key="test-book|jane doe")
        session.add_all([shop, scan, book])
        session.commit()

        tab = Tab(
            scan_id=scan.id,
            url="https://amazon.com/dp/XYZ",
            domain="amazon.com",
            shop_id=shop.id,
            book_id=book.id,
        )
        session.add(tab)
        session.commit()
        tab_id = tab.id

    with SessionLocal(bind=engine) as session:
        loaded = session.get(Tab, tab_id)
        assert loaded is not None
        assert loaded.url == "https://amazon.com/dp/XYZ"
        assert loaded.decision.value == "pending"
        assert loaded.process_status.value == "pending"

        loaded_shop = session.get(Shop, loaded.shop_id)
        assert loaded_shop is not None
        assert loaded_shop.domains == ["amazon.com"]

        loaded_book = session.get(Book, loaded.book_id)
        assert loaded_book is not None
        assert loaded_book.authors == ["Jane Doe"]
        assert loaded_book.selection_count == 1
        assert loaded_book.status.value == "unread"
