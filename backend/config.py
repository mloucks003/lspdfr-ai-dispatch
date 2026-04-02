from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables or config.ini."""

    # Database — SQLite by default (zero install), MongoDB optional
    db_backend: str = "sqlite"  # "sqlite" or "mongodb"
    sqlite_path: str = "dispatch.db"
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_database: str = "lspdfr_dispatch"

    # API Keys
    api_key: str = "changeme"
    openai_api_key: str = ""

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Officer defaults
    default_callsign: str = "1-Adam-12"

    model_config = {"env_prefix": "DISPATCH_"}


settings = Settings()
