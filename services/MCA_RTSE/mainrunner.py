# Profiling imports
import configparser
import io
import json
import pstats
# Local imports
import socketserver as ss
import sys
from cProfile import Profile
from collections import namedtuple

import numpy as np
from pydantic import ValidationError

import dataloader as dl
import layoutEngine2 as ca2
import params
from params import DInput

config = configparser.ConfigParser()
config.read('testing.ini')

envv = dict(config['Environment'])
ini_params = dict(config['Parameters'])

params.PANEL_WATTAGE = int(ini_params['panel_wattage'])
params.GRIDCELL_SIZE = float(ini_params['grid_size'])

pp_dimen = ini_params['panel_dimen'].split(",")
params.PANEL_DIMEN = (int(pp_dimen[0]), int(pp_dimen[1]))
params.PANEL_ENERGY_EFF = float(ini_params['panel_energy_eff'])

params.GRIDCELL_AREA = params.gridArea()
params.PANEL_SIZE = params.panelSize()

params.TRIG_LVL_NEW_ROW = float(ini_params['hyst_new_row'])
params.TRIG_LVL_NEW_CLUS = float(ini_params['hyst_new_clus'])
params.TRIG_LEVELS = (params.TRIG_LVL_NEW_ROW, params.TRIG_LVL_NEW_CLUS)

params.ROOF_ALBEDO = float(ini_params['roof_albedo'])
params.SOLAR_CONSTANT = float(ini_params['solar_constant'])
mhm = ini_params['mount_height_multipliers'].split(",")
params.MOUNT_HEIGHTS_MULTS = np.array(mhm, dtype=float)

params.ALLOWED_BLOCK_PANEL_SHAPES = {
    'samerow': [(1, 1), (2, 1), (3, 1), (4, 1)],
    'diffrow': [],  # [(1,params.MIN_PANELS_IN_ROW)],
    'newclus': [(1, 2), (1, 3), (2, 2), (2, 3), (3, 3), (3, 4), (4, 4)]
}

CityInfo = namedtuple('CityInfo', ['utm_zone_code', 'utm_zone_number', 'data_storage_type', 'storage_root',
                                   'filename_preamble'])


# # mumbai_hdf_root = r"X:\TN_CHENNAI\5_CSTEP_TN_CHENNAI_HDF"
# mumbai_hdf_root = r"Z:\EDALL Deliverables\processeddata\INDORE_DELIVERY\7_HDF"
# jabalpur_hdf_root = r"W:\MP\JABALPUR_HDF5"
# gwalior_hdf_root = r"Z:\EDALL Deliverables\processeddata\GWALIOR_DELIVERY\7_HDF"
# bhopal_hdf_root = r"Z:\EDALL Deliverables\processeddata\BHOPAL_DELIVERY\7_HDF"
# raipur_hdf_root = r"W:\chhattisgarh\cstep_raipur\5_CSTEP_RAIPUR_HDF"
# durg_hdf_root = r"X:\chhattisgarh\cstep_durg\5_CSTEP_DURG_HDF"
# bilaspur_hdf_root = r"X:\chhattisgarh\cstep_bilaspur\5_CSTEP_BILASPUR_HDF"
# mysore_hdf_root = r"W:\SKYLARK_Data\KARNATAKA\KA_MYSORE\5_CSTEP_KA_MYSORE_HDF"

# hdf_filename_preamble = 'MH_Mumbai_HDF_Tile_patched_'
# chdf_filename_preamble = 'TN_CHENNAI_HDF_TILE_'
# ihdf_filename_preamble = 'CSTEP_INDORE_HDF_TILE_'
# jhdf_filename_preamble = 'CSTEP_JABALPUR_HDF_TILE_'
# bhdf_filename_preamble = 'CSTEP_BHOPAL_HDF_TILE_'
# ghdf_filename_preamble = 'CSTEP_GWALIOR_TILE_'
# raipurhdf_filename_preamble = 'CSTEP_RAIPUR_HDF_TILE_'
# durghdf_filename_preamble = 'CSTEP_DURG_HDF_TILE_'
# bilaspurhdf_filename_preamble = 'CSTEP_BILASPUR_HDF_TILE_'
# mysore_filename_preamble = 'CSTEP_MYSORE_HDF_TILE_'

