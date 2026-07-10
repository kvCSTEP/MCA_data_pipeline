from prefect import flow, task, get_run_logger, pause_flow_run
import subprocess

from helpers.email_helper import send_email
from helpers.prefect_input_classes import *
from helpers.prefect_helper import get_run_date, get_parameter_content

@task(name = "spatial join task",
      task_run_name=f"spatial join python call",
      )
async def run_spatial_join(spatial_join_input: SpatialJoinInput):
    logger = get_run_logger()
    result = None
    
    ward_shapefile_path: str = spatial_join_input.ward_shapefile_path
    input_folder: str = spatial_join_input.input_folder
    output_folder: str = spatial_join_input.output_folder
    max_workers: int = spatial_join_input.max_workers
    ward_name_field: str = spatial_join_input.ward_name_field
    ward_no_field: str = spatial_join_input.ward_no_field
    predicate: str = spatial_join_input.predicate
    try:
        result = subprocess.run(
            [
                "python",
                "/app/services/spatial_processing/O2_spatial_join.py",
                "--ward_shapefile_path", ward_shapefile_path,
                "--input_folder" , input_folder,
                "--output_folder", output_folder,
                "--max_workers", str(max_workers),
                "--ward_name_field", ward_name_field,
                "--ward_no_field", ward_no_field,
                "--predicate", predicate
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        logger.info("==== sub process O/P ====")
        logger.info(result.stdout)
        return result.stdout  
    except subprocess.CalledProcessError as e:
        logger.error(f"Internal Script Stdout: {e.stdout}")
        logger.error(f"CRITICAL - Internal Script Crash Traceback:\n{e.stderr}")
        return None
    except Exception as e:
        logger.info("--- other exception ---")
        logger.error(e)
        return None
        


# =========================================================================
@flow(name="spatial_joins",
    flow_run_name= lambda : f"{get_parameter_content('city')} {get_run_date()}"
    )
async def spatial_joins(city: str):
    logger = get_run_logger()
    logger.info("Waitng for Spatial Join Inputs...")
    spatial_join_input: SpatialJoinInput = await pause_flow_run(
        wait_for_input=SpatialJoinInput,
        timeout=TIMEOUT_SEC,
        key=get_unique_id()
        )
    
    spatial_join_output = await run_spatial_join(spatial_join_input)
    
    
    if spatial_join_output:
        await send_email(subject="Spatial join update",
                   to=["keerthi.vignesh@cstep.in"],
                   body="Spatial join SUCCESS. proceed on app."
                   )
    else:
        await send_email(subject="Spatial join update",
                   to=["keerthi.vignesh@cstep.in"],
                   body="Spatial join FAILED. proceed on app."
                   )