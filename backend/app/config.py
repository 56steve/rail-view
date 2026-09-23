"""Application configuration, loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the RailView backend.

    All fields have safe local-dev defaults. The live pipeline (simulator,
    processor, WebSocket hub) runs entirely in memory, so the API boots
    without Postgres or Redis; only `scripts/seed_db.py` needs a database.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://railpulse:railpulse@localhost:5432/railpulse"
    redis_url: str = "redis://localhost:6379/0"

    # How often (seconds) the simulator advances trains and the WebSocket
    # hub broadcasts a position snapshot to all connected clients. Which
    # trains run comes from the official timetable, not from settings.
    simulation_tick_seconds: float = 1.0

    # If no position update for a train is received/generated within this
    # window, clients must treat that train's data as stale rather than
    # inventing a new position.
    stale_after_seconds: float = 15.0

    cors_allow_origins: list[str] = ["http://localhost:3000"]

    # Next.js dev picks the next free port when 3000 is taken (3001, 3002,
    # ...), so local dev additionally allows any localhost origin via
    # regex. Production deployments should set this to None via env and
    # rely solely on `cors_allow_origins`.
    cors_allow_origin_regex: str | None = r"^http://localhost:\d+$"


@lru_cache
def get_settings() -> Settings:
    return Settings()
