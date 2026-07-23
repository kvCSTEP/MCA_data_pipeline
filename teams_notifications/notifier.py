"""
Thin wrapper around the three Graph calls this system needs:
  - create a root (thread-starting) channel message
  - reply into an existing thread
  - post a standalone message (used when no parent thread is found)
"""

import httpx

from .auth import get_access_token
from .config import settings

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def _channel_messages_url() -> str:
    return f"{GRAPH_BASE}/teams/{settings.teams_team_id}/channels/{settings.teams_channel_id}/messages"


async def _post(url: str, text: str) -> dict:
    token = await get_access_token()
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={"body": {"contentType": "html", "content": text}},
        )
    response.raise_for_status()
    return response.json()


async def create_root_message(text: str) -> str:
    """Posts a new top-level channel message. Returns its message id."""
    result = await _post(_channel_messages_url(), text)
    return result["id"]


async def reply_to_thread(message_id: str, text: str) -> None:
    """Posts a reply into an existing thread."""
    url = f"{_channel_messages_url()}/{message_id}/replies"
    await _post(url, text)


async def post_standalone(text: str) -> None:
    """Posts a new, unthreaded top-level message (no DB row is written for this)."""
    await _post(_channel_messages_url(), text)
