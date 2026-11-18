"""Store scoped, short-lived phone download links."""

import sqlalchemy as sa
from alembic import op

revision = "20261118_03"
down_revision = "20261118_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "download_links",
        sa.Column("digest", sa.String(64), primary_key=True),
        sa.Column("original_id", sa.Uuid(), sa.ForeignKey("original_photos.id", ondelete="CASCADE")),
        sa.Column("filmstrip_id", sa.Uuid(), sa.ForeignKey("filmstrips.id", ondelete="CASCADE")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("(original_id IS NULL) <> (filmstrip_id IS NULL)", name="download_link_one_asset"),
    )
    op.create_index("ix_download_links_expires_at", "download_links", ["expires_at"])


def downgrade() -> None:
    raise RuntimeError("The photo booth schema has no automatic destructive downgrade.")
