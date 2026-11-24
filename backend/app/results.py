"""Resolve deliverable photo results across capture and effects."""

from typing import Literal
from uuid import UUID

from app.ai_photos import require_completed_effect
from app.creative import require_creative_result
from app.photos import ResultKind, require_result

PhotoResultKind = ResultKind | Literal["effect", "creative"]
RESULT_AREAS: dict[PhotoResultKind, str] = {
    "original": "originals",
    "filmstrip": "processed",
    "effect": "ai-generated",
    "creative": "processed",
}


def require_owned_result(db, session_id: UUID, asset_id: UUID, kind: PhotoResultKind) -> UUID:
    if kind == "effect":
        return require_completed_effect(db, session_id, asset_id)
    if kind == "creative":
        return require_creative_result(db, session_id, asset_id)
    return require_result(db, session_id, asset_id, kind)
