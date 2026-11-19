"""Record why a Time Sculpture session delivered its pose sequence."""

import sqlalchemy as sa
from alembic import op

revision = "20261119_10"
down_revision = "20261119_09"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("filmstrips", sa.Column("fallback_reason", sa.String(), nullable=True))


def downgrade() -> None:
    raise RuntimeError("The photo booth schema has no automatic destructive downgrade.")
