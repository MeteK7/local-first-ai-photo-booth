"""Select a session experience and preserve a separately rendered filmstrip."""

import sqlalchemy as sa
from alembic import op

revision = "20261118_02"
down_revision = "20261118_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("booth_sessions", sa.Column("experience", sa.String(12), server_default="single", nullable=False))
    op.create_check_constraint("session_experience", "booth_sessions", "experience IN ('single', 'filmstrip')")
    op.create_table(
        "filmstrips",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("booth_sessions.id"), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    raise RuntimeError("The photo booth schema has no automatic destructive downgrade.")
