from re import S

from prefect.input import RunInput

import uuid

TIMEOUT_SEC = 3600

def get_unique_id():
    return uuid.uuid4().hex[:8]

class AreaCalculationInput(RunInput):
    input_folder: str  
    output_folder: str 
    check_first: bool = False
    
class SpatialJoinInput(RunInput):
    ward_shapefile_path: str
    input_folder: str
    output_folder: str
    max_workers: int = 10
    ward_name_field: str = "Ward_Name"
    ward_no_field: str = "Ward_No"
    predicate: str = "intersects"
    
class CsvPolygonInput(RunInput):
    shp_folder: str
    csv_path: str
    output_csv_path: str
    
class WaitAndProceed(RunInput):
    proceed: bool
    
class MCAScriptInput(RunInput):
    job_vars: dict
    
class CityInput(RunInput):
    city: str
    
class MergedScriptInput(RunInput):
    INPUT_SLOPE_SHP_FOLDER: str
    WARD_BOUNDARY_SHP: str
    WARD_NAME_FIELD: str
    WARD_NO_FIELD: str
    SPATIAL_JOIN_PREDICATE: str
    INPUT_POLYGON_CSV: str
    FINAL_SHP_OUTPUT_FOLDER: str
    OUT_WARD_TILE_CSV: str
    OUT_POLYGON_WITH_WARDS_CSV: str
    
    