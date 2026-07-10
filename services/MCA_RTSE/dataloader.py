import datetime
import os
from collections import namedtuple
from itertools import repeat
from os.path import isfile as filexists
from os.path import join as pathjoin

import h5py
import numpy as np
import pandas as pd
import scipy.ndimage as nd
import utm
from natsort import natsorted
from shapely import vectorized as shvec
from shapely.geometry.polygon import Polygon as shPolygon
from shapely.prepared import prep as shPrep
import psycopg2
import datetime
import logging
from decouple import config

# custom imports
import compute_htn as ch
import layout_funcs as lfs
import params

logging.basicConfig(format="{asctime} - {levelname} - {message}", style="{", datefmt="%Y-%m-%d %H:%M",)

TimeAndDayArray = namedtuple('TimeAndDayArray', ['dayArr', 'timeArr'])


class DatabaseManager:
    def __init__(self):
        """Initialize the DatabaseManager with environment variables for connection."""
        self.dbname = config('DB_NAME')
        self.user = config('DB_USER')
        self.host = config('DB_HOST')
        self.password = config('DB_PASS')

    def get_db_connection(self):
        """Establish a connection to the database."""
        try:
            con = psycopg2.connect(
                dbname=self.dbname,
                user=self.user,
                host=self.host,
                password=self.password
            )
            return con
        except psycopg2.Error as e:
            print(f"Error connecting to the database: {e}")
            return None

    def create_tables_for_location(self, location):
        """Create the necessary tables for a given location if they do not exist."""
        try:
            # Get database connection
            with self.get_db_connection() as con:
                if not con:
                    print("Failed to establish database connection.")
                    return

                cur = con.cursor()

                # Create schema if it doesn't exist
                create_schema = """CREATE SCHEMA IF NOT EXISTS mcapanels"""
                cur.execute(create_schema)

                # Create the panel_placement_details table dynamically
                create_table_placement_details = f"""
                    CREATE TABLE IF NOT EXISTS mcapanels.panel_placement_details_{location.lower()} (
                        placement_details_id SERIAL PRIMARY KEY,
                        tile_id int,
                        polygon_id varchar(40),
                        grid_id varchar(2000),
                        created_date timestamp without time zone,
                        updated_date timestamp without time zone,
                        CONSTRAINT panel_placement_unique_{location.lower()} UNIQUE (tile_id, polygon_id, grid_id)
                    )
                """
                cur.execute(create_table_placement_details)

                # Create the polygon table dynamically
                create_table_polygons = f"""
                    CREATE TABLE IF NOT EXISTS mcapanels.{location.lower()}_polygons (
                        polygon_id SERIAL PRIMARY KEY,
                        polygon_code varchar(2000),
                        tile_polygon_id varchar(2000),
                        tile_id int,
                        system_size numeric(10,3),
                        cuf numeric(10,3),
                        created_date timestamp without time zone,
                        updated_date timestamp without time zone,
                        CONSTRAINT polygon_unique_{location.lower()} UNIQUE (polygon_code, tile_polygon_id, tile_id)
                    )
                """
                cur.execute(create_table_polygons)

                # Commit changes to the database
                con.commit()
                print(f"Tables for location '{location}' created successfully.")

        except psycopg2.Error as e:
            print(f"Error while creating tables for location '{location}': {e}")
        except Exception as e:
            print(f"Unexpected error: {e}")


def processAllHdf5FileData(city_info, tile_id):
    '''Testing function to test the ability to gather the needed data for all polygons available in a
    given tile within to a given city. Does not work as of now, need to come up with a definition and
    then implementation of processTPI.

    Parameters
    ----------
    city_info : dict
    tile_id : str, optional
        The ID of the tile to run this over. The default is '210'.

    Returns
    -------
    all_error_conds : list
        All error conditions encountered.

    '''
    all_data = dict()
    all_error_conds = list()

    hdf_root = city_info['storage_root']
    tile_name = city_info['filename_preamble']

    hdf_file = pathjoin(hdf_root, tile_name + str(tile_id) + '.h5')
    print(hdf_file)
    if not filexists(hdf_file):
        error_cond = {'polId': 0, 'tId': tile_id, 'code': 'e002', 'msg': "No insolation file was found for tile"}
        all_error_conds.append(error_cond)

    with h5py.File(hdf_file, 'r') as hdfile:
        # content = hdf.get(tile_building_polygon_id)
        for key in hdfile.keys():
            hdf5content = hdfile.get(key)
            print(key)
            _, error_conds = processTPI(hdf5content, tpi=key)
            # dataFrameDict, error_conds = processTPI(hdf5content, tpi=key)
            # all_data[key] = dataFrameDict
            all_error_conds.append(error_conds)
            pass
    return all_error_conds


