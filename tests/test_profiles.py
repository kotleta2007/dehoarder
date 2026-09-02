"""Thorium profile detection against a saved `Local State` fixture with
three named profiles.
"""

from __future__ import annotations

from pathlib import Path

from dehoarder.ingest.profiles import current_profile, find_profile_by_name, list_profiles

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "thorium_profiles"


def test_list_profiles_returns_display_names() -> None:
    names = {p.display_name for p in list_profiles(FIXTURE_DIR)}
    assert names == {"Mark", "Work", "Books"}


def test_current_profile_is_last_used() -> None:
    profile = current_profile(FIXTURE_DIR)
    assert profile is not None
    assert profile.dir_name == "Profile 1"
    assert profile.display_name == "Work"


def test_find_profile_by_name() -> None:
    profile = find_profile_by_name("Books", FIXTURE_DIR)
    assert profile is not None
    assert profile.dir_name == "Profile 2"


def test_find_profile_by_name_missing_returns_none() -> None:
    assert find_profile_by_name("Nonexistent", FIXTURE_DIR) is None


def test_list_profiles_missing_local_state_returns_empty() -> None:
    assert list_profiles(Path("/nonexistent/thorium/dir")) == []


def test_current_profile_missing_local_state_returns_none() -> None:
    assert current_profile(Path("/nonexistent/thorium/dir")) is None
