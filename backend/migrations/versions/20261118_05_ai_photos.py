"""Add configurable photo effects and their local processing jobs."""

import sqlalchemy as sa
from alembic import op

revision = "20261118_05"
down_revision = "20261118_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    templates = op.create_table(
        "ai_templates",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("description", sa.String(240), nullable=False),
        sa.Column("prompt", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
    )
    op.bulk_insert(templates, [{
        "id": "cinematic-portrait",
        "name": "Cinematic portrait",
        "description": "Warm highlights and cool shadows for a film-style finish.",
        "prompt": "Give the photograph cool shadows and warm highlights with cinematic color grading. "
                  "Preserve the subject's identity, pose, clothing, and composition.",
        "enabled": True,
    }])
    op.create_table(
        "ai_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("original_id", sa.Uuid(), sa.ForeignKey("original_photos.id"), nullable=False),
        sa.Column("template_id", sa.String(64), sa.ForeignKey("ai_templates.id"), nullable=False),
        sa.Column("prompt", sa.String(), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("sends_photo", sa.Boolean(), nullable=False),
        sa.Column("consented_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("detail", sa.String(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("byte_size", sa.Integer()),
        sa.Column("width", sa.Integer()),
        sa.Column("height", sa.Integer()),
        sa.UniqueConstraint("original_id", "template_id", "provider", name="ai_job_one_result"),
        sa.CheckConstraint(
            "state IN ('queued', 'processing', 'completed', 'failed', 'interrupted', 'canceled')",
            name="ai_job_state",
        ),
        sa.CheckConstraint(
            "(state = 'completed' AND width IS NOT NULL AND height IS NOT NULL AND byte_size IS NOT NULL)"
            " OR (state <> 'completed' AND width IS NULL AND height IS NULL AND byte_size IS NULL)",
            name="ai_job_result",
        ),
    )
    op.create_index("ix_ai_jobs_provider_state_updated_at", "ai_jobs", ["provider", "state", "updated_at"])


def downgrade() -> None:
    raise RuntimeError("The photo booth schema has no automatic destructive downgrade.")