# mumbai_info = CityInfo(utm_zone_code='Q', utm_zone_number=43, data_storage_type='Skylark_HDF',
#                        storage_root=mumbai_hdf_root, filename_preamble=hdf_filename_preamble)
# chennai_info = CityInfo(utm_zone_code='P', utm_zone_number=44, data_storage_type='Skylark_HDF',
#                         storage_root=mumbai_hdf_root, filename_preamble=chdf_filename_preamble)
# indore_info = CityInfo(utm_zone_code='Q', utm_zone_number=43, data_storage_type='Edall_HDF',
#                        storage_root=mumbai_hdf_root, filename_preamble=ihdf_filename_preamble)
# jabalpur_info = CityInfo(utm_zone_code='Q', utm_zone_number=44, data_storage_type='Edall_HDF',
#                          storage_root=jabalpur_hdf_root, filename_preamble=jhdf_filename_preamble)
# bhopal_info = CityInfo(utm_zone_code='Q', utm_zone_number=43, data_storage_type='Edall_HDF',
#                        storage_root=bhopal_hdf_root, filename_preamble=bhdf_filename_preamble)
# gwalior_info = CityInfo(utm_zone_code='R', utm_zone_number=44, data_storage_type='Edall_HDF',
#                         storage_root=gwalior_hdf_root, filename_preamble=ghdf_filename_preamble)
# raipur_info = CityInfo(utm_zone_code='Q', utm_zone_number=44, data_storage_type='Edall_HDF',
#                        storage_root=raipur_hdf_root, filename_preamble=raipurhdf_filename_preamble)
# durg_info = CityInfo(utm_zone_code='Q', utm_zone_number=44, data_storage_type='Edall_HDF',
#                      storage_root=durg_hdf_root, filename_preamble=durghdf_filename_preamble)
# bilaspur_info = CityInfo(utm_zone_code='Q', utm_zone_number=44, data_storage_type='Edall_HDF',
#                          storage_root=bilaspur_hdf_root, filename_preamble=bilaspurhdf_filename_preamble)

# mysore_info = CityInfo(utm_zone_code='P', utm_zone_number=43, data_storage_type='Skylark_HDF',
#                        storage_root=mysore_hdf_root, filename_preamble=mysore_filename_preamble)

# all_cities_info = {'mumbai': mumbai_info, 'chennai': chennai_info, 'Indore': indore_info, 'Jabalpur': jabalpur_info,
#                    'Bhopal': bhopal_info,
#                    'Gwalior': gwalior_info, 'Raipur': raipur_info, 'Durg': durg_info, 'Bilaspur': bilaspur_info,
#                    'Mysore': mysore_info}

