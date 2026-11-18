"""Allow temporary phone links to reference a completed photo effect."""

import sqlalchemy as sa
from alembic import op

revision = "20261118_07"
down_revision = "20261118_06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("download_links", sa.Column("effect_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "download_links_effect_id_fkey", "download_links", "ai_jobs", ["effect_id"], ["id"], ondelete="CASCADE",
    )
    op.drop_constraint("download_link_one_asset", "download_links", type_="check")
    op.create_check_constraint(
        "download_link_one_asset", "download_links", "num_nonnulls(original_id, filmstrip_id, effect_id) = 1",
    )


def downgrade() -> None:
    raise RuntimeError("The photo booth schema has no automatic destructive downgrade.")
