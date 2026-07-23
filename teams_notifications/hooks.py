"""
Wire these into your five @flow decorators. See README for exact wiring.

Design recap:
  - TOP_LEVEL_FLOW_NAMES create a thread the first time they're seen
    Running, and every one of their own later state changes replies into
    that same thread (via the same topmost-ancestor lookup as everyone
    else -- for a top-level flow, "topmost ancestor" is itself).
  - Every other flow, at any nesting depth, resolves its topmost ancestor
    and replies into that thread if a row exists.
  - If no row exists (e.g. a sub-deployment run manually from the UI, with
    no top-level parent that ever registered), the message is posted
    standalone and no DB row is written.
  - No error detail is included in messages, only state + a link, per
    current requirements.
"""

from typing import Union
from uuid import UUID

from prefect.states import State

from . import db_helper as db

from .notifier import create_root_message, post_standalone, reply_to_thread
from .thread_resolver import get_flow_run_url, get_topmost_ancestor_id

TOP_LEVEL_FLOW_NAMES = {"master_pipeline", "two_pass_orchestration"}

_STATE_EMOJI = {
    "RUNNING": "▶️",
    "COMPLETED": "✅",
    "FAILED": "❌",
    "CRASHED": "💥",
    "PAUSED": "⏸️",
}


def _format_message(flow_name: str, state_label: str, url: str) -> str:
    emoji = _STATE_EMOJI.get(state_label.upper(), "ℹ️")
    return f"{emoji} <b>{flow_name}</b> — {state_label.title()}<br><a href='{url}'>{url}</a>"


async def notify_state_change(flow_run_id, flow_name: str, run_name: Union[str, None], state_label: str) -> None:
    flow_run_id = UUID(str(flow_run_id))
    url = await get_flow_run_url(flow_run_id)

    is_top_level = flow_name in TOP_LEVEL_FLOW_NAMES

    if is_top_level and state_label.upper() == "RUNNING":
        existing = await db.get_thread_message_id(str(flow_run_id))
        if existing is None:
            display_name = f"{flow_name} {run_name}"          # "master_pipeline bangalore - 2026-07-23T14-30"
            text = _format_message(display_name, state_label, url)
            message_id = await create_root_message(text)
            await db.insert_thread(str(flow_run_id), flow_name, message_id)
            return

    # every reply — root's own later states, and every sub-flow — uses flow_name only
    text = _format_message(flow_name, state_label, url)

    root_id = await get_topmost_ancestor_id(flow_run_id)
    message_id = await db.get_thread_message_id(str(root_id))

    if message_id is not None:
        await reply_to_thread(message_id, text)
    else:
        await post_standalone(text)

# ---- Prefect state-change hooks -------------------------------------------
# Attach these directly on the @flow decorator, e.g.:
#
#   @flow(on_running=[on_running], on_completion=[on_completion],
#         on_failure=[on_failure], on_crashed=[on_crashed])
#   def master_pipeline1(...): ...

async def on_running(flow, flow_run, state: State) -> None:
    await notify_state_change(flow_run.id, flow.name, flow_run.name, "Running")


async def on_completion(flow, flow_run, state: State) -> None:
    await notify_state_change(flow_run.id, flow.name, flow_run.name, "Completed")


async def on_failure(flow, flow_run, state: State) -> None:
    await notify_state_change(flow_run.id, flow.name, flow_run.name, "Failed")


async def on_crashed(flow, flow_run, state: State) -> None:
    await notify_state_change(flow_run.id, flow.name, flow_run.name, "Crashed")
    
async def on_cancellation(flow, flow_run, state: State) -> None:
    await notify_state_change(flow_run.id, flow.name, flow_run.name, "Cancelled")

# ---- Paused: no native flow-level hook exists for this -----------------
# Prefect doesn't fire on_running/on_completion/on_failure/on_crashed for a
# pause -- pausing happens via pause_flow_run() called *inside* the flow.
# Call this explicitly right where you call pause_flow_run(), using the
# same context (must be directly inside the @flow body, not a @task, same
# constraint pause_flow_run() itself has).
async def notify_paused(flow_run_id: Union[UUID, str], flow_name: str, flow_run_name: str) -> None:
    await notify_state_change(flow_run_id, flow_name,flow_run_name , "Paused")
