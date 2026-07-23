"""
Resolves a flow run to its topmost ancestor by walking parent_task_run_id.

This relies on Prefect's default linking behavior: when a flow calls
run_deployment() from inside a task, the resulting flow run's
parent_task_run_id points back to that calling task run, and that task
run's flow_run_id is the parent flow. Repeating this walk finds the true
root regardless of nesting depth.
"""

from typing import Union
from uuid import UUID

from prefect.client.orchestration import get_client


async def get_topmost_ancestor_id(flow_run_id: Union[UUID, str]) -> UUID:
    """
    Returns the flow_run_id of the topmost ancestor of the given flow run.
    If the flow run has no parent, returns its own id.
    """
    current_id = UUID(str(flow_run_id))

    async with get_client() as client:
        while True:
            flow_run = await client.read_flow_run(current_id)
            if flow_run.parent_task_run_id is None:
                return current_id
            task_run = await client.read_task_run(flow_run.parent_task_run_id)
            current_id = task_run.flow_run_id


async def get_flow_run_url(flow_run_id: Union[UUID, str]) -> str:
    from .config import settings

    return f"{settings.prefect_ui_base_url}/flow-runs/flow-run/{flow_run_id}"
