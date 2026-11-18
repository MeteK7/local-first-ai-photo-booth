from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.media import asset_path, prepare_storage
from app.sessions import BoothSession, State


def test_terminal_session_cannot_be_changed():
    now = datetime.now(UTC)
    session = BoothSession(state=State.ACTIVE)
    session.finish(State.COMPLETED, now)
    assert session.state == State.COMPLETED
    assert session.ended_at == now
    with pytest.raises(ValueError):
        session.finish(State.CANCELED, now)
    assert session.state == State.COMPLETED


def test_asset_areas_are_created_and_traversal_is_rejected(tmp_path):
    prepare_storage(tmp_path)
    asset = uuid4()
    assert asset_path(tmp_path, "originals", asset) == tmp_path / "originals" / f"{asset}.jpg"
    with pytest.raises(ValueError):
        asset_path(tmp_path, "../another-directory", asset)