def retrieveTPI_Skylark(hdfHandle, polygonId, selectedArea, city_info):
    """
        Retrieve and process TPI Skylark data for a specified polygon.

        This function extracts and processes data from an HDF5 file handle for a given polygon ID.
        It converts UTM coordinates to latitude and longitude, reshapes irradiation data, and
        applies a mask to filter grid cells based on a selected area. The function returns a
        dictionary containing radiation data, a grid mask, and a DataFrame of grid cell information,
        along with the centroid latitude.
    """
    hdf5content = hdfHandle.get(polygonId)

    aspect, slope = hdf5content.attrs['Aspect'], hdf5content.attrs['Slope']
    centroid_lat_m = hdf5content.attrs['Centroid Latitude']
    centroid_lon_m = hdf5content.attrs['Centroid Longitude']
    # These are in UTM projected metres (rectangular coordinates) rather than degrees (spherical coordinates)

    gridids = hdf5content['Coordinates']['grid_ids']
    x_coords = hdf5content['Coordinates']['x_coords']
    y_coords = hdf5content['Coordinates']['y_coords']

    np_gridids = np.array(gridids)

    ghivaluedata = hdf5content['Irradiation_Data']['GHI']['Values']
    assert ghivaluedata.shape[0] == 365 and ghivaluedata.shape[1] == 24
    np_ghivaluedata = np.array(ghivaluedata)
    print(ghivaluedata.shape)
    num_hours = np_ghivaluedata.shape[0] * np_ghivaluedata.shape[1]
    tsh = (num_hours, np_ghivaluedata.shape[2], np_ghivaluedata.shape[3])
    rad_data = np_ghivaluedata.reshape(tsh)

    utm_zcod = city_info.utm_zone_code
    utm_znum = city_info.utm_zone_number

    centroid_lat, centroid_lon = convertMeterToDegree(centroid_lat_m, centroid_lon_m, utm_znum, utm_zcod)
    params.slope = slope
    params.aspect = aspect

    onepolyDict = dict()
    if selectedArea is None:
        sel_np_gridcellIDs = np_gridids

    elif selectedArea is not None:
        fl_gridX = np.array(x_coords).flatten()
        fl_gridY = np.array(y_coords).flatten()

        poly_geom = getCustomGeom(selectedArea)

        mask = getDrawnPolygonMask(poly_geom, fl_gridX, fl_gridY, np_gridids)

        np_gridids1 = np_gridids.copy()
        np_gridids1[~mask] = -1
        sel_np_gridcellIDs = np_gridids1

    gridmask_arr, gridcells_df = getPolygonMask_storedGridIDs(x_coords[0, :],
                                                              y_coords[:, 0],
                                                              sel_np_gridcellIDs)

    onepolyDict['radiation_data'] = rad_data
    onepolyDict['gridMask'] = gridmask_arr
    onepolyDict['gridCellsDf'] = gridcells_df

    return onepolyDict, centroid_lat


def retrieveTPI_Edall(hdfHandle, tId, tbId, tbpId, selectedArea, city_info):
    # hdf5content = hdfHandle.get(pathjoin(tId, tbId, tbpId))
    """
        Retrieve and process radiation data for a specified area from an HDF5 file.

        This function extracts radiation data from an HDF5 file using the provided
        HDF5 handle and identifiers. It converts grid coordinates from meters to
        degrees, applies a mask based on a selected area, and compiles spatial
        Global Horizontal Irradiance (GHI) data. The function returns a dictionary
        containing the processed radiation data, grid mask, and grid cell DataFrame,
        as well as the latitude of the first grid point.
    """
    hdf5content = hdfHandle.get("/".join([tId, tbId, tbpId]))
    grid = hdf5content["Rad_X_Y_Pixel_ID"]
    utm_zcod = city_info.utm_zone_code
    utm_znum = city_info.utm_zone_number

    latt, lonn = convertMeterToDegree(grid['y_cod'], grid['x_cod'],
                                      utm_znum, utm_zcod)
    latitude = latt[0]

    gridId = grid['Pixel Id'].squeeze()
    gridX = grid['x_cod'].squeeze()
    gridY = grid['y_cod'].squeeze()
    data = hdf5content["Rad_Hr_interval"]

    assert data.shape[1] == 4746

    radiationDataDf = pd.DataFrame(data[:, 1:], index=data[:, 0].astype(int)).T

    params.slope = hdf5content["Slope"][()]
    params.aspect = hdf5content["Aspect"][()]

    onepolyDict = dict()

    if selectedArea is None:
        mask = np.ones((gridX.shape[0],), dtype=bool)
    elif selectedArea is not None:
        poly_geom = getCustomGeom(selectedArea)
        mask = getDrawnPolygonMask(poly_geom, gridX, gridY, gridId)

    gridmask_arr, gridcells_df = getPolygonBox(gridX, gridY, gridId, mask)
    nx, ny = gridmask_arr.shape
    ghi_grid = compileSpatialGhi(gridcells_df, gridmask_arr, radiationDataDf)

    onepolyDict['radiation_data'] = ghi_grid
    onepolyDict['gridMask'] = gridmask_arr
    onepolyDict['gridCellsDf'] = gridcells_df

    return onepolyDict, latitude


