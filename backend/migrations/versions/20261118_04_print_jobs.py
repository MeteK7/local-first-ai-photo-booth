"""Persist one-copy customer print jobs and their spooler state."""

import sqlalchemy as sa
from alembic import op

revision = "20261118_04"
down_revision = "20261118_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "print_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("original_id", sa.Uuid(), sa.ForeignKey("original_photos.id"), unique=True),
        sa.Column("filmstrip_id", sa.Uuid(), sa.ForeignKey("filmstrips.id"), unique=True),
        sa.Column("printer", sa.String(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("detail", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("(original_id IS NULL) <> (filmstrip_id IS NULL)", name="print_job_one_asset"),
        sa.CheckConstraint("state IN ('queued', 'submitting', 'submitted', 'sent', 'failed', 'unknown')",
                           name="print_job_state"),
    )
    op.create_index("ix_print_jobs_state_updated_at", "print_jobs", ["state", "updated_at"])


def downgrade() -> None:
    raise RuntimeError("The photo booth schema has no automatic destructive downgrade.")
