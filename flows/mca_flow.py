
from prefect import flow, task, get_run_logger, pause_flow_run
import subprocess
import shutil

from helpers.email_helper import send_email
from helpers.prefect_input_classes import *
from prefect.variables import Variable
from helpers.prefect_helper import get_run_date, get_parameter_content

from prefect_docker.containers import (
    create_docker_container,
    start_docker_container,
    get_docker_container_logs,
    remove_docker_container 
)

DOCKER_IMAGE_NAME = "mca-runner"
DB_INFO_VARIABLE = "test_mca_db_info"
volume_bindings = {}
async def get_db_info(prefect_variable: str, job_vars: dict, logger):
    data_path = job_vars.pop("storage_path")
    
    db_info = await Variable.get(prefect_variable)
    for k, v in db_info.items():
        job_vars[k]=v
    volume_bindings[data_path] = {
            "bind": "/data", 
            "mode": "rw"
        }
    logger.info(volume_bindings)

@task(name="run container", task_run_name="")
async def run_isolated_container(image_name: str, env: dict):
    logger = get_run_logger()
    
    env['PYTHONUNBUFFERED'] = "1"
    
    # 1. Create the container (Equivalent to docker create)
    container = await create_docker_container(
        image=image_name,
        environment=env,
        volumes=volume_bindings
    )
    
    # 2. Spin it up
    await start_docker_container(container_id=container.id)
    
    # 3. Stream and extract container logs cleanly into the Prefect dashboard
    logs = await get_docker_container_logs(container_id=container.id)
    logger.info(f"Container Output: {logs}")    
    await remove_docker_container(container_id = container.id, force=True)     
    
    
def run_docker(image: str, env: dict = {}, logger=None) -> int:
    storage_path = env.pop("storage_root")
    cmd = ["docker", "run", "--rm"]
    for k, v in env.items():
        cmd += ["-e", f"{k}={v}"]
    cmd += ["-v", storage_path]
    cmd.append(image)

    logger and logger.info(f"Running: {' '.join(cmd)}")
    logger.info(shutil.which("docker"))
    
    
    # proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    # for line in proc.stdout:
    #     logger and logger.info(line.rstrip())
    # proc.wait()
    return proc.returncode

@task(name="run-mca-scrpit", task_run_name="")
def run_mca_scrpit(image: str, job_vars: dict) -> str:
    logger = get_run_logger()
    rc = run_docker(image, job_vars, logger=logger)
    if rc != 0:
        raise RuntimeError(f"Step 1 container exited with code {rc}")
    # Return whatever step 1 produced (path, ID, etc.)
    return "/data/step1_output"   # ← replace with real output discovery

@task(name="build-image",
      task_run_name="")
def build_image(tag: str, dockerfile: str) -> str:
    logger = get_run_logger()
    logger.info(f"Building {tag} from {dockerfile} ...")
    
    proc = subprocess.Popen(
        ["docker", "build", "-f", dockerfile, "-t", tag, "."],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    for line in proc.stdout:
        logger.info(line.rstrip())
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"docker build failed for {dockerfile}")
    return tag

# --------------------------------------------------------------------------------------------------------------------

@flow(name="mca_script_run",
    flow_run_name= lambda : f"{get_parameter_content('city')} {get_run_date()}"
    )
async def mca_script_run(city: str):
    logger = get_run_logger()

    mca_input = await pause_flow_run(
        wait_for_input=MCAScriptInput,
        key=get_unique_id()
    )
    
    job_vars = mca_input.job_vars
    
    await get_db_info(DB_INFO_VARIABLE, job_vars, logger)
    logger.info("="*50)
    logger.info(job_vars)
    # mca_output = run_mca_scrpit(DOCKER_IMAGE_NAME, job_vars)
    await run_isolated_container(DOCKER_IMAGE_NAME, job_vars)
    
    msg_plain = f"MCA script run completed \n Flow is in paused status for {TIMEOUT_SEC /60} minutes."
    await send_email(subject="MCA flow update",
        to=["keerthi.vignesh@cstep.in"],
        body=msg_plain
        )    
    
