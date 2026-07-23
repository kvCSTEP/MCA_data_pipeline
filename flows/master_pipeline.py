from helpers.prefect_input_classes import *
from prefect.deployments import run_deployment
from prefect import flow
from helpers.prefect_helper import get_parameter_content, get_run_date
from teams_notifications import (on_completion, on_crashed, 
                                 on_failure, on_running, 
                                 on_cancellation)

@flow(name="master_pipeline",
    flow_run_name= lambda : f"{get_parameter_content('city')} {get_run_date()}",
    on_completion=[on_completion],
    on_cancellation=[on_cancellation],
    on_crashed=[on_crashed],
    on_failure=[on_failure],
    on_running=[on_running]
    )
async def master_pipeline(city: str):
    
    mca_result = await run_deployment(
        name="mca_script_run/Script 01 - MCA",
        parameters={"city": city},
        timeout=None,
    )
    
    area_calculation_result = await run_deployment(
        name="area_calculation/Script 02 - Area calculation",
        parameters={"city": city},
        timeout=None,       
    )
    
    spatial_join_result = await run_deployment(
        name="spatial_joins/Script 03 - spatial join",
        parameters={"city": city},
        timeout=None,         
    )
    
    csv_polygon_result = await run_deployment(
        name="CSV-Polygon mapping/Script 04 - csv polygon map",
        parameters={"city": city},
        timeout=None,         
    )
    
    csv_polygon_new_result = await run_deployment(
        name="csv_polygon_map_new/Script 05 - csv polygon map new",
        parameters={"city": city},
        timeout=None,         
    )
    return csv_polygon_new_result