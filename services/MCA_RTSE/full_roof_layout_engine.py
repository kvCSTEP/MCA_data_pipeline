from collections import namedtuple

import numpy as np
import pandas as pd

# local libraries
import compute_htn as ch
import layout_funcs as lfs
import params  # , vlibs


# Lays out panels all over the roof, sorts by power generation and then picks panels one by one with
# the highest generation.

def createDayOfYearNpArray():
    """
    Creates a named tuple containing arrays for the day of the year and the time of day.

    This function calculates the day of the year and the time of day for each hour
    in a non-leap year (365 days). It returns a named tuple with two arrays: one for
    the day of the year and another for the time of day, starting from 6 AM.

    """
    total_hours_per_year = 365 * 24
    hours_per_day = 24
    hourIndexArr = np.arange(1, total_hours_per_year + 1)

    time = (hourIndexArr % hours_per_day) + 6
    day = np.ceil(hourIndexArr / hours_per_day).astype(int)

    TimeAndDayArray = namedtuple('TimeAndDayArray', ['dayArr', 'timeArr'])
    timeAndDayArrayObj = TimeAndDayArray(day, time)
    return timeAndDayArrayObj


def createDayOfYearNpArrayB():
    """
    Creates a dictionary containing arrays for the day of the year and the time of day.

    This function calculates the day of the year and the time of day for each hour
    in a non-leap year (365 days). It returns a dictionary with two NumPy arrays:
    'dayArr' for the day of the year and 'timeArr' for the time of day, starting
    from 6 AM.
    """
    total_hours_per_year = 365 * 24
    hours_per_day = 24
    hourIndexArr = np.arange(1, total_hours_per_year + 1)

    time = hourIndexArr % hours_per_day + 6
    day = np.ceil(hourIndexArr / hours_per_day).astype(int)

    timeAndDayArrays = {'dayArr': day, 'timeArr': time}
    return timeAndDayArrays


def getBasePanels(polygon_mask, panel_shape, gap_rows):
    """
    Generate a base panel layout grid for a given polygon mask.

    This function creates a grid layout of panels based on the provided polygon mask,
    panel shape, and the number of gap rows. It calculates the number of panels that
    can fit within the polygon mask and returns the panel grid layout along with the
    difference in shape between the panel grid layout and the polygon mask.
    """
    panel_proto = np.ones(panel_shape, dtype=int)
    gap_proto = np.zeros((gap_rows, panel_shape[1]), dtype=int)
    panel_gap_proto = np.vstack((gap_proto, panel_proto))

    panel_rows = int(np.ceil(polygon_mask.shape[0] / panel_gap_proto.shape[0]))
    panel_cols = int(np.ceil(polygon_mask.shape[1] / panel_gap_proto.shape[1]))

    panel_layout = np.arange(1, panel_rows * panel_cols + 1).reshape((panel_rows, panel_cols))
    panel_grid_layout = np.kron(panel_layout, panel_gap_proto)

    diff_shape_rows = panel_grid_layout.shape[0] - polygon_mask.shape[0]
    diff_shape_cols = panel_grid_layout.shape[1] - polygon_mask.shape[1]
    diff_shape = (diff_shape_rows, diff_shape_cols)

    return panel_grid_layout, diff_shape


def getConfigPanels(base_panel_grid_layout, skip_shape):
    """
    Generate a list of panel configuration layouts by rolling the base panel grid layout.

    This function takes a base panel grid layout and generates multiple configurations
    by rolling the grid layout across specified rows and columns. Each configuration
    is created by shifting the grid layout by a certain number of rows and columns,
    as defined by the `skip_shape` parameter.
    """
    skip_rows, skip_cols = skip_shape
    config_layouts = []

    for skip_row in np.arange(skip_rows):
        for skip_col in np.arange(skip_cols):
            config_layouts.append(np.roll(base_panel_grid_layout, (skip_row, skip_col), (0, 1)))
    return config_layouts


def getValidConfigPanels(config_layouts, polygon_mask, panel_shape, cells):
    """
    Determine valid configuration panels from a list of configuration layouts.

    This function iterates over a list of configuration layouts, applying a polygon mask
    to each layout to identify valid panel configurations based on the specified panel shape.
    It returns indices and layouts of valid configurations.
    """
    panel_num_cells = panel_shape[0] * panel_shape[1]

    config_panel_idxs = []
    config_panel_layouts = []

    for config_layout in config_layouts:
        masked_config_layout, layout_config_cells_df = getValidConfigPanel(config_layout, polygon_mask,
                                                                           panel_num_cells, cells)
        if masked_config_layout is not None and layout_config_cells_df is not None:
            config_panel_idxs.append(layout_config_cells_df)
            config_panel_layouts.append(masked_config_layout)

    return config_panel_idxs, config_panel_layouts


