from prefect import get_run_logger
from O365 import Account

from helpers.prefect_helper import *

mca_recepiants = ["keerthi.vignesh@cstep.in"]
area_clac_recepiants = ["keerthi.vignesh@cstep.in"]
spatial_join_recepiants = ["keerthi.vignesh@cstep.in"]
csv_polygon_recepiants = ["keerthi.vignesh@cstep.in"]

async def send_email(subject: str, body: str, to: list[str]):   
    ms_app_info = await get_prefect_variable("ms_app_info")
    app_password = (await get_prefect_secret("app-secret")).get()
    
    logger = get_run_logger()
    logger.info("-"*100)
    logger.info(ms_app_info)
    credentials = (ms_app_info['client_id'], app_password)
    account = Account(credentials, auth_flow_type='credentials', tenant_id=ms_app_info["tenant_id"])
    try:  
        if account.authenticate(scopes=['message.send']):
            logger.info("Authenticated successfully without user interaction!")
            
            mailbox = account.mailbox(resource='keerthi.vignesh@cstep.in') 
            m = mailbox.new_message()
            m.to.add(to)
            m.subject = subject
            m.body = body
            m.send()
    except Exception as e:
        logger.info("="*50)
        logger.info("Exception :",e)