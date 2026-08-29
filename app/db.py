from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from app.config import Settings, get_settings


def create_engine_from_settings(settings: Settings) -> Engine:
    url = settings.DATABASE_URL
    kwargs: dict = {}
    if url.startswith("sqlite"):
        # Search runs in a thread pool; connections must be usable across threads.
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)


@lru_cache
def get_engine() -> Engine:
    return create_engine_from_settings(get_settings())