def getDataFromHdf1(city_info, data_input):
    '''Gathers all the polygon data needed for panel placement for the relevant city for either Skylark
    or Edall HDF data

    Parameters
    ----------
    city_info : dict
        Key geospatial and HDF-file-location info for the city.
    data_input : dict
        Selected tile, building, polygon(s) and optionally co-ordinates of custom polygon drawn within.

    Returns
    -------
    dataFrameDict : dict
        Data structure holding all needed data about the polygons.
    error_conds : list
        Collection of all errors encountered during the data gathering process.

    '''
    error_conds = []
    dataFrameDict = {}
    if data_input['typeOfComputation'] == 'op':
        polygons = data_input['polygonDetails']
    elif data_input['typeOfComputation'] == 'cu':
        polygons = data_input['costomPolygons']

    hdf_root = city_info.storage_root
    tile_name = city_info.filename_preamble

    for polygon in polygons:
        tile_id, building_id, polygon_id = str(polygon['tileId']), polygon['buildingId'], polygon['polygonId']
        tbId = "_".join((str(tile_id), str(building_id)))
        tbpId = "_".join((str(tile_id), str(building_id), str(polygon_id)))
        print(tbpId)
        if city_info.data_storage_type == 'Skylark_HDF':
            hdf_file = pathjoin(hdf_root, tile_name + str(tile_id) + '.h5')
        elif city_info.data_storage_type == 'Edall_HDF':
            hdf_file = pathjoin(hdf_root, tile_name + str(tile_id) + '.hdf5')

        print(hdf_file)
        if not filexists(hdf_file):
            error_cond = {'polId': polygon_id, 'tId': tile_id, 'code': 'e002',
                          'msg': "No insolation file was found for tile"}
            error_conds.append(error_cond)
            continue

        with h5py.File(hdf_file, 'r') as hdf:
            if data_input['typeOfComputation'] == 'op':
                selectedArea = None
            elif data_input['typeOfComputation'] == 'cu':
                selectedArea = polygon['selectedPolygon']

            if city_info.data_storage_type == 'Skylark_HDF':
                onepolyDict, centroid_lat = retrieveTPI_Skylark(hdf, tbpId, selectedArea, city_info)
            elif city_info.data_storage_type == 'Edall_HDF':
                onepolyDict, centroid_lat = retrieveTPI_Edall(hdf, tile_id, tbId, tbpId, selectedArea, city_info)

            dataFrameDict[tbpId] = {'tileId': tile_id, 'buildingId': building_id,
                                    'polygonId': polygon_id, 'polygonArrays': onepolyDict,
                                    'slope': params.slope, 'aspect': params.aspect,
                                    'latitude': centroid_lat,
                                    }
    return dataFrameDict, error_conds


def get_data_from_hdfs(city_info, data_input, tile_id, building_id, polygon_id, hdf):
    """ Retrieve and process data from HDF5 files for specified city and polygon information.

        This function accesses HDF5 files to extract and process data based on the provided
        city information, data input type, and identifiers for tiles, buildings, and polygons.
        It handles different data storage types ('Skylark_HDF' and 'Edall_HDF') and computes
        the necessary spatial data, including radiation data and geographic coordinates.
        The function returns a dictionary containing the processed data and any error conditions
        encountered during the data retrieval process.
    """
    error_conds = []
    dataFrameDict = {}

    if data_input.typeOfComputation == 'cu':
        polygons = data_input.costomPolygons

    tbId = "_".join((str(tile_id), str(building_id)))
    tbpId = "_".join((str(tile_id), str(building_id), str(polygon_id)))
    tile_building_polygon_id = " ".join((str(tile_id), str(building_id), str(polygon_id)))

    hdf_file = hdf

    print(hdf_file)
    if not filexists(hdf_file):
        error_cond = {'polId': polygon_id, 'tId': tile_id, 'code': 'e002',
                      'msg': "No insolation file was found for tile"}
        error_conds.append(error_cond)

    with h5py.File(hdf_file, 'r') as hdf:
        if data_input.typeOfComputation == 'op':
            selectedArea = None
        elif data_input.typeOfComputation == 'cu':
            selectedArea = polygons['selectedPolygon']

        if city_info.data_storage_type == 'Skylark_HDF':
            onepolyDict, centroid_lat = retrieveTPI_Skylark(hdf, polygon_id, selectedArea, city_info)
        elif city_info.data_storage_type == 'Edall_HDF':
            onepolyDict, centroid_lat = retrieveTPI_Edall(hdf, tile_id, building_id, polygon_id, selectedArea,
                                                          city_info)

        dataFrameDict[tile_building_polygon_id] = {'tileId': tile_id, 'buildingId': building_id,
                                                   'polygonId': polygon_id, 'polygonArrays': onepolyDict,
                                                   'slope': params.slope, 'aspect': params.aspect,
                                                   'latitude': centroid_lat,
                                                   }
    return dataFrameDict, error_conds


