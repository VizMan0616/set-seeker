from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "sqlite:///data/setseeker.db"
    # Per-solve CP-SAT wall clock (ADR 0005 / engine-spec §5). Not a queue timeout.
    SOLVER_TIME_LIMIT_MS: int = 2000
    # OR-Tools threads *inside one* solve. Peak solver threads is roughly
    # SOLVER_MAX_INFLIGHT * SOLVER_NUM_WORKERS — do not raise both on a small host.
    SOLVER_NUM_WORKERS: int = 8
    # Global cap on concurrent solve jobs (start_search, load_more, prefetch).
    # Two users must not each spawn a full OR-Tools portfolio (8+8 workers).
    SOLVER_MAX_INFLIGHT: int = 1
    # How long a request waits for a solve slot before a fast busy response.
    # Waiting keeps the TCP/tunnel connection; timeout returns 503 HTML.
    SOLVER_QUEUE_WAIT_S: float = 30.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
