from prefect import serve
from flows import csv_polygon_map_flow_new, mca_flow, area_calc_flow, spatial_join_flow, csv_polygon_map_flow, master_pipeline
from helpers.prefect_input_classes import *

DOCKER_IMAGE_NAME = "mca-runner"

if __name__=="__main__":
    mca = mca_flow.mca_script_run.to_deployment(name="Script 01 - MCA")
    area_calc = area_calc_flow.area_calculation.to_deployment(name="Script 02 - Area calculation")
    spatial_join = spatial_join_flow.spatial_joins.to_deployment(name="Script 03 - spatial join")
    csv_polygon = csv_polygon_map_flow.csv_polygon_map.to_deployment(name="Script 04 - csv polygon map")
    csv_polygon_new = csv_polygon_map_flow_new.csv_polygon_map_new.to_deployment(name="Script 05 - csv polygon map new")
    pipeline = master_pipeline.master_pipeline.to_deployment(name="Pipeline orchestrator")
    
    
    # deploy(mca, area_calc, spatial_join, csv_polygon, master_pipeline)
    serve(mca, area_calc, spatial_join, csv_polygon, pipeline, csv_polygon_new)
    