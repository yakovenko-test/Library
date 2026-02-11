from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException

from config import get_settings
from db import db

settings = get_settings()
app = FastAPI(title="Mongo vs Postgres Benchmark API")


@app.on_event("startup")
async def on_startup() -> None:
    await db.connect()


@app.on_event("shutdown")
async def on_shutdown() -> None:
    await db.disconnect()


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {"status": "ok", "db_type": settings.db_type}


@app.get("/users/{user_id}")
async def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    user = await db.fetch_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