def getValidConfigPanel(config_layout, polygon_mask, panel_num_cells, cells):
    """
    Process a configuration layout to identify valid panels within a polygon mask.

    This function clips the given configuration layout to the size of the polygon mask
    and applies the mask to filter out invalid areas. It calculates the number of cells
    in each panel and eliminates panels that do not meet the required number of cells.
    The function returns a masked configuration layout and a DataFrame containing
    the indices and panel IDs of valid panels.

    """
    config_layout_clip = config_layout[0:polygon_mask.shape[0], 0:polygon_mask.shape[1]]
    masked_config_layout = config_layout_clip * polygon_mask
    counts = np.bincount(masked_config_layout.flatten())

    if counts.shape[0] <= 1:
        return None, None

    panelgridcounts = counts[1:]
    elim_panel_nums = np.nonzero(panelgridcounts < panel_num_cells)[0] + 1

    if elim_panel_nums.shape[0] == panelgridcounts.shape[0]:
        return None, None

    masked_config_layout[np.isin(masked_config_layout, elim_panel_nums)] = 0

    valid_panel_axiswise_idxs = np.nonzero(masked_config_layout)
    valid_panel_arr_idxs = np.transpose(valid_panel_axiswise_idxs)
    masked_config_layout_vals = masked_config_layout[valid_panel_axiswise_idxs]
    layout_config_cells = np.c_[valid_panel_arr_idxs, masked_config_layout_vals]

    layout_config_cells_df = pd.DataFrame(layout_config_cells, columns=['rowidx', 'colidx', 'panelid'], dtype=int)

    layout_config_cells_df = layout_config_cells_df.join(cells, on=['rowidx', 'colidx'])
    layout_config_cells_df = layout_config_cells_df.rename(columns={0: "gridid"})
    return masked_config_layout, layout_config_cells_df


def getAllPanelsGhi(dataframe, cells_df, panel_shape):
    """
    Calculate the minimum insolation values for each panel.

    This function processes the given dataframes to determine the minimum
    insolation values for each panel based on their grid cell IDs.

    """
    sr_cells_df = cells_df.set_index('gridcellIDs')
    panel_min_insol_values = dataframe.T.groupby(by=sr_cells_df['panelid']).min()
    panel_min_insol_values.index = panel_min_insol_values.index.astype(int)
    return panel_min_insol_values


# @profile
def getAllPanelsGhiNp(dataframe, sr_cells_df, panel_shape):
    """
    Calculate the minimum insolation values for each panel over a given time period.

    This function reshapes the insolation data from a 2D DataFrame into a 3D array
    based on the number of hours and the panel shape. It then computes the minimum
    insolation values for each panel across all grid cells
    """
    panel_num_cells = panel_shape[0] * panel_shape[1]
    panel_insol_values = dataframe.loc[:, sr_cells_df.index]
    num_hours = dataframe.shape[0]
    panel_insol_values_3darr = panel_insol_values.values.reshape((num_hours, -1, panel_num_cells))
    panel_min_insol_values = panel_insol_values_3darr.min(axis=2)
    return panel_min_insol_values


def getAllConfigCufs(dataframe, validConfigDfs, panel_shape, timeAndDayArr, latitude, tilt_roof, orientation_roof):
    """
    Calculate the Capacity Utilization Factor (CUF) and hourly generation for each valid panel configuration.

    This function iterates over a list of valid panel configurations, computes the minimum insolation
    values for each panel, and calculates the hourly generation and CUF for each configuration.
    The results include the total CUF for each configuration, the hourly generation data, and
    panel-specific generation and CUF values.

    """
    hourlyGen_results = []
    panels_results = []
    totalCuf_results = []
    config = -1
    for validConfigDf in validConfigDfs:
        config += 1
        validConfigDf = validConfigDf.set_index('gridcellIDs').sort_values(by='panelid')
        panel_num_cells = panel_shape[0] * panel_shape[1]
        panelsDf = pd.DataFrame(validConfigDf['panelid'].values.reshape((-1, panel_num_cells))[:, 0])
        panelsDf = panelsDf.rename(columns={0: 'panelid'})
        panelsDf = panelsDf.set_index('panelid')
        panel_min_vals = getAllPanelsGhiNp(dataframe, validConfigDf, panel_shape)

        htn = ch.computeHtnForEachGridHour(timeAndDayArr.dayArr, timeAndDayArr.timeArr, latitude, tilt_roof,
                                           orientation_roof, panel_min_vals)

        hourlyGeneration = ch.calculateGpi(htn)
        hourlyGenerationDf = pd.DataFrame(hourlyGeneration, columns=panelsDf.index)
        # totalHourlyGenDf = hourlyGenerationDf.sum(axis=1)
        totalGeneration = hourlyGenerationDf.sum(axis=0)
        panelwiseCuf = ch.calculateCUF(totalGeneration, 1)

        totalTotalGeneration = totalGeneration.sum()
        totalCuf = ch.calculateCUF(totalTotalGeneration, hourlyGenerationDf.shape[1])

        panelsDf['totalGen'] = totalGeneration
        panelsDf['Cuf'] = panelwiseCuf

        hourlyGen_results.append(hourlyGenerationDf)
        panels_results.append(panelsDf)
        totalCuf_results.append(totalCuf)

    return totalCuf_results, hourlyGen_results, panels_results


