"""Add local Creative Studio results and delivery references."""

import sqlalchemy as sa
from alembic import op

revision = "20261119_08"
down_revision = "20261118_07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "creative_results",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("original_id", sa.Uuid(), sa.ForeignKey("original_photos.id"), nullable=False),
        sa.Column("treatment", sa.String(40), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("detail", sa.String(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("byte_size", sa.Integer()),
        sa.Column("width", sa.Integer()),
        sa.Column("height", sa.Integer()),
        sa.UniqueConstraint("original_id", "treatment", "version", name="creative_result_one_version"),
        sa.CheckConstraint("state IN ('queued', 'processing', 'completed', 'failed', 'canceled')",
                           name="creative_result_state"),
        sa.CheckConstraint(
            "(state = 'completed' AND width IS NOT NULL AND height IS NOT NULL AND byte_size IS NOT NULL)"
            " OR (state <> 'completed' AND width IS NULL AND height IS NULL AND byte_size IS NULL)",
            name="creative_result_file",
        ),
    )
    op.create_index("ix_creative_results_state_updated_at", "creative_results", ["state", "updated_at"])
    for table, constraint in (("download_links", "download_link_one_asset"), ("print_jobs", "print_job_one_asset")):
        op.add_column(table, sa.Column("creative_id", sa.Uuid()))
        op.create_foreign_key(
            f"{table}_creative_id_fkey", table, "creative_results", ["creative_id"], ["id"],
            ondelete="CASCADE" if table == "download_links" else None,
        )
        op.drop_constraint(constraint, table, type_="check")
        op.create_check_constraint(
            constraint, table, "num_nonnulls(original_id, filmstrip_id, effect_id, creative_id) = 1",
        )
    op.create_unique_constraint("print_jobs_creative_id_key", "print_jobs", ["creative_id"])


def downgrade() -> None:
    raise RuntimeError("The photo booth schema has no automatic destructive downgrade.")
