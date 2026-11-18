"""Store original photo metadata for booth sessions."""

import sqlalchemy as sa
from alembic import op

revision = "20261118_01"
down_revision = "20261117_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "original_photos",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("booth_sessions.id"), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.UniqueConstraint("session_id", "request_id", name="original_photo_capture_request"),
    )
    op.create_index("ix_original_photos_session_captured", "original_photos", ["session_id", "captured_at"])


def downgrade() -> None:
    raise RuntimeError("The photo booth schema has no automatic destructive downgrade.")
