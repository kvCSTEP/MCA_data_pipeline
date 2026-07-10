from prefect.variables import Variable
from prefect.blocks.system import Secret
import datetime
from datetime import datetime
from prefect.context import FlowRunContext

async def get_prefect_variable(variable_name: str):
    return await Variable.get(variable_name)

async def get_prefect_secret(secret_block_name: str):
    return await Secret.load(secret_block_name)

def get_run_date():
    return f"{datetime.now():%Y-%m-%d_%H-%M-%S}"

def get_parameter_content(parameter_name: str):
    # 1. Reach into Prefect's active execution context tracking layer
    ctx = FlowRunContext.get()
    
    if ctx and ctx.parameters:
        # Extract straight from the parameters object
        parameter_content = ctx.parameters.get(parameter_name) or "unknown"
        return parameter_content
    return "unknown_parameter"