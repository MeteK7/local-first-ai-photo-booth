"""Preserve the selected language when queuing local creative artwork."""

import sqlalchemy as sa
from alembic import op

revision = "20261120_11"
down_revision = "20261119_10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("creative_results", sa.Column("render_locale", sa.String(2), server_default="en", nullable=False))


def downgrade() -> None:
    raise RuntimeError("The photo booth schema has no automatic destructive downgrade.")
