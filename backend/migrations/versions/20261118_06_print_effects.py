"""Allow the existing print queue to reference a completed photo effect."""

import sqlalchemy as sa
from alembic import op

revision = "20261118_06"
down_revision = "20261118_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("print_jobs", sa.Column("effect_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("print_jobs_effect_id_fkey", "print_jobs", "ai_jobs", ["effect_id"], ["id"])
    op.create_unique_constraint("print_jobs_effect_id_key", "print_jobs", ["effect_id"])
    op.drop_constraint("print_job_one_asset", "print_jobs", type_="check")
    op.create_check_constraint("print_job_one_asset", "print_jobs", "num_nonnulls(original_id, filmstrip_id, effect_id) = 1")


def downgrade() -> None:
    raise RuntimeError("The photo booth schema has no automatic destructive downgrade.")
