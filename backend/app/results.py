"""Resolve deliverable photo results across capture and effects."""

from typing import Literal
from uuid import UUID

from app.ai_photos import require_completed_effect
from app.photos import ResultKind, require_result

PhotoResultKind = ResultKind | Literal["effect"]
RESULT_AREAS: dict[PhotoResultKind, str] = {
    "original": "originals",
    "filmstrip": "processed",
    "effect": "ai-generated",
}


def require_owned_result(db, session_id: UUID, asset_id: UUID, kind: PhotoResultKind) -> UUID:
    if kind == "effect":
        return require_completed_effect(db, session_id, asset_id)
    return require_result(db, session_id, asset_id, kind)
