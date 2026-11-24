from alembic import context

from app import admin, ai_photos, creative, downloads, photos, printing, sessions  # Import model definitions.
from app.config import Settings
from app.db import Base, make_engine

settings = context.config.attributes.get("booth_settings") or Settings()
if context.is_offline_mode():
    context.configure(dialect_name="postgresql", target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = make_engine(settings)
    try:
        with engine.connect() as conn:
            context.configure(connection=conn, target_metadata=Base.metadata, compare_type=True)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()
