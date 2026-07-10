import asyncio
import os
import json

from prefect.variables import Variable
from prefect.blocks.system import Secret
from prefect.exceptions import ObjectAlreadyExists
from prefect.client.schemas.actions import WorkPoolCreate
from prefect.client.orchestration import get_client

async def init():
    await Variable.set(
        name="ms_app_info",
        value=json.loads(os.environ["MS_APP_INFO"]),
        overwrite=True,
    )
    
    await Variable.set(
        name="test_mca_db_info",
        value=json.loads(os.environ["TEST_MCA_DB_INFO"]),
        overwrite=True,
    )

    smb_username = Secret(value=os.environ["SMB_USERNAME"])
    await smb_username.save("smb-username", overwrite=True)

    smb_password = Secret(value=os.environ["SMB_PASSWORD"])
    await smb_password.save("smb-password", overwrite=True)
    
    
    app_secret = Secret(value=os.environ["APP_SECRET"])
    await app_secret.save("app-secret", overwrite=True)
    
    db_password = Secret(value=os.environ["DB_PASSWORD"])
    await db_password.save("db-password", overwrite=True)
    
    # Work pools is required when flows are deployed via .deploy().
    # When deployed via serve(), all the flows are sub-process of serve() process
    
    # await create_work_pool_if_not_exists("mca-pipeline-pool", "process")
    
    
async def create_work_pool_if_not_exists(pool_name: str, pool_type: str = "process"):
    async with get_client() as client:
        try:
            work_pool_config = WorkPoolCreate(
                name = pool_name,
                type = pool_type
            )
            await client.create_work_pool(work_pool = work_pool_config)
        except ObjectAlreadyExists:
            print(f"--- Work pool '{pool_name}' already exists. Skipping creation. ---") 
        except Exception as e:
            print("--- error while creating pool---")
            print(e)  
            
asyncio.run(init())