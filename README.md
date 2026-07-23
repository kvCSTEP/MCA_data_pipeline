<!-- ### Project Directory Structure
> - Services
> * Includes MCA script git repo, and spatial_sprocessing script
> * Spatial processing isnt a git repo. It is copy pasted and modified as per Prefect necessity 
> 
> - Helpers
> * Prefect helper -> Get prefect secret and variables
> * Prefect input classes -> Define input class for each flow inputs
>
> - Flows
> * Create a flow for each services, like one flow for MCA script, another for Area Calculation, spatial joins
> * Contains master pipeline orchaster, which pipes MCA, and other flows
> * We can have multiple pipeline orchestration
>
> - Teams Notification
> *  -->

### MCA_RTSE_PREFECT
```
├── 📁 **flows/** -> Prefect flow for each script + orchestration
│   ├── 📄 area_calc_flow.py
│   ├── 📄 csv_polygon_map_flow.py
│   ├── 📄 csv_polygon_map_flow_new.py
│   ├── 📄 master_pipeline.py
│   ├── 📄 mca_flow.py
│   └── 📄 spatial_join_flow.py
├── 📁 **helpers/** 
│   ├── 📄 email_helper.py
│   ├── 📄 prefect_helper.py
│   └── 📄 prefect_input_classes.py
├── 📁 **services/** 
│   ├── 📁 **MCA_RTSE/** -> git clone of MCA_RTSE. Makes use of prefect-docker lib to dockerise 
│   └── 📁 **spatial_processing/** -> No repo available. Prefect compatible scripts
│       ├── 📄 O1_area_calculation.py
│       ├── 📄 O1_temp.py
│       ├── 📄 O2_spatial_join.py
│       ├── 📄 O3_csv_polygon_mapping.py
│       └── 📄 O4_mca_csv_building_polygon_map_new.py
├── 📁 **teams_notifications/** -> Threaded communication 
│   ├── 📄 001_create_teams_threads.sql -> one time run on docker volume creation
│   ├── 📄 __init__.py -> Imports hooks, and suply them to any code flows
│   ├── 📄 auth.py -> Create a short lived refresh token from a long lived access token
│   ├── 📄 config.py -> Defines a Dataclass and data populated object
│   ├── 📄 db.py -> DB helper to identify MS message thread_id and creating new thread
│   ├── 📄 Flow State Change-2026-07-20-102734-1.png
│   ├── 📄 get_initial_refresh_token.py -> One time setup - Get the access token, and store it it prefect variable
│   ├── 📄 hooks.py -> Flow state change messages 
│   ├── 📄 notifier.py -> Helper to hooks
│   ├── 📄 README.md
│   └── 📄 thread_resolver.py -> help identify top most message id, get flow run URL
├── 📄 deploy_flows.py -> Docker - prefect worker initial command. Serve() the flows 
├── 📄 docker-compose.yaml
├── 📄 Dockerfile
├── 📄 init_prefect.py -> Create prefect secret and variables after
├── 📄 nginx-entrypoint.sh -> Create nginx.conf using the template
├── 📄 nginx.conf.template
├── 📄 README.md
└── 📄 requirements.txt
```

### Environment variables
> - SMB - Shared Memory Block
> * username, and password
> - Asure app info
> * Client id, tenant id, secret
> - MCA DB info
> * host, db name, user name, and password
> - Prefect DB
> * DB URL, username, password, and DB name
> Prefect 
> * PREFECT_API_KEY, PREFECT_API_URL, PREFECT_API_URL_DIRECT
> - MS-Teams thread 
> * MS_TEAMS_CHANNEL_ID, ACTUAL_PREFCE_URL

### How to set up the pipeline ?
1. Create MCA-runner image 
2. docker-compose up --build 
3. execute teams_notifications\001_create_teams_threads.sql
4. execute get_initial_refresh_token.py
   * The script will print a ms login url with code. Login with the app user having admin access. we will get the access token. paste it in the prefect secret
5. https://prefect-server/ -> This will point us to prefect dashboard

### Notes
* On any update on MCA_RTSE repo, the current repo should do git pull, create mca-runner image