def createAllPolyDataStructsNewLayout(dataFrameDict, time_and_day):
    '''Creates all necessary data structures for each polygon to be able to run panel placement

    Parameters
    ----------
    dataFrameDict : dict
    time_and_day : namedTuple

    Returns
    -------
    all_poly_data_structs : dict
        Collection of all poly_data_structs indexed by their ID.
    all_hourly_gpis : dict
        Collection of panel generation for each possible position.
    clusters_nuclei_df : pandas.DataFrame
        Collection of identified cluster nuclei.
    error_conds : list
        List of errors encountered in the application.

    '''
    global clusters_nuclei_df
    block_panel_shapes = set(params.ALLOWED_BLOCK_PANEL_SHAPES['newclus'] + \
                             params.ALLOWED_BLOCK_PANEL_SHAPES['diffrow'] + \
                             params.ALLOWED_BLOCK_PANEL_SHAPES['samerow'])

    all_poly_data_structs = {}
    all_hourly_gpis, error_conds, all_clusters = {}, [], []

    for tile_polygon_id, onepoly in dataFrameDict.items():
        if not onepoly['polygonArrays']:
            # if it's a empty polygon break
            error_cond = {'tile_polygon_id': tile_polygon_id, 'code': 'e004',
                          'msg': "polygonArrays or gridids is empty"}
            error_conds.append(error_cond)
            break

        polygon_arrays = onepoly['polygonArrays']
        gridmask_arr, gridcells_df = polygon_arrays['gridMask'], polygon_arrays['gridCellsDf']

        poly_shape = gridmask_arr.shape
        poly_nrows, poly_ncols = poly_shape

        latitude = onepoly['latitude']
        roof_slope = onepoly['slope']
        roof_azimuth = onepoly['aspect']

        buil_len = poly_nrows
        if buil_len >= params.PANEL_DIMEN[0] / params.GRIDCELL_SIZE:
            panel_orientation = params.PORTRAIT
        else:
            panel_orientation = params.LANDSCAPE

        bundl1 = lfs.getPanelAngleParams(roof_slope, latitude, panel_orientation, roof_azimuth)
        panel_shape, tilt_panel, skip_shape, ori_roof = bundl1

        if poly_nrows < panel_shape[0] or poly_ncols < panel_shape[1]:
            error_cond = {'polId': onepoly['polygonId'], 'tId': onepoly['tileId'], 'code': 'e003',
                          'msg': "No suitable location exists in polygon for panel"}
            error_conds.append(error_cond)
            continue

        radiation_array = polygon_arrays['radiation_data']
        ghi_grid, panelwise_min_ghi_grid = filterAllValidGhi(gridmask_arr, radiation_array, panel_shape)
        total_ghi_grid = ghi_grid.sum(axis=0)

        exclayout1, panel_layout = np.zeros(poly_shape), np.zeros(poly_shape)
        exclayout1[total_ghi_grid == 0] = -1

        panel_valid_mask = lfs.getValidPosits_EPS(exclayout1, panel_layout, panel_shape, (1, 1))

        panel_gpi = ch.calculateGpiPoly(panelwise_min_ghi_grid, time_and_day, latitude,
                                        tilt_panel, ori_roof, exclayout1)
        total_panel_gpi = panel_gpi.sum(axis=0)
        total_panel_gpi[~panel_valid_mask] = 0

        block_valid_masks, sgpif_block_panel_shapes = {}, {}

        # lfs.updateClustersAndBlockValidMasks(all_poly_data_structs)
        mhm = params.MOUNT_HEIGHTS_MULTS
        for block_panel_shape in block_panel_shapes:
            block_sum_gpi = lfs.blockSumGPI(total_panel_gpi, panel_shape, block_panel_shape, mhm)
            sgpif_block_panel_shapes[block_panel_shape] = block_sum_gpi

            if block_panel_shape in params.ALLOWED_BLOCK_PANEL_SHAPES['newclus']:
                cluster_nuclei = lfs.markClustersAtLocalMinPanelPeaks2(block_sum_gpi,
                                                                       block_panel_shape)
                cluster_nuclei['polygon'] = tile_polygon_id
                cluster_nuclei['blockPanelShape'] = list(repeat(block_panel_shape, times=len(cluster_nuclei)))

                all_clusters.append(cluster_nuclei)

        mesh = np.meshgrid(range(poly_nrows), range(poly_ncols))
        mesh1 = np.stack(mesh, axis=2)
        mesh2 = np.swapaxes(mesh1, 0, 2)

        OnePolygon = params.Polygon(gridMask=gridmask_arr, totalGpiGrid=total_panel_gpi, panelShape=panel_shape,
                                    skipShape=skip_shape, mesh=mesh2, gridCellsDF=gridcells_df,
                                    blockGPISums=sgpif_block_panel_shapes, panelLayout=panel_layout,
                                    excLayout1=exclayout1, blockValidMasks=block_valid_masks, )

        all_poly_data_structs[tile_polygon_id] = OnePolygon
        all_hourly_gpis[tile_polygon_id] = panel_gpi

    if all_clusters:
        clusters_nuclei_df = pd.concat(all_clusters, axis=0).sort_values(by='total_energy',
                                                                         ascending=False).reset_index()
    else:
        clusters_nuclei_df = pd.DataFrame()
    # visualize the clusters
    return all_poly_data_structs, all_hourly_gpis, clusters_nuclei_df, error_conds