def getBestPanels(selectedPanels, maxPanelsForSanctionLoad):
    """
    Selects the best panels based on their capacity utilization factor (Cuf).

    Sorts the given DataFrame of selected panels in descending order of the 'Cuf'
    column and returns the top panels up to the specified maximum number for
    a sanction load.
    """
    sSelectedPanels = selectedPanels.sort_values(by=['Cuf'], ascending=False)
    return sSelectedPanels.iloc[:maxPanelsForSanctionLoad, :]


def optimisedSelectBestPanels(all_poly_CPDf, no_pan):
    """
    Selects the best panel configurations based on the capacity utilization factor (Cuf).

    This function sorts the given DataFrame of panel configurations by the 'Cuf' value
    in descending order and selects the top configurations up to the specified number
    of panels (`no_pan`). It ensures that only one configuration per tile polygon is
    selected, prioritizing configurations with higher 'Cuf' values.

    """
    all_poly_CPDf_best = all_poly_CPDf.sort_values(by=['Cuf'], ascending=False)
    # prelim = all_poly_CPDf_best.iloc[:no_pan, :]

    cfgmap = {}
    selected = []
    cwise_idx = 0
    added = 0

    while added < no_pan and cwise_idx < all_poly_CPDf_best.shape[0]:
        pan = all_poly_CPDf_best.iloc[cwise_idx]
        if pan['Cuf'] == 0:
            break

        tile_polygon_id = pan.polyUid

        if tile_polygon_id not in cfgmap:
            cfgmap[tile_polygon_id] = pan.configId
            selected.append(pan)
            added += 1
        else:
            decided_cfg = cfgmap[tile_polygon_id]
            if decided_cfg == pan.configId:
                selected.append(pan)
                added += 1

        cwise_idx += 1
    selected_panels_polygons = pd.concat(selected, axis=1).T.drop(columns='configId')
    selected_panels_polygons = selected_panels_polygons.infer_objects()

    return selected_panels_polygons, cfgmap


def processPolygon(tile_id, polygon_id, polygon_arrays, slope, aspect, latitude, time_and_day_arr):
    """
    Process a polygon to determine valid panel configurations and their generation metrics.

    This function takes polygon-related data and calculates potential solar panel configurations
    based on the polygon's grid mask, slope, aspect, and latitude. It computes the panel layout,
    valid configurations, and their respective Capacity Utilization Factors (CUF) and hourly
    generation data. The function returns dataframes and grids representing valid configurations
    and their generation metrics.
    """
    polygon_valid_grid_mask = polygon_arrays['gridMask']
    cells_df = polygon_arrays['gridCellsDf']
    raddata1 = polygon_arrays['radiation_data']
    raddata2 = np.moveaxis(raddata1, 0, 2)
    nr, nc, _ = raddata2.shape
    raddata3 = raddata2.reshape((nr * nc, -1)).T
    flatmask = polygon_valid_grid_mask.flatten()
    raddata4 = raddata3[:, flatmask == True]
    dataframe = pd.DataFrame(data=raddata4, columns=cells_df['gridcellIDs'])

    buil_len = polygon_valid_grid_mask.shape[0]

    if buil_len >= params.PANEL_DIMEN[0] / params.GRIDCELL_SIZE:
        orientation = params.PORTRAIT
    else:
        orientation = params.LANDSCAPE

    result1 = lfs.getPanelAngleParams(slope, latitude, orientation, aspect)
    panel_shape, tilt_roof, shadow_mult, orientation_roof = result1
    skip_rows = int(panel_shape[0] * shadow_mult[0, 0])
    max_row = panel_shape[0] + skip_rows

    base_panel_layout_grid, remainder_shape = getBasePanels(polygon_valid_grid_mask, panel_shape, skip_rows)

    configs_panel_layout_grid = getConfigPanels(base_panel_layout_grid, (max_row, remainder_shape[1] + 1))
    # vcpls = valid_configs_panel_layout
    vcpls_listDf, vcpls_grid = getValidConfigPanels(configs_panel_layout_grid, polygon_valid_grid_mask,
                                                    panel_shape, cells_df)

    configs_CUF, configs_hourly_gen, configs_panels = getAllConfigCufs(dataframe,
                                                                       vcpls_listDf, panel_shape,
                                                                       time_and_day_arr,
                                                                       latitude, tilt_roof, orientation_roof)

    return vcpls_listDf, vcpls_grid, configs_hourly_gen, configs_panels


