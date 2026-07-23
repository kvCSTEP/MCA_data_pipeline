from prefect import flow, task, get_run_logger, pause_flow_run
import os
import subprocess
from prefect.context import get_run_context

from helpers.prefect_input_classes import *
from helpers.prefect_helper import get_run_date, get_parameter_content
from teams_notifications import (on_completion, on_crashed, 
                                 on_failure, on_running, 
                                 on_cancellation, notify_paused)
@task(task_run_name=f"area_calculation python call"
      )
async def run_area_calc(input_folder: str, output_folder: str, check_first: bool):
    logger = get_run_logger()
    logger.info("========= input path exists ? ==========")
    logger.info(os.path.exists(input_folder))
    logger.info("========= output path exists ? ==========")
    logger.info(os.path.exists(output_folder))
    logger.info("========= check_first ? ==========")
    logger.info(f"{check_first}--{type(check_first)}")
    logger.info("Pausing — waiting for operator input before Stage 2 ...")
    try:
        result = subprocess.run(
            [
                "python",
                "/app/services/spatial_processing/O1_area_calculation.py",
                "--input_file", input_folder,
                "--output_file", output_folder,
                "--check_first", str(check_first)
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
@flow(name="area_calculation",
    flow_run_name= lambda : f"{get_parameter_content('city')} {get_run_date()}",
    on_completion=[on_completion],
    on_cancellation=[on_cancellation],
    on_crashed=[on_crashed],
    on_failure=[on_failure],
    on_running=[on_running]
    )
async def area_calculation(city: str):
    
    ctx = get_run_context()
    await notify_paused(ctx.flow_run.id, ctx.flow.name, ctx.flow_run.name)
    area_input: AreaCalculationInput = await pause_flow_run(
        wait_for_input=AreaCalculationInput,
        timeout=TIMEOUT_SEC,   # auto-fail after 1 hour if nobody resumes
        key=get_unique_id()
    )
    area_calc_script_output = await run_area_calc(area_input.input_folder,
                                                  area_input.output_folder,
                                                  area_input.check_first)
    