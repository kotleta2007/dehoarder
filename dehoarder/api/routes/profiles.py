"""GET /api/v1/profiles: Thorium profiles available for the SNSS fallback
scan, so the Tabs view can offer a profile dropdown when no extension is
detected.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from dehoarder.ingest.profiles import current_profile, list_profiles

router = APIRouter(prefix="/api/v1", tags=["profiles"])


class ProfileOut(BaseModel):
    dir_name: str
    display_name: str
    current: bool


@router.get("/profiles", response_model=list[ProfileOut])
def get_profiles() -> list[ProfileOut]:
    current_dir = None
    current = current_profile()
    if current is not None:
        current_dir = current.dir_name

    return [
        ProfileOut(
            dir_name=p.dir_name, display_name=p.display_name, current=p.dir_name == current_dir
        )
        for p in list_profiles()
    ]
