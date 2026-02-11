from typing import Any, Dict, Optional
import asyncio

import asyncpg
from motor.motor_asyncio import AsyncIOMotorClient

from config import get_settings


class Database:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._pg_pool: Optional[asyncpg.Pool] = None
        self._mongo_client: Optional[AsyncIOMotorClient] = None

    async def connect(self, retries: int = 30, delay: float = 2.0) -> None:
        """
        Подключение к выбранной БД с простым механизмом ретраев.
        Это нужно, чтобы приложение не падало, пока Postgres/Mongo ещё инициализируются.
        """
        last_exc: Optional[BaseException] = None
        for _ in range(retries):
            try:
                if self.settings.db_type == "postgres":
                    self._pg_pool = await asyncpg.create_pool(
                        host=self.settings.postgres_host,
                        port=self.settings.postgres_port,
                        user=self.settings.postgres_user,
                        password=self.settings.postgres_password,
                        database=self.settings.postgres_db,
                        min_size=5,
                        max_size=20,
                    )
                    return
                if self.settings.db_type == "mongo":
                    uri = f"mongodb://{self.settings.mongo_host}:{self.settings.mongo_port}"
                    self._mongo_client = AsyncIOMotorClient(uri)
                    # простая проверка подключения
                    await self._mongo_client.admin.command("ping")
                    return
                raise ValueError(f"Unsupported DB_TYPE: {self.settings.db_type}")
            except BaseException as exc:  # noqa: BLE001
                last_exc = exc
                await asyncio.sleep(delay)

        raise RuntimeError(f"Failed to connect to database after retries: {last_exc}") from last_exc

    async def disconnect(self) -> None:
        if self._pg_pool is not None:
            await self._pg_pool.close()
            self._pg_pool = None
        if self._mongo_client is not None:
            self._mongo_client.close()
            self._mongo_client = None

    async def fetch_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        if self.settings.db_type == "postgres":
            if self._pg_pool is None:
                raise RuntimeError("Postgres pool is not initialized")
            async with self._pg_pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT id, name, email, created_at, last_login_at "
                    "FROM users WHERE id = $1",
                    user_id,
                )
            if row is None:
                return None
            return dict(row)

        if self.settings.db_type == "mongo":
            if self._mongo_client is None:
                raise RuntimeError("Mongo client is not initialized")
            db = self._mongo_client[self.settings.mongo_db]
            doc = await db.users.find_one({"_id": user_id})
            if doc is None:
                return None
            # Mongo возвращает ObjectId и datetime в собственных форматах; для
            # benchmark нам достаточно привести ключи к тем же именам.
            return {
                "id": doc.get("_id"),
                "name": doc.get("name"),
                "email": doc.get("email"),
                "created_at": doc.get("created_at"),
                "last_login_at": doc.get("last_login_at"),
            }

        raise ValueError(f"Unsupported DB_TYPE: {self.settings.db_type}")


db = Database()