def computeOptimalPlacement(dataFrameDict, time_and_day_arr, no_pan):
    """
    Compute the optimal placement of solar panels on building polygons.

    This function processes a dictionary of dataframes containing polygon data and calculates
    the optimal solar panel configurations for each polygon. It uses the provided time and day
    array to compute generation metrics and selects the best panel configurations based on
    capacity utilization. The function returns dataframes of selected panel configurations,
    hourly generation data, layout lists, and any error conditions encountered.

    """
    all_poly_CP = []
    error_conds = []

    result_allpolycfg_dict = {}

    for k, v in dataFrameDict.items():
        v['time_and_day_arr'] = time_and_day_arr
        tile_id = v['tileId']
        building_id = v['buildingId']
        polygon_id = v['polygonId']
        tile_polygon_id = '_'.join([str(tile_id), str(building_id), str(polygon_id)])
        polyarrays = v['polygonArrays']
        if polyarrays['gridCellsDf'].shape[0] == 0:
            valid_configs_panel_layout_listDf, configs_hourly_gen, configs_panels = pd.DataFrame(
                columns=['rowidx', 'colidx', 'panelid', 'gridid']), [], []
        else:
            bundl2 = processPolygon(tile_id, polygon_id, polyarrays, v['slope'], v['aspect'],
                                    v['latitude'], time_and_day_arr)
            valid_configs_panel_layout_listDf, vcpls_grid, configs_hourly_gen, \
                configs_panels = bundl2

        for cid in range(len(configs_panels)):
            result_allpolycfg_dict[(tile_polygon_id, cid)] = (
                configs_hourly_gen[cid], valid_configs_panel_layout_listDf[cid], vcpls_grid[cid])

        m_configs_panels = []
        for config_id, config_panelsDf in enumerate(configs_panels):
            config_panelsDf['configId'] = int(config_id)
            config_panelsDf['polyUid'] = tile_polygon_id

            m_configs_panels.append(config_panelsDf)

        all_poly_CP += m_configs_panels

    all_poly_CPDf = pd.concat(all_poly_CP).reset_index()

    if all_poly_CPDf.shape[0] == 0:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
        error_cond = {'polId': 0, 'tId': 0, 'code': 'e003'}
        error_cond['msg'] = 'No valid configuration of panels on polygons could be found'
        error_conds.append(error_cond)

    selected_panels_polygons, polygons_cfg_map = optimisedSelectBestPanels(all_poly_CPDf, no_pan)

    result_allpoly_dict = {}

    for tile_polygon_id, config_id in polygons_cfg_map.items():
        tupl = result_allpolycfg_dict[(tile_polygon_id, config_id)]
        result_allpoly_dict[tile_polygon_id] = (tupl[0], tupl[1])
        vlibs.visualize_2d_np_array(array=tupl[2], plot_id=tile_polygon_id,
                                    plot_title="Panel Layout ", engine="frle")

    all_poly_HG = []
    all_poly_LL = []

    grpr = selected_panels_polygons.groupby(by='polyUid')
    for poly_uid, panel_uids in grpr.groups.items():
        selected_panel_ids = selected_panels_polygons.loc[panel_uids, 'panelid']
        unfilt_hourly_gen = result_allpoly_dict[poly_uid][0]
        unfilt_layout_list = result_allpoly_dict[poly_uid][1]

        filt_hourly_gen = unfilt_hourly_gen.loc[:, selected_panel_ids]
        filt_hourly_gen.columns = panel_uids
        filt_layout_list = unfilt_layout_list[unfilt_layout_list['panelid'].isin(selected_panel_ids)].copy()

        filt_layout_list['uPanelid'] = filt_layout_list['panelid'].replace(selected_panel_ids.to_list(),
                                                                           value=panel_uids.to_list())

        all_poly_HG.append(filt_hourly_gen)
        all_poly_LL.append(filt_layout_list)

    all_hourly_gen_df = pd.concat(all_poly_HG, axis=1)
    all_layout_list_df = pd.concat(all_poly_LL, axis=0)

    return selected_panels_polygons, all_hourly_gen_df, all_layout_list_df, error_conds
