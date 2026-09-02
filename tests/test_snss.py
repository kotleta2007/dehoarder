"""SNSS parser tests against a synthetic fixture built in-test (byte layout
verified against Chromium source — see docstring in dehoarder/ingest/snss.py)
plus the read-only/open-mode guarantees.
"""

from __future__ import annotations

import builtins
import struct
from pathlib import Path
from unittest import mock

import pytest

from dehoarder.ingest import snss


def _pack_command(command_id: int, contents: bytes) -> bytes:
    size = 1 + len(contents)
    return struct.pack("<H", size) + bytes([command_id]) + contents


def _set_tab_window(window_id: int, tab_id: int) -> bytes:
    return _pack_command(snss.CMD_SET_TAB_WINDOW, struct.pack("<ii", window_id, tab_id))


def _set_selected_navigation_index(tab_id: int, index: int) -> bytes:
    return _pack_command(
        snss.CMD_SET_SELECTED_NAVIGATION_INDEX, struct.pack("<ii", tab_id, index)
    )


def _tab_closed(tab_id: int) -> bytes:
    # ClosedPayload{ int32 id; int64 close_time; } — natively aligned, so
    # there are 4 padding bytes before the int64.
    return _pack_command(snss.CMD_TAB_CLOSED, struct.pack("<i4xq", tab_id, 0))


def _window_closed(window_id: int) -> bytes:
    return _pack_command(snss.CMD_WINDOW_CLOSED, struct.pack("<i4xq", window_id, 0))


def _pickle_string(s: str) -> bytes:
    raw = s.encode("utf-8")
    return struct.pack("<I", len(raw)) + raw + b"\x00" * ((4 - len(raw) % 4) % 4)


def _pickle_string16(s: str) -> bytes:
    raw = s.encode("utf-16-le")
    return struct.pack("<I", len(s)) + raw + b"\x00" * ((4 - len(raw) % 4) % 4)


def _update_tab_navigation(tab_id: int, index: int, url: str, title: str) -> bytes:
    body = struct.pack("<ii", tab_id, index) + _pickle_string(url) + _pickle_string16(title)
    pickle = struct.pack("<I", len(body)) + body
    return _pack_command(snss.CMD_UPDATE_TAB_NAVIGATION, pickle)


def _session_header(version: int = 1) -> bytes:
    return snss.MAGIC + struct.pack("<I", version)


def _build_synthetic_session() -> bytes:
    """Two windows: window 1 has two live tabs (10, 11); window 2 has tab 12
    which gets closed directly, and window 3 (with tab 13) gets closed as a
    whole. Only tabs 10 and 11 should come back as open.
    """
    commands = [
        _set_tab_window(1, 10),
        _update_tab_navigation(10, 0, "https://example.com/a", "A"),
        _set_selected_navigation_index(10, 0),
        _set_tab_window(1, 11),
        _update_tab_navigation(11, 0, "https://example.com/b", "B"),
        _update_tab_navigation(11, 1, "https://example.com/b2", "B2"),
        _set_selected_navigation_index(11, 1),
        _set_tab_window(2, 12),
        _update_tab_navigation(12, 0, "https://example.com/closed-tab", "Closed tab"),
        _tab_closed(12),
        _set_tab_window(3, 13),
        _update_tab_navigation(13, 0, "https://example.com/closed-window", "Closed window"),
        _window_closed(3),
    ]
    return _session_header() + b"".join(commands)


def test_parse_session_file_reconstructs_open_tabs(tmp_path: Path) -> None:
    path = tmp_path / "Session_1000"
    path.write_bytes(_build_synthetic_session())

    tabs = snss.parse_session_file(path)

    assert set(tabs) == {10, 11}
    assert tabs[10].window_id == 1
    assert tabs[10].url == "https://example.com/a"
    assert tabs[10].title == "A"

    # Selected index picks the second navigation entry for tab 11.
    assert tabs[11].url == "https://example.com/b2"
    assert tabs[11].title == "B2"


def test_directly_closed_tab_is_excluded(tmp_path: Path) -> None:
    path = tmp_path / "Session_1000"
    path.write_bytes(_build_synthetic_session())
    assert 12 not in snss.parse_session_file(path)


def test_tab_in_a_closed_window_is_excluded(tmp_path: Path) -> None:
    path = tmp_path / "Session_1000"
    path.write_bytes(_build_synthetic_session())
    assert 13 not in snss.parse_session_file(path)


def test_bad_magic_raises(tmp_path: Path) -> None:
    path = tmp_path / "Session_1000"
    path.write_bytes(b"NOPE" + struct.pack("<I", 1))
    with pytest.raises(snss.SnssError, match="bad magic"):
        snss.parse_session_file(path)


def test_unsupported_version_raises(tmp_path: Path) -> None:
    path = tmp_path / "Session_1000"
    path.write_bytes(snss.MAGIC + struct.pack("<I", 99))
    with pytest.raises(snss.SnssError, match="unsupported"):
        snss.parse_session_file(path)


def test_truncated_trailing_record_does_not_crash(tmp_path: Path) -> None:
    path = tmp_path / "Session_1000"
    data = _build_synthetic_session()
    # Simulate Thorium mid-write: a record that claims more bytes than exist.
    truncated = data + struct.pack("<H", 500) + b"\x06only-a-few-bytes"
    path.write_bytes(truncated)

    tabs = snss.parse_session_file(path)
    assert set(tabs) == {10, 11}


def test_find_latest_session_file_picks_the_newest_by_timestamp(tmp_path: Path) -> None:
    sessions_dir = tmp_path / "Sessions"
    sessions_dir.mkdir()
    (sessions_dir / "Session_100").write_bytes(_session_header())
    (sessions_dir / "Session_9999999999999999").write_bytes(_session_header())
    (sessions_dir / "Session_200").write_bytes(_session_header())

    latest = snss.find_latest_session_file(tmp_path)
    assert latest is not None
    assert latest.name == "Session_9999999999999999"


def test_find_latest_session_file_missing_dir_returns_none(tmp_path: Path) -> None:
    assert snss.find_latest_session_file(tmp_path / "nonexistent") is None


def test_read_open_tabs_end_to_end(tmp_path: Path) -> None:
    sessions_dir = tmp_path / "Sessions"
    sessions_dir.mkdir()
    (sessions_dir / "Session_1000").write_bytes(_build_synthetic_session())

    tabs = snss.read_open_tabs(tmp_path)

    assert [t["id"] for t in tabs] == [10, 11]
    assert tabs[0] == {
        "windowId": 1,
        "id": 10,
        "url": "https://example.com/a",
        "title": "A",
        "discarded": False,
        "lastAccessed": None,
    }


def test_read_open_tabs_with_no_session_files_returns_empty(tmp_path: Path) -> None:
    assert snss.read_open_tabs(tmp_path) == []


def test_read_file_with_retry_retries_once_on_a_short_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "Session_1000"
    path.write_bytes(b"0123456789")

    real_open = builtins.open
    call_modes: list[str] = []

    class ShortReadFile:
        def __init__(self, real_file: object, truncate: bool) -> None:
            self._real_file = real_file
            self._truncate = truncate

        def read(self) -> bytes:
            data = self._real_file.read()  # type: ignore[attr-defined]
            return data[:5] if self._truncate else data

        def __enter__(self) -> ShortReadFile:
            return self

        def __exit__(self, *exc: object) -> None:
            self._real_file.close()  # type: ignore[attr-defined]

    def fake_open(file: object, mode: str = "r", *args: object, **kwargs: object) -> object:
        call_modes.append(mode)
        return ShortReadFile(real_open(file, mode, *args, **kwargs), truncate=len(call_modes) == 1)

    monkeypatch.setattr(snss, "open", fake_open, raising=False)

    data = snss._read_file_with_retry(path)

    assert data == b"0123456789"
    assert call_modes == ["rb", "rb"]


def test_never_opens_for_writing(tmp_path: Path) -> None:
    session_file = tmp_path / "Session_1000"
    session_file.write_bytes(_build_synthetic_session())

    with mock.patch("builtins.open", wraps=builtins.open) as mocked_open:
        snss.parse_session_file(session_file)

    assert mocked_open.call_count >= 1
    for call in mocked_open.call_args_list:
        args, kwargs = call
        mode = kwargs.get("mode", args[1] if len(args) > 1 else "r")
        assert mode == "rb"
