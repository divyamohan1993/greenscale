"""Thin async client to the greenscale-db service."""
from __future__ import annotations
import os
import logging
import httpx

log = logging.getLogger("db_client")
DB_URL = os.environ.get("DB_URL", "").rstrip("/")
TIMEOUT = httpx.Timeout(8.0, connect=5.0)


async def post_decision(row: dict) -> int | None:
    if not DB_URL:
        return None
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            r = await c.post(f"{DB_URL}/decisions", json=row)
            r.raise_for_status()
            return r.json().get("id")
    except Exception as e:
        log.warning("db post_decision failed: %s", e)
        return None


async def list_decisions(limit: int = 50) -> list[dict]:
    if not DB_URL:
        return []
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            r = await c.get(f"{DB_URL}/decisions", params={"limit": limit})
            r.raise_for_status()
            return r.json()
    except Exception as e:
        log.warning("db list_decisions failed: %s", e)
        return []


async def stats() -> dict:
    if not DB_URL:
        return {"connected": False}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            r = await c.get(f"{DB_URL}/stats")
            r.raise_for_status()
            d = r.json()
            d["connected"] = True
            return d
    except Exception as e:
        log.warning("db stats failed: %s", e)
        return {"connected": False, "error": str(e)}