def get_city_configurations():
    """
    Creates and returns configurations for different cities including their HDF roots,
    filename preambles, and other metadata.
    
    Returns:
        dict: Dictionary containing CityInfo objects for each city
    """
    # Define HDF root paths
    hdf_roots = {
        'mumbai': r"Z:\EDALL Deliverables\processeddata\INDORE_DELIVERY\7_HDF",
        'chennai': r"X:\TN_CHENNAI\5_CSTEP_TN_CHENNAI_HDF",
        'jabalpur': r"W:\MP\JABALPUR_HDF5",
        'gwalior': r"Z:\EDALL Deliverables\processeddata\GWALIOR_DELIVERY\7_HDF",
        'bhopal': r"Z:\EDALL Deliverables\processeddata\BHOPAL_DELIVERY\7_HDF",
        'raipur': r"W:\chhattisgarh\cstep_raipur\5_CSTEP_RAIPUR_HDF",
        'durg': r"X:\chhattisgarh\cstep_durg\5_CSTEP_DURG_HDF",
        'bilaspur': r"X:\chhattisgarh\cstep_bilaspur\5_CSTEP_BILASPUR_HDF",
        'mysore': r"W:\SKYLARK_Data\KARNATAKA\KA_MYSORE\5_CSTEP_KA_MYSORE_HDF"
    }

    # Define filename preambles
    filename_preambles = {
        'mumbai': 'MH_Mumbai_HDF_Tile_patched_',
        'chennai': 'TN_CHENNAI_HDF_TILE_',
        'indore': 'CSTEP_INDORE_HDF_TILE_',
        'jabalpur': 'CSTEP_JABALPUR_HDF_TILE_',
        'bhopal': 'CSTEP_BHOPAL_HDF_TILE_',
        'gwalior': 'CSTEP_GWALIOR_TILE_',
        'raipur': 'CSTEP_RAIPUR_HDF_TILE_',
        'durg': 'CSTEP_DURG_HDF_TILE_',
        'bilaspur': 'CSTEP_BILASPUR_HDF_TILE_',
        'mysore': 'CSTEP_MYSORE_HDF_TILE_'
    }

    # Define city configurations
    city_configs = {
        'mumbai': {'utm_zone_code': 'Q', 'utm_zone_number': 43, 'data_storage_type': 'Skylark_HDF'},
        'chennai': {'utm_zone_code': 'P', 'utm_zone_number': 44, 'data_storage_type': 'Skylark_HDF'},
        'indore': {'utm_zone_code': 'Q', 'utm_zone_number': 43, 'data_storage_type': 'Edall_HDF'},
        'jabalpur': {'utm_zone_code': 'Q', 'utm_zone_number': 44, 'data_storage_type': 'Edall_HDF'},
        'bhopal': {'utm_zone_code': 'Q', 'utm_zone_number': 43, 'data_storage_type': 'Edall_HDF'},
        'gwalior': {'utm_zone_code': 'R', 'utm_zone_number': 44, 'data_storage_type': 'Edall_HDF'},
        'raipur': {'utm_zone_code': 'Q', 'utm_zone_number': 44, 'data_storage_type': 'Edall_HDF'},
        'durg': {'utm_zone_code': 'Q', 'utm_zone_number': 44, 'data_storage_type': 'Edall_HDF'},
        'bilaspur': {'utm_zone_code': 'Q', 'utm_zone_number': 44, 'data_storage_type': 'Edall_HDF'},
        'mysore': {'utm_zone_code': 'P', 'utm_zone_number': 43, 'data_storage_type': 'Skylark_HDF'}
    }

    # Create CityInfo objects for all cities
    all_cities_information = {}
    for city in city_configs.keys():
        config = city_configs[city]
        all_cities_information[city] = CityInfo(
            utm_zone_code=config['utm_zone_code'],
            utm_zone_number=config['utm_zone_number'],
            data_storage_type=config['data_storage_type'],
            storage_root=hdf_roots.get(city, ''),  # Use lowercase for consistency
            filename_preamble=filename_preambles.get(city, '')
        )
    return all_cities_information


all_cities_info = get_city_configurations()

time_and_day_24h = dl.createTimeDayOfYearNpArrays_24h()
time_and_day_13h = dl.createTimeDayOfYearNpArrays_13h()


class PanelPlacementTCPHandler(ss.StreamRequestHandler):
    """
        Handles incoming TCP requests by decoding the received data, processing it,
        and sending back the result.

        The method receives data from the client, decodes it, and extracts relevant
        information. It then processes the data using city-specific information to
        determine optimal panel placement. The result is serialized to JSON and sent
        back to the client.
    """

    def handle(self):
        data = self.request.recv(self.server.req_len)
        data = data.decode("utf-8", errors="ignore")
        assert isinstance(data, object)
        print('raw data--', data)
        data = data[data.find('{'):len(data) - 1]
        data = data.replace("\\\"", "\"")  # + '}'
        print('replaced data--', data)

        datadict = json.loads(data)
        city_info = all_cities_info[datadict['company']]
        joutp = processBuildingData(datadict, city_info)
        json_data = json.dumps(joutp)
        self.request.sendall(bytes(json_data, "utf-8"))

        print('disposing request', joutp)


