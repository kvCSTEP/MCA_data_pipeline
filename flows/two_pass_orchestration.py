from helpers.prefect_input_classes import *
from prefect.deployments import run_deployment
from prefect import flow
from helpers.prefect_helper import get_parameter_content, get_run_date
from teams_notifications import (on_completion, on_crashed, 
                                 on_failure, on_running, 
                                 on_cancellation)

@flow(name="two_pass_orchestration",
    flow_run_name= lambda : f"{get_parameter_content('city')} {get_run_date()}",
    on_completion=[on_completion],
    on_cancellation=[on_cancellation],
    on_crashed=[on_crashed],
    on_failure=[on_failure],
    on_running=[on_running]
    )
async def two_pass_orchestration(city: str):
    mca_result = await run_deployment(
        name="mca_script_run/Script 01 - MCA",
        parameters={"city": city},
        timeout=None,
    )
    
    spatial_processing = await run_deployment(
        name="merger_spatial_processing/merged spatial processing", # flow name / deployment name
        parameters={"city": city},
        timeout=None,       
    )
    return spatial_processing