def compileSpatialGhi(gridcells_df, gridmask_arr, ghi_df):
    """Returns layout of GHI at every timestep at every valid location"""
    num_hours = ghi_df.shape[0]

    rowidxs = gridcells_df.index.get_level_values('rowidx').values
    colidxs = gridcells_df.index.get_level_values('colidx').values

    gridname_arr = np.zeros(gridmask_arr.shape, dtype=int)
    gridnames = gridcells_df['gridcellIDs'].values
    gridname_arr[rowidxs, colidxs] = gridnames
    flat_gridname_arr = gridname_arr.reshape((-1))

    ghi_gridcellwise = ghi_df.reindex(columns=flat_gridname_arr).values
    tsh = (num_hours, gridname_arr.shape[0], gridname_arr.shape[1])
    ghi_grid = ghi_gridcellwise.reshape(tsh)
    ghi_grid[np.isnan(ghi_grid)] = 0

    return ghi_grid


def filterAllValidGhi(gridmask_arr, ghi_grid, panel_shape):
    """Returns grid-cell-wise map of GHI at every timestep at every valid location as well as the minimum
    across all the cells for a single panel (identified by its south-west corner) in a given polygon.

    Parameters
    ----------
    gridmask_arr : numpy.array
    radiation_array : numpy.array
    panel_shape : tuple

    Returns
    -------
    ghi_grid : numpy.array
        Array of the same size as gridmask_arr.
    panelwise_min_ghi_grid : numpy.array
        Array of the same size as gridmask_arr.

    """

    ghi_grid[np.isnan(ghi_grid)] = 0
    rr, cc = np.nonzero(gridmask_arr == False)
    ghi_grid[:, rr, cc] = 0

    # Core functionality below - above removes invalid radiation data...
    org_x = +1 * (panel_shape[0] // 2) - 1
    org_y = -1 * (panel_shape[1] // 2)
    rowwise_min_ghi_grid = nd.minimum_filter1d(ghi_grid, size=panel_shape[0], axis=1, mode='constant', cval=0,
                                               origin=org_x)
    panelwise_min_ghi_grid = nd.minimum_filter1d(rowwise_min_ghi_grid, size=panel_shape[1], axis=2, mode='constant',
                                                 cval=0, origin=org_y)

    return ghi_grid, panelwise_min_ghi_grid


def convertMeterToDegree(lat, lon, zone_num, zone_code):
    return utm.to_latlon(lon, lat, zone_num, zone_code)


def createTimeDayOfYearNpArrays_24h():
    """Generate numpy arrays representing the day of the year and hour of the day.

    This function creates two numpy arrays: one for the day of the year and another
    for the hour of the day, assuming a non-leap year with 365 days. Each day is 
    divided into 24 hours. The arrays are encapsulated in a named tuple 
    'TimeAndDayArray' with fields 'dayArr' and 'timeArr'."""
    hours_per_day = 24
    total_hours_per_year = 365 * hours_per_day
    hourIndexArr = np.arange(1, total_hours_per_year + 1)

    time = ((hourIndexArr - 1) % hours_per_day) + 1
    day = np.ceil(hourIndexArr / hours_per_day).astype(int)

    timeAndDay = TimeAndDayArray(day, time)
    return timeAndDay


def createTimeDayOfYearNpArrays_13h():
    """Create numpy arrays representing the day of the year and time of day for a 13-hour day schedule.

    This function generates two numpy arrays: one for the day of the year and another for the time of day,
    assuming each day consists of 13 hours starting at 6 AM. It returns a named tuple containing these arrays.
    """
    hours_per_day = 13
    total_hours_per_year = 365 * hours_per_day
    hourIndexArr = np.arange(1, total_hours_per_year + 1)

    time = ((hourIndexArr - 1) % hours_per_day) + 6
    day = np.ceil(hourIndexArr / hours_per_day).astype(int)

    timeAndDay = TimeAndDayArray(day, time)
    return timeAndDay


def getPolygonMask_storedGridIDs(xcoords_vec, ycoords_vec, gridcells_box):
    """ 
    Generate a boolean mask and a DataFrame of grid cell information for a given polygon.

    This function identifies grid cells within a specified bounding box and returns a boolean
    mask indicating the presence of these cells, along with a DataFrame containing the grid
    cell indices, coordinates,
    """
    gr, gc = (gridcells_box >= 0).nonzero()

    cells_df = pd.DataFrame()
    cells_df['rowidx'] = gr
    cells_df['colidx'] = gc
    cells_df['lat'] = ycoords_vec[gr]
    cells_df['long'] = xcoords_vec[gc]
    cells_df['gridcellIDs'] = gridcells_box[gr, gc]
    cells_df = cells_df.set_index(['rowidx', 'colidx'])

    box = np.zeros(gridcells_box.shape, dtype=bool)
    box[gr, gc] = True

    return box, cells_df


def getPolygonBox(xcoords_vec, ycoords_vec, gridcell_IDs, mask):
    """ Calculate a grid cell box and DataFrame for a polygon defined by coordinate vectors. """
    miny, maxy = ycoords_vec.min(), ycoords_vec.max()
    minx, maxx = xcoords_vec.min(), xcoords_vec.max()

    num_cols = int((maxx - minx) / params.GRIDCELL_SIZE)
    num_rows = int((maxy - miny) / params.GRIDCELL_SIZE)

    gridcells_box = np.zeros((num_rows + 1, num_cols + 1), dtype=bool)

    rowidx = ((ycoords_vec - miny) / params.GRIDCELL_SIZE).round(0).astype(int)
    colidx = ((xcoords_vec - minx) / params.GRIDCELL_SIZE).round(0).astype(int)

    gridcells_box[rowidx[mask], colidx[mask]] = True

    cells_df = pd.DataFrame()
    cells_df['long'] = xcoords_vec[mask]
    cells_df['lat'] = ycoords_vec[mask]
    cells_df['rowidx'] = rowidx[mask]
    cells_df['colidx'] = colidx[mask]
    cells_df['gridcellIDs'] = gridcell_IDs[mask]
    cells_df = cells_df.set_index(['rowidx', 'colidx'])

    return gridcells_box, cells_df


def getCustomGeom(listPoint):
    """ Converts a list of latitude-longitude strings into a Shapely Polygon object.

    Each string in the input list is expected to be in the format 'lat-lon'.
    The function parses these strings, converts the latitude and longitude
    values to UTM coordinates, and constructs a polygon from these points.
    """
    latList, lonList = [], []
    for point in listPoint:
        gridLatLong = point.split('-')
        lonList.append(float(gridLatLong[1]))
        latList.append(float(gridLatLong[0]))
    x_m, y_m, zone_num, zone_letter = utm.from_latlon(np.array(latList), np.array(lonList))
    polygon_geom = shPolygon(zip(x_m, y_m))
    return polygon_geom


def getDrawnPolygonMask(polygonObj, xcoords_flat, ycoords_flat, gridids):
    """
        Generate a mask indicating which grid cells are contained within a drawn polygon.

        This function prepares a polygon object and checks which grid cells, identified by their
        flat x and y coordinates, are contained within the polygon. It returns a boolean mask
        indicating the presence of grid cells within the polygon.
    """
    gridids_flat = gridids.flatten()
    prepPoly = shPrep(polygonObj)
    containedMask = shvec.contains(prepPoly, xcoords_flat, ycoords_flat)
    containedGridIDs = gridids_flat[containedMask]
    roofPolyValidMask = np.isin(gridids, containedGridIDs)
    return roofPolyValidMask


def consolidateOutput(error_conds, selected_panels_polygons=None,
                      all_hourly_gen_df=None, all_layout_list_df=None, city_info=None):
    """Gathers panel location and energy information from multiple data collections, along with any errors
    and puts them exactly as needed by web application.

    Parameters
    ----------
    error_conds : list
        Errors encountered during panel placement.
    selected_panels_polygons : pandas.DataFrame, optional
        All panels and their respective polygons. The default is None.
    all_hourly_gen_df : pandas.DataFrame, optional
        Energy generation from each panel for each hour. The default is None.
    all_layout_list_df : pandas.DataFrame, optional
        Grid cells (identified lat-long string) occupied by each panel. The default is None.

    Returns
    -------
    response : dict
        Output dict consisting of panel locations, panel energies, and total energy.

    """
    er_resp = {}
    response = {}
    if len(error_conds) == 0:
        er_resp['isError'] = False
        er_resp['details'] = []
    else:
        er_resp['isError'] = True
        er_resp['details'] = error_conds
    response['errorStatus'] = er_resp

    if selected_panels_polygons is not None and all_hourly_gen_df is not None and all_layout_list_df is not None:
        optimalplacement = []
        energy_gen = all_hourly_gen_df.sum(axis=1)
        total_energy_gen = energy_gen.sum()

        for panelObj in selected_panels_polygons.itertuples():
            idx = panelObj.Index
            tile_polygon_id = panelObj.polyUid
            tile_id = tile_polygon_id.split(' ')[0]
            building_id = tile_polygon_id.split(' ')[1]
            polygon_id = tile_polygon_id.split(' ')[2]
            cuf = panelObj.Cuf
            grid_details = []
            mask = (all_layout_list_df['uPanelid'] == idx)
            panelGridsDf = all_layout_list_df[mask]
            for grid_individual in panelGridsDf.itertuples():
                grid_details_entity = {'grids_lat': grid_individual.lat, 'grids_long': grid_individual.long}
                grid_details.append(grid_details_entity)

            panel_details = {
                'tileId': tile_id,
                'polygonId': polygon_id,
                'buildingId': building_id,
                'gridDetails': grid_details,
                'cuf': cuf
            }

            optimalplacement.append(panel_details)

        response['optimalPlacement'] = optimalplacement
        response['energy'] = round(total_energy_gen, 2)
        response['energyGenerationPerPanelHour'] = energy_gen.round(3).to_list()
        print("Started insertion to db, please wait...")
        from params import default_input
        into_db(response, optimalplacement, len(selected_panels_polygons), default_input['city'])
        print("insertion complete")
    return response


def into_db(response, optimalplacement, panels_with_max_cuf, location):
    """
        Insert data into the database for a given location.

        This function calculates the system size based on the number of panels with maximum CUF
        and inserts data into the database tables specific to the given location. It creates the
        necessary tables if they do not exist and inserts records into the 'polygons' and 
        'panel_placement_details' tables. The function ensures that the system size is greater 
        than 0.7 before performing the insert operations.
    """
    date = datetime.datetime.now()
    response['system_size'] = round(((panels_with_max_cuf * (params.PANEL_WATTAGE * 0.001)) / 1), 3)
    loc = location
    DatabaseManager().create_tables_for_location(location)
    try:
        con = DatabaseManager().get_db_connection()
        if response['system_size'] > 0.7:
            with con.cursor() as cur:
                # Dynamically inserting the table name using f-string
                query1 = (
                    f"INSERT INTO mcapanels.{loc}_polygons "
                    "(polygon_code, tile_id, system_size, cuf, created_date, updated_date) "
                    "VALUES (%s, %s, %s, %s, %s, %s)"
                )
                cur.execute(
                    query1,
                    (optimalplacement[1]['polygonId'], optimalplacement[1]['tileId'],
                     response['system_size'], optimalplacement[1]['cuf'], date, date)
                )

                for x in range(panels_with_max_cuf):
                    lat_long_db = [
                        str(response['optimalPlacement'][x]['gridDetails'][c]['grids_lat']) + "-" +
                        str(response['optimalPlacement'][x]['gridDetails'][c]['grids_long'])
                        for c in range(len(response['optimalPlacement'][x]['gridDetails']))
                    ]

                    # Dynamically inserting the table name using f-string for panel placement details
                    query2 = (
                        f"INSERT INTO mcapanels.panel_placement_details_{loc} "
                        "(tile_id, polygon_id, grid_id, created_date, updated_date) "
                        "VALUES (%s, %s, %s, %s, %s)"
                    )
                    cur.execute(
                        query2,
                        (optimalplacement[1]['tileId'], optimalplacement[1]['polygonId'],
                         lat_long_db, date, date)
                    )
            con.commit()
    finally:
        con.close()
    print('Inserted into DB successfully')


def get_hdf_files(hdf_root, extensions):
    """Retrieve HDF files with given extensions from the specified root directory."""
    hdf_dir = natsorted(os.listdir(hdf_root))
    return [file for file in hdf_dir if file.endswith(extensions)]


def process_hdf_file(file_path, city_info, d_input, results):
    """Process an individual HDF file and extract results."""
    import mainrunner
    try:
        with h5py.File(file_path, 'r') as tile:
            # Choose the structure to iterate based on data storage type
            if city_info.data_storage_type == 'Skylark_HDF':
                for tid in tile.keys():
                    hdf5content = tile[tid]
                    print(f"Processing {tid}: {hdf5content}")
                    tile_id = tid.split('_')[0]
                    building_id = "_".join(tid.split('_')[: 2])
                    polygon_id = tid
                    results.append(
                        mainrunner.processBuildingData(
                            d_input, city_info, tile_id, building_id, polygon_id, file_path
                        )
                    )
            else:  # Edall_HDF case
                for tile_id in tile.keys():
                    for building_id in tile[tile_id].keys():
                        for polygon_id in tile[tile_id][building_id].keys():
                            hdf5content = tile[tile_id][building_id][polygon_id]
                            print(f"Processing {tile_id}/{building_id}/{polygon_id}: {hdf5content}")
                            results.append(
                                mainrunner.processBuildingData(
                                    d_input, city_info, tile_id, building_id, polygon_id, file_path
                                )
                            )
    except Exception as e:
        print(f"Error reading HDF5 file {file_path}: {e}")


def yield_hdfs(city_info, data_input, hdf_root):
    """
        Process HDF files from the specified root directory and yield results based on
        the provided city information and data input. Determines the appropriate file
        extensions and polygons to process, and utilizes the processBuildingData function
        to extract and return results from each HDF file.
    """
    from mainrunner import get_input_arguments

    # Prepare input for processBuildingData
    d_input = get_input_arguments(params.default_input)

    # Determine which polygons to use
    polygons = (
        hdf_root if data_input['typeOfComputation'] == 'op' else data_input.get('customPolygons', [])
    )

    # Get the correct HDF file extensions
    extensions = ('.h5',) if city_info.data_storage_type == 'Skylark_HDF' else ('.hdf5',)
    hdf_files = get_hdf_files(hdf_root, extensions)

    # Process the HDF files
    if hdf_files:
        results = []
        for file in hdf_files:
            file_path = pathjoin(hdf_root, file)
            process_hdf_file(file_path, city_info, d_input, results)
        return results  # Return all results after processing
    else:
        print("No HDF files found.")
        return None


# import datetime
# from typing import Dict, List, Any
# import psycopg2
# from psycopg2.extras import execute_batch
# import logging
# from contextlib import contextmanager
#
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)
#
#
# def prepare_panel_data(response: Dict, optimal_placement: Dict,
#                        panels_count: int, date: datetime.datetime) -> List[tuple]:
#     """Prepare batch data for panel placement details"""
#     panel_data = []
#     for x in range(panels_count):
#         lat_long_db = [
#             f"{grid['grids_lat']}-{grid['grids_long']}"
#             for grid in response['optimalPlacement'][x]['gridDetails']
#         ]
#
#         panel_data.append((
#             optimal_placement[1]['tileId'],
#             optimal_placement[1]['polygonId'],
#             lat_long_db,
#             date,
#             date
#         ))
#     return panel_data
#
#
# def prepare_polygon_data(response: Dict, optimal_placement: Dict,
#                          date: datetime.datetime) -> tuple:
#     """Prepare data for polygon insertion"""
#     return (
#         optimal_placement[1]['polygonId'],
#         optimal_placement[1]['tileId'],
#         response['system_size'],
#         optimal_placement[1]['cuf'],
#         date,
#         date
#     )
#
#
# class DatabaseInserter:
#     def __init__(self, batch_size: int = 10000):
#         self.batch_size = batch_size
#
#     @contextmanager
#     def get_connection(self):
#         """Context manager for database connections"""
#         conn = DatabaseManager().get_db_connection()
#         try:
#             yield conn
#         finally:
#             conn.close()
#
#
# def into_db(response: Dict, optimal_placement: Dict,
#             panels_with_max_cuf: int, location: str) -> None:
#     """
#         Optimized database insertion for large datasets.
#
#         Args:
#             response: Dictionary containing response data
#             optimal_placement: Dictionary containing placement data
#             panels_with_max_cuf: Number of panels with maximum CUF
#             location: Location identifier for table names
#         """
#     try:
#         # Calculate system size
#         response['system_size'] = round(
#             panels_with_max_cuf * (params.PANEL_WATTAGE * 0.001), 3
#         )
#
#         if response['system_size'] <= 0.7:
#             logger.warning(f"System size {response['system_size']} is too small, skipping insertion")
#             return
#
#         date = datetime.datetime.now()
#         DatabaseManager().create_tables_for_location(location)
#
#         with DatabaseInserter().get_connection() as conn:
#             with conn.cursor() as cur:
#                 # Insert polygon data
#                 polygon_query = f"""
#                         INSERT INTO mcapanels.{location}_polygons
#                         (polygon_code, tile_id, system_size, cuf, created_date, updated_date)
#                         VALUES (%s, %s, %s, %s, %s, %s)
#                     """
#                 polygon_data = prepare_polygon_data(response, optimal_placement, date)
#                 cur.execute(polygon_query, polygon_data)
#
#                 # Batch insert panel placement details
#                 panel_query = f"""
#                         INSERT INTO mcapanels.panel_placement_details_{location}
#                         (tile_id, polygon_id, grid_id, created_date, updated_date)
#                         VALUES (%s, %s, %s, %s, %s)
#                     """
#                 panel_data = prepare_panel_data(
#                     response, optimal_placement, panels_with_max_cuf, date
#                 )
#
#                 execute_batch(cur, panel_query, panel_data, page_size=DatabaseInserter().batch_size)
#
#             conn.commit()
#
#         logger.info(f"Successfully inserted panels_with_max_cuf {panels_with_max_cuf} records for location {location}")
#
#     except Exception as e:
#         logger.error(f"Error during database insertion: {str(e)}")
#         raise
