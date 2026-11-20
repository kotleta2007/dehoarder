"""Read-only parser for Chromium/Thorium SNSS `Session_*` files.

Reconstructs which windows/tabs are currently open and each tab's selected
navigation entry (url, title), by replaying the append-only command log
Chromium writes to `Sessions/Session_<timestamp>`.

Byte layout verified 2026-09 against Chromium source
(components/sessions/core/session_command.cc,
components/sessions/core/session_service_commands.cc):

    file    := b"SNSS" version:uint32_le command*
    command := size:uint16_le id:uint8 contents(size-1 bytes)

`SessionCommand::GetContents` copies the raw, natively-aligned C++ struct
bytes for the fixed-size commands (SetTabWindow, SetSelectedNavigationIndex,
TabClosed, WindowClosed); UpdateTabNavigation's contents are a base::Pickle
(its own 4-byte length header, then 4-byte-aligned fields). Only the five
command ids needed to know which tabs are open and what their current
URL/title is are decoded here; everything else is skipped.

Never opens the file for writing — SNSS files are Chromium's own, and a
half-written file would corrupt Thorium's session.
"""

from __future__ import annotations

import struct
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

MAGIC = b"SNSS"
SUPPORTED_VERSIONS = (1, 3)

CMD_SET_TAB_WINDOW = 0
CMD_UPDATE_TAB_NAVIGATION = 6
CMD_SET_SELECTED_NAVIGATION_INDEX = 7
CMD_TAB_CLOSED = 16
CMD_WINDOW_CLOSED = 17


class SnssError(Exception):
    """Raised when a file doesn't look like a Chromium SNSS session file."""


@dataclass
class OpenTab:
    tab_id: int
    window_id: int | None = None
    navigations: dict[int, tuple[str, str]] = field(default_factory=dict)
    selected_index: int = 0

    @property
    def _current_entry(self) -> tuple[str, str] | None:
        if self.selected_index in self.navigations:
            return self.navigations[self.selected_index]
        if self.navigations:
            return self.navigations[max(self.navigations)]
        return None

    @property
    def url(self) -> str | None:
        entry = self._current_entry
        return entry[0] if entry else None

    @property
    def title(self) -> str | None:
        entry = self._current_entry
        return entry[1] if entry else None


def _read_file_with_retry(path: Path) -> bytes:
    """Reads the whole file in binary mode, retrying once on a short read.
    Only ever opens with mode "rb"."""
    expected_size = path.stat().st_size
    with open(path, "rb") as f:
        data = f.read()
    if len(data) < expected_size:
        with open(path, "rb") as f:
            data = f.read()
    return data


def _iter_commands(data: bytes) -> Iterator[tuple[int, bytes]]:
    offset = 8  # past the 4-byte magic + 4-byte version header
    n = len(data)
    while offset + 2 <= n:
        (size,) = struct.unpack_from("<H", data, offset)
        offset += 2
        if size < 1 or offset + size > n:
            return  # truncated trailing record (file written mid-command); stop
        command_id = data[offset]
        contents = data[offset + 1 : offset + size]
        offset += size
        yield command_id, contents


def _read_pickle_string(data: bytes, pos: int) -> tuple[str, int]:
    (length,) = struct.unpack_from("<I", data, pos)
    pos += 4
    raw = data[pos : pos + length]
    pos += length + (4 - length % 4) % 4
    return raw.decode("utf-8", errors="replace"), pos


def _read_pickle_string16(data: bytes, pos: int) -> tuple[str, int]:
    (chars,) = struct.unpack_from("<I", data, pos)
    length = chars * 2
    pos += 4
    raw = data[pos : pos + length]
    pos += length + (4 - length % 4) % 4
    return raw.decode("utf-16-le", errors="replace"), pos


