from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import Settings


class Base(DeclarativeBase):
    pass


def make_engine(settings: Settings):
    return create_engine(
        settings.database_url, connect_args={"connect_timeout": 3},
        pool_pre_ping=True, hide_parameters=True,
    )