def processBuildingData(datadict, city_info, tile_id, building_id, polygon_id, hdf):
    """ Extracts data and attributes for the city in question,
        performs analyses and attempts to place panels optimally,
        and returns the position of the panels and their
        generation Parameters
        ----------
    datadict : dict
        Describes the desired size of the system; the tile, building and polygon
        IDs; and whether the entire polygon is being considered for laying panels
    city_info : CityInfo
        NamedTuple describing key geospatial characteristics for the city in question.

    Returns
        -------
    joutp : dict
        Describes the result of panel placement with the list of panels, total
        energy for each hour as well as the total, and any errors encountered.
    """

    print('starting computation')
    sanction_load = datadict.sanctionLoad
    no_pan = np.round((sanction_load * 1000) / params.PANEL_WATTAGE).astype(int)
    dataFrameDict, error_conds1 = dl.get_data_from_hdfs(city_info, datadict, tile_id, building_id, polygon_id, hdf)

    if city_info.data_storage_type == 'Skylark_HDF':
        time_and_day = time_and_day_24h
    elif city_info.data_storage_type == 'Edall_HDF':
        time_and_day = time_and_day_13h

    if 'targetGen' in datadict:
        target_gen = datadict.targetGen
    else:
        target_gen = None

    if len(dataFrameDict) > 0:
        bundl0 = dl.createAllPolyDataStructsNewLayout(dataFrameDict, time_and_day)
        all_poly_data_structs, all_hourly_gpis, clusters, errs = bundl0
        result = ca2.computeNewPlacement(dataFrameDict, all_poly_data_structs,
                                         all_hourly_gpis, no_pan, target_gen, clusters)
        # result = frle.computeOptimalPlacement(dataFrameDict, time_and_day, no_pan)
        selected_panels, selected_hourlyGen, selected_layouts, error_conds2 = result
        errors = error_conds1 + error_conds2
        joutp = dl.consolidateOutput(errors, selected_panels, selected_hourlyGen, selected_layouts, city_info)
    else:
        errors = error_conds1
        joutp = dl.consolidateOutput(errors)

    print('ended computation')
    return joutp


def get_input_arguments(default_input: dict) -> DInput:
    """
    Retrieve input arguments from the command line or use the provided default input.
    Validate the input using the DInput Pydantic model.
    """
    if len(sys.argv) > 1 and sys.argv[1]:
        try:
            input_data = json.loads(sys.argv[1])
            return DInput(**input_data)
        except (json.JSONDecodeError, ValidationError) as e:
            print(f"Invalid input provided: {e}")
            sys.exit(1)
    else:
        # Use default input and validate it
        return DInput(**default_input)


def write_output_to_file(output_data, output_path):
    """
    Write the processed output to a JSON file.
    """
    with open(output_path, "w") as fd:
        json.dump(output_data, fd)


def profile_function(func, *args, **kwargs):
    """
    Profile a function and save the profiling results to a file.
    """
    profiler = Profile()
    profiler.enable()

    # Execute the function
    result = func(*args, **kwargs)

    profiler.disable()
    stats_stream = io.StringIO()
    stats = pstats.Stats(profiler, stream=stats_stream).sort_stats(pstats.SortKey.CUMULATIVE)
    stats.print_stats()
    stats.dump_stats("../run.prof")

    # Print stats to console for quick debugging
    print(stats_stream.getvalue())

    return result


def main():
    # Default test data

    # Get and validate input arguments
    d_input = get_input_arguments(params.default_input)

    # Retrieve city-specific info
    city_info = all_cities_info[d_input.city]
    hdf_root = city_info.storage_root

    # Process data
    joutp = profile_function(dl.yield_hdfs, city_info, d_input.model_dump(), hdf_root)

    # Write output to file
    output_path = "./outputs/city_output.json"
    write_output_to_file(joutp, output_path)

    # Print JSON output
    print(json.dumps(joutp, indent=4))


if __name__ == '__main__':
    main()
