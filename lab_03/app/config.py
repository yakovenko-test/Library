import os
from functools import lru_cache


class Settings:
    db_type: str
    postgres_host: str
    postgres_port: int
    postgres_db: str
    postgres_user: str
    postgres_password: str
    mongo_host: str
    mongo_port: int
    mongo_db: str

    def __init__(self) -> None:
        self.db_type = os.getenv("DB_TYPE", "postgres").lower()

        self.postgres_host = os.getenv("POSTGRES_HOST", "localhost")
        self.postgres_port = int(os.getenv("POSTGRES_PORT", "5432"))
        self.postgres_db = os.getenv("POSTGRES_DB", "benchmark")
        self.postgres_user = os.getenv("POSTGRES_USER", "benchmark")
        self.postgres_password = os.getenv("POSTGRES_PASSWORD", "benchmark")

        self.mongo_host = os.getenv("MONGO_HOST", "localhost")
        self.mongo_port = int(os.getenv("MONGO_PORT", "27017"))
        self.mongo_db = os.getenv("MONGO_DB", "benchmark")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()



