"""
Minimal asyncpg access to the teams_threads table. Uses a module-level
connection pool, lazily created, matching the asyncpg-driver pattern
already used elsewhere in this project.
"""

from typing import Union

import asyncpg
import logging
from .config import settings

_pool: Union[asyncpg.Pool, None] = None


async def _get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        logging.info("--- DB_URL:", settings.database_url, "---")
        _pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=5)
    return _pool


async def get_thread_message_id(flow_run_id: str) -> Union[str, None]:
    """Returns the root Teams message_id for a top-level flow_run_id, or None."""
    pool = await _get_pool()
    row = await pool.fetchrow(
        "SELECT message_id FROM teams_threads WHERE flow_run_id = $1",
        flow_run_id,
    )
    return row["message_id"] if row else None


async def insert_thread(flow_run_id: str, flow_name: str, message_id: str) -> None:
    pool = await _get_pool()
    await pool.execute(
        """
        INSERT INTO teams_threads (flow_run_id, flow_name, team_id, channel_id, message_id)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (flow_run_id) DO NOTHING
        """,
        flow_run_id,
        flow_name,
        settings.teams_team_id,
        settings.teams_channel_id,
        message_id,
    )
