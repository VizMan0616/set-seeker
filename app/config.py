from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "sqlite:///data/setseeker.db"
    SOLVER_TIME_LIMIT_MS: int = 2000
    SOLVER_NUM_WORKERS: int = 8


@lru_cache
def get_settings() -> Settings:
    return Settings()
