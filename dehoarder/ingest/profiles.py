"""Thorium profile detection via `Local State`, for the SNSS read-only
fallback (Step 1.4). Profiles are looked up by their human-readable name —
what an operator recognizes — never by the profile directory.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from dehoarder.config import settings


@dataclass(frozen=True)
class Profile:
    dir_name: str
    display_name: str


def _read_local_state(thorium_dir: Path | None = None) -> dict:
    path = (thorium_dir or settings.thorium_dir) / "Local State"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def list_profiles(thorium_dir: Path | None = None) -> list[Profile]:
    info_cache = _read_local_state(thorium_dir).get("profile", {}).get("info_cache", {})
    return [
        Profile(dir_name=dir_name, display_name=info.get("name", dir_name))
        for dir_name, info in info_cache.items()
    ]


def current_profile(thorium_dir: Path | None = None) -> Profile | None:
    profile_block = _read_local_state(thorium_dir).get("profile", {})
    last_used = profile_block.get("last_used")
    if last_used is None:
        return None

    info = profile_block.get("info_cache", {}).get(last_used)
    display_name = info.get("name", last_used) if info else last_used
    return Profile(dir_name=last_used, display_name=display_name)


def find_profile_by_name(name: str, thorium_dir: Path | None = None) -> Profile | None:
    for profile in list_profiles(thorium_dir):
        if profile.display_name == name:
            return profile
    return None
