from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from app.config import Settings, get_settings


def create_engine_from_settings(settings: Settings) -> Engine:
    return create_engine(settings.DATABASE_URL)


@lru_cache
def get_engine() -> Engine:
    return create_engine_from_settings(get_settings())
