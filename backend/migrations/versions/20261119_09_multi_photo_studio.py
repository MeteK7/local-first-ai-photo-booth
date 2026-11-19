"""Persist Signature Strip plans, capture positions, and result layouts."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20261119_09"
down_revision = "20261119_08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("booth_sessions", sa.Column("multi_photo_plan", JSONB(none_as_null=True)))
    op.create_check_constraint("session_multi_photo_plan", "booth_sessions",
                               "multi_photo_plan IS NULL OR experience = 'filmstrip'")
    op.add_column("original_photos", sa.Column("capture_slot", sa.Integer()))
    op.create_unique_constraint("original_photo_capture_slot", "original_photos", ["session_id", "capture_slot"])
    op.create_check_constraint("original_photo_slot_range", "original_photos", "capture_slot BETWEEN 1 AND 6")
    op.add_column("filmstrips", sa.Column("layout", sa.String(12)))
    op.create_check_constraint("filmstrip_layout", "filmstrips", "layout IN ('vertical', 'horizontal', 'grid')")


def downgrade() -> None:
    raise RuntimeError("The photo booth schema has no automatic destructive downgrade.")
