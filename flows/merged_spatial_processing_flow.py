from prefect import flow, task, get_run_logger, pause_flow_run
import os
import subprocess
from prefect.context import get_run_context

from helpers.prefect_input_classes import *
from helpers.prefect_helper import get_run_date, get_parameter_content
from teams_notifications import (on_completion, on_crashed, 
                                 on_failure, on_running, 
                                 on_cancellation, notify_paused)

@task(task_run_name=f"run merged script task"
      )
async def run_merged_script(
    INPUT_SLOPE_SHP_FOLDER: str,
    WARD_BOUNDARY_SHP: str,
    WARD_NAME_FIELD: str,
    WARD_NO_FIELD: str,
    SPATIAL_JOIN_PREDICATE: str,
    INPUT_POLYGON_CSV: str,
    FINAL_SHP_OUTPUT_FOLDER: str,
    OUT_WARD_TILE_CSV: str,
    OUT_POLYGON_WITH_WARDS_CSV: str
):
    logger = get_run_logger()
    try:
        result = subprocess.run(
            [
                "python",
                "/app/services/spatial_processing/merged_slope_ward_pipeline.py",
                "--input_slope_shp_folder", INPUT_SLOPE_SHP_FOLDER,
                "--ward_boundary_shp", WARD_BOUNDARY_SHP,
                "--ward_name_field", WARD_NAME_FIELD,
                "--ward_no_field", WARD_NO_FIELD,
                "--spatial_join_predicate", SPATIAL_JOIN_PREDICATE,
                "--input_polygon_csv", INPUT_POLYGON_CSV,
                "--final_shp_output_folder", FINAL_SHP_OUTPUT_FOLDER,
                "--out_ward_tile_csv", OUT_WARD_TILE_CSV,
                "--out_polygon_with_wards_csv", OUT_POLYGON_WITH_WARDS_CSV,
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

    return result.stdout
# ===========================================================================================
@flow(name="merger_spatial_processing",
    flow_run_name= lambda : f"{get_parameter_content('city')} {get_run_date()}",
    on_completion=[on_completion],
    on_cancellation=[on_cancellation],
    on_crashed=[on_crashed],
    on_failure=[on_failure],
    on_running=[on_running]
    )
async def merger_spatial_processing(city: str):
    
    ctx = get_run_context()
    await notify_paused(ctx.flow_run.id, ctx.flow.name, ctx.flow_run.name)
    merged_script_inputs: MergedScriptInput = await pause_flow_run(
        wait_for_input=MergedScriptInput,
        timeout=TIMEOUT_SEC,   # auto-fail after 1 hour if nobody resumes
        key=get_unique_id()
    )
    area_calc_script_output = await run_merged_script(merged_script_inputs.INPUT_SLOPE_SHP_FOLDER,
                                                  merged_script_inputs.WARD_BOUNDARY_SHP,
                                                  merged_script_inputs.WARD_NAME_FIELD,
                                                  merged_script_inputs.WARD_NO_FIELD,
                                                  merged_script_inputs.SPATIAL_JOIN_PREDICATE,
                                                  merged_script_inputs.INPUT_POLYGON_CSV,
                                                  merged_script_inputs.FINAL_SHP_OUTPUT_FOLDER,
                                                  merged_script_inputs.OUT_WARD_TILE_CSV,
                                                  merged_script_inputs.OUT_POLYGON_WITH_WARDS_CSV
                                                  )

    