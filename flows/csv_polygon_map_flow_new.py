
from prefect import flow, task, get_run_logger, pause_flow_run
import subprocess
from prefect.context import get_run_context

from helpers.prefect_input_classes import *
from helpers.prefect_helper import get_run_date, get_parameter_content
from teams_notifications import (on_completion, on_crashed, 
                                 on_failure, on_running, 
                                 on_cancellation, notify_paused)
@task(task_run_name=f"csv_polygon_mapping python call"
      )
def run_csv_polygon(csv_polygon_input: CsvPolygonInput):
    logger = get_run_logger()
    
    shp_folder: str = csv_polygon_input.shp_folder
    csv_path: str = csv_polygon_input.csv_path
    output_csv_path: str = csv_polygon_input.output_csv_path
    
    try:
        result = subprocess.run(
            [
                "python",
                "/app/services/spatial_processing/O4_mca_csv_building_polygon_map_new.py",
                "--shp_folder", shp_folder,
                "--csv_path", csv_path,
                "--output_csv_path", output_csv_path
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        logger.info("==== sub process O/P ====")
        logger.info(result.stdout)
    except subprocess.CalledProcessError as e:
        logger.error(f"Internal Script Stdout: {e.stdout}")
        logger.error(f"CRITICAL - Internal Script Crash Traceback:\n{e.stderr}")

# ======================================================================
@flow(name="csv_polygon_map_new",
    flow_run_name= lambda : f"{get_parameter_content('city')} {get_run_date()}",
    on_completion=[on_completion],
    on_cancellation=[on_cancellation],
    on_crashed=[on_crashed],
    on_failure=[on_failure],
    on_running=[on_running]
    )
async def csv_polygon_map_new(city: str):
    logger = get_run_logger()
    
    ctx = get_run_context()
    await notify_paused(ctx.flow_run.id, ctx.flow.name, ctx.flow_run.name)
    logger.info("Waitng for CSV-polygon mapping inputs(shp_folder, csv_path, output_csv_path)...")
    csv_polygon_input: CsvPolygonInput = await pause_flow_run(
        wait_for_input=CsvPolygonInput,
        timeout=TIMEOUT_SEC,
        key=get_unique_id()
    )
    
    csv_polygon_output = run_csv_polygon(csv_polygon_input)