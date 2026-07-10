
from prefect import flow, task, get_run_logger, pause_flow_run
import subprocess

from helpers.email_helper import send_email
from helpers.prefect_input_classes import *
from helpers.prefect_helper import get_run_date, get_parameter_content

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
      )
async def csv_polygon_map_new(city: str):
    logger = get_run_logger()
    logger.info("Waitng for CSV-polygon mapping inputs(shp_folder, csv_path, output_csv_path)...")
    csv_polygon_input: CsvPolygonInput = await pause_flow_run(
        wait_for_input=CsvPolygonInput,
        timeout=TIMEOUT_SEC,
        key=get_unique_id()
    )
    
    csv_polygon_output = run_csv_polygon(csv_polygon_input)
    
    if csv_polygon_output:
        await send_email(body="csv-polygon mapping script completed successfully", 
                   to=["keerthi.vignesh@cstep.in"],
                   subject="update on csv-polygon mapping"
                   )
    
    else:
        await send_email(body="csv-polygon mapping script Failed. ", 
                   to=["keerthi.vignesh@cstep.in"],
                   subject="update on csv-polygon mapping"
                   )