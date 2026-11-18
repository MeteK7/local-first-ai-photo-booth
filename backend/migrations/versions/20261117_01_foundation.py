"""Create booth sessions and local administrator authentication."""

from alembic import op
import sqlalchemy as sa

revision = "20261117_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "booth_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("access_digest", sa.String(64), nullable=False, unique=True),
        sa.Column("state", sa.String(12), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("state IN ('active', 'completed', 'canceled')", name="session_state"),
        sa.CheckConstraint("(state = 'active') = (ended_at IS NULL)", name="session_end"),
    )
    op.create_table(
        "admin_users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(256), nullable=False),
    )
    op.create_table(
        "admin_logins",
        sa.Column("digest", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("admin_users.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    raise RuntimeError("The initial photo booth schema has no automatic destructive downgrade.")