def _parse_update_tab_navigation(contents: bytes) -> tuple[int, int, str, str] | None:
    """Returns (tab_id, nav_index, url, title), or None if malformed/short."""
    if len(contents) < 4:
        return None
    (pickle_length,) = struct.unpack_from("<I", contents, 0)
    if pickle_length + 4 != len(contents):
        return None

    pos = 4
    if pos + 8 > len(contents):
        return None
    tab_id, nav_index = struct.unpack_from("<ii", contents, pos)
    pos += 8

    try:
        url, pos = _read_pickle_string(contents, pos)
        title, pos = _read_pickle_string16(contents, pos)
    except struct.error:
        return None
    return tab_id, nav_index, url, title


def parse_session_file(path: Path) -> dict[int, OpenTab]:
    """Replays a `Session_*` file's command log and returns the tabs that
    are still open (not individually closed, and not in a closed window),
    keyed by tab id.
    """
    data = _read_file_with_retry(path)
    if data[:4] != MAGIC:
        raise SnssError(f"{path}: not a Chromium SNSS file (bad magic)")
    (version,) = struct.unpack_from("<I", data, 4)
    if version not in SUPPORTED_VERSIONS:
        raise SnssError(f"{path}: unsupported SNSS version {version}")

    tabs: dict[int, OpenTab] = {}
    closed_window_ids: set[int] = set()

    def tab(tab_id: int) -> OpenTab:
        if tab_id not in tabs:
            tabs[tab_id] = OpenTab(tab_id=tab_id)
        return tabs[tab_id]

    for command_id, contents in _iter_commands(data):
        if command_id == CMD_SET_TAB_WINDOW and len(contents) >= 8:
            window_id, tab_id = struct.unpack_from("<ii", contents, 0)
            tab(tab_id).window_id = window_id
        elif command_id == CMD_UPDATE_TAB_NAVIGATION:
            parsed = _parse_update_tab_navigation(contents)
            if parsed is not None:
                tab_id, nav_index, url, title = parsed
                tab(tab_id).navigations[nav_index] = (url, title)
        elif command_id == CMD_SET_SELECTED_NAVIGATION_INDEX and len(contents) >= 8:
            tab_id, index = struct.unpack_from("<ii", contents, 0)
            tab(tab_id).selected_index = index
        elif command_id == CMD_TAB_CLOSED and len(contents) >= 4:
            (tab_id,) = struct.unpack_from("<i", contents, 0)
            tabs.pop(tab_id, None)
        elif command_id == CMD_WINDOW_CLOSED and len(contents) >= 4:
            (window_id,) = struct.unpack_from("<i", contents, 0)
            closed_window_ids.add(window_id)

    return {
        tab_id: t
        for tab_id, t in tabs.items()
        if t.window_id is not None and t.window_id not in closed_window_ids and t.navigations
    }


def find_latest_session_file(profile_dir: Path) -> Path | None:
    sessions_dir = profile_dir / "Sessions"
    if not sessions_dir.is_dir():
        return None
    candidates = list(sessions_dir.glob("Session_*"))
    if not candidates:
        return None
    return max(candidates, key=_session_timestamp)


def _session_timestamp(path: Path) -> int:
    try:
        return int(path.name.split("_", 1)[1])
    except (IndexError, ValueError):
        return -1


def read_open_tabs(profile_dir: Path) -> list[dict]:
    """Finds the newest `Session_*` file under `profile_dir/Sessions` and
    returns its open tabs, shaped like the extension's `list_tabs`
    response so they can feed the same scan-persisting code path.
    """
    session_file = find_latest_session_file(profile_dir)
    if session_file is None:
        return []

    tabs = parse_session_file(session_file)
    return [
        {
            "windowId": t.window_id,
            "id": t.tab_id,
            "url": t.url,
            "title": t.title,
            "discarded": False,
            "lastAccessed": None,
        }
        for t in sorted(tabs.values(), key=lambda t: (t.window_id, t.tab_id))
        if t.url is not None
    ]
