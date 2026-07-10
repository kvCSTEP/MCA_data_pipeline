# -*- coding: utf-8 -*-
"""
Created on Thu Jul 16 16:32:19 2020

@author: milind

Parameters
----------
ds2
	layout of closest panel-containing grid-cell coordinates
	ds2[0,:,:] A grid-cell-map which has row-coordinate of that grid-cell
	ds2[1,:,:] A grid-cell-map which has column-coordinate of that grid-cell
block_shape
	A tuple representing the shape of block (#rows, #columns) to be laid.
panel_valid_mask
	A grid-cell-map showing grid-cells where panels are allowed to be placed (with the south-west corner of each panel
	overlapping completely with the south-west corner of the grid-cell) 
block_valid_mask
	A grid-cell-map showing grid-cells where blocks are allowed to be placed (with the south-west corner of the block
	overlapping completely with the south-west corner of the grid-cell)
coord_diff
	similar to ds2, but contains the (rows, cols) difference to closest panel-containing grid-cell.
sgpif
	A grid-cell-map showing the energy generation of the panel/block laid at grid-cell (with the south-west corner of the block
	overlapping completely with the south-west corner of the grid-cell)
pos_clus_same_row
	(row,column) highest GPI position for extending a row of panels by one.
pos_clus_diff_row
	(row,column) highest GPI position for starting a row of panels with minimum set of panels.
pan_pos
	(row,column) position at which left-top corner of panel is to be placed.
panelid
	ID of panel to be placed.



"""
from collections import defaultdict

import numpy as np
import pandas as pd
import scipy.ndimage as nd

import compute_htn as ch
# Custome local libraries
import layout_funcs as lfs
# import vlibs, \
import params

# LAT_LON_LEN_STR = 26
# # max length of string required to hold lat-long grid id

clusters_nuclei_df = pd.DataFrame()
block_maps = defaultdict(dict)
all_poly_data_structs = None


def getCandidatePosits1(panel_layout, exclayout1):
    '''
	Returns layout with the coordinates of the closest grid cell with an
	existing panel in it
	'''

    rr, cc = np.nonzero(panel_layout)
    vals = panel_layout[rr, cc]
    samp = exclayout1.copy()
    samp[rr, cc] = vals
    samp[np.where(samp == 0)] = -65536
    samp[np.where(samp > 0)] = 0
    ds1, ds2 = nd.distance_transform_cdt(samp, metric='taxicab',
                                         return_indices=True)
    return ds1, ds2


def getSameRowBlockPoss(t_p_i, coord_diff, block_valid_mask, block_shape):
    '''
	Returns the best same-row left and right positions to lay blocks
	
	Returns
	-------
	sposes : numpy.array
		m×2 array where m is the number of valid same-row adjacent positions found

	'''

    global block_maps

    l, w = block_valid_mask.shape
    same_row = coord_diff[1, :, :] * block_valid_mask
    all_block_corners = [*block_maps[t_p_i].values()]
    corners1 = [each[0] for each in all_block_corners]
    corners1_x, corners1_y = zip(*corners1)
    corners1_xy = np.c_[corners1_x, corners1_y]
    corners2 = [each[1] for each in all_block_corners]
    corners2_x, corners2_y = zip(*corners2)
    corners2_xy = np.c_[corners2_x, corners2_y]
    bot_rights = np.c_[corners1_xy[:, 0], corners2_xy[:, 1]]
    bot_right_just_rights = bot_rights + np.array([0, 1])
    bot_left_block_lefts = corners1_xy - np.array([0, block_shape[1]])

    bot_right_just_rights = bot_right_just_rights[bot_right_just_rights[:, 1] < w, :]
    bot_left_block_lefts = bot_left_block_lefts[bot_left_block_lefts[:, 1] >= 0, :]

    left_okay_mask_poses = block_valid_mask[bot_left_block_lefts[:, 0], bot_left_block_lefts[:, 1]]
    right_okay_mask_poses = block_valid_mask[bot_right_just_rights[:, 0], bot_right_just_rights[:, 1]]
    lokay = bot_left_block_lefts[left_okay_mask_poses, :]
    rokay = bot_right_just_rights[right_okay_mask_poses, :]
    sposes = np.r_[lokay, rokay]

    return sposes


def placePanel(pan_layout, pan_pos, panshape, panelid):
    '''
	Adds specified (by its ID) panel of the given shape to the grid-cell-wise map starting from its
	south-west corner.
	'''

    a, b = pan_pos[0], pan_pos[1]
    p, q = panshape[0], panshape[1]
    pan_layout1 = pan_layout.copy()
    pan_layout1[a - p + 1:a + 1, b:b + q] = panelid

    return pan_layout1


def getBestPositions1Poly(t_p_i, one_polygon, pans_rem):
    '''
	Finds the best position and block configuration for a new block to be placed on the polygon 
	to maximize generation. It considers the allowed block panel shapes for existing rows and 
	starting a new adjacent row separately. Starting a new row is currently not implemented.
	
	Returns
	-------
	same_row_data : tuple
		pos_data info describing best position at the edge of any existing row within the specified 
		polygon.
	diff_row_data : tuple
		pos_data info describing best position to start a new row at any edge of any existing cluster 
		within the specified polygon. Currently a null result.
	
	'''
    sgpif_block_panel = one_polygon.blockGPISums
    block_valid_masks = one_polygon.blockValidMasks
    panel_shape = one_polygon.panelShape
    exclayout1 = one_polygon.excLayout1
    mesh2 = one_polygon.mesh
    panel_layout = one_polygon.panelLayout

    ds1, ds2 = getCandidatePosits1(panel_layout, exclayout1)
    coord_diff = mesh2 - ds2

    elig_shapes_chosen = lfs.getEligibleBlockConfigs(params.ALLOWED_BLOCK_PANEL_SHAPES['samerow'],
                                                     pans_rem)

    # initialize variables
    # cere = cluster existing row extend
    best_cere_gpi = 0.0
    best_cere_b2p_shape = None
    best_cere_pos = None
    samerow_poses_block = dict()

    for block_2_panel_shape in elig_shapes_chosen:
        block_shape = lfs.tupMultiply(panel_shape, block_2_panel_shape)
        block_valid_mask = block_valid_masks[block_2_panel_shape]
        adj_pos = getSameRowBlockPoss(t_p_i, coord_diff, block_valid_mask, block_shape)

        samerow_poses_block[block_2_panel_shape] = adj_pos
        if adj_pos.shape[0] == 0:
            continue

        sgpif_b2p = sgpif_block_panel[block_2_panel_shape]
        samerow_gpis = sgpif_b2p[adj_pos[:, 0], adj_pos[:, 1]]

        # Just pick the highest gpi across all the block_panel_shapes
        mgi = samerow_gpis.argmax(axis=0)
        if samerow_gpis[mgi] > best_cere_gpi:
            best_cere_gpi = samerow_gpis[mgi]
            best_cere_pos = (adj_pos[mgi, 0], adj_pos[mgi, 1])
            best_cere_b2p_shape = block_2_panel_shape

    same_row_data = (best_cere_gpi, best_cere_pos, t_p_i, best_cere_b2p_shape)
    diff_row_data = (0, None, t_p_i, None)

    return same_row_data, diff_row_data


def getBestPositions2(touched_polygons, pans_rem):
    '''
	Obtains ultimate best positions for blocks in existing rows, adjacent rows, and as part of new cluster 
	given the current panel layout. It also disables new cluster positions that are now invalid. 
	
	Parameters
	----------
	touched_polygons : list
		All polygons with at least one block already present, among which the positions are to be found.
	
	Returns
	-------
	same_row_best : tuple
		pos_data info describing best position at the edge of any existing row in any polygon within 
		touched_polygons.
	diff_row_best : tuple
		pos_data info describing best position to start a new row at the edge of an existing cluster 
		within any polygon within touched_polygons.
	
	'''
    global all_poly_data_structs, clusters_nuclei_df
    gtn_max_same_row, gtn_max_diff_row = 0, 0

    same_row_data_coll = defaultdict(list)
    diff_row_data_coll = defaultdict(list)

    for t_p_i in touched_polygons:
        onepoly = all_poly_data_structs[t_p_i]
        same_row_data, diff_row_data = getBestPositions1Poly(t_p_i, onepoly, pans_rem)

        same_row_data_coll['t_p_i'].append(same_row_data[2])
        same_row_data_coll['gtn_clus_same_row'].append(same_row_data[0])
        same_row_data_coll['pos_clus_same_row'].append(same_row_data[1])
        same_row_data_coll['block_panel_shape_same_row'].append(same_row_data[3])

        diff_row_data_coll['t_p_i'].append(diff_row_data[2])
        diff_row_data_coll['gtn_clus_diff_row'].append(diff_row_data[0])
        diff_row_data_coll['pos_clus_diff_row'].append(diff_row_data[1])
        diff_row_data_coll['block_panel_shape_diff_row'].append(diff_row_data[3])

    # Extract max_gtn same_row and diff_row values
    if same_row_data_coll['gtn_clus_same_row']:
        gtn_max_same_row = max(same_row_data_coll['gtn_clus_same_row'])
        same_row_max_idx = same_row_data_coll['gtn_clus_same_row'].index(gtn_max_same_row)
        t_p_i_gtn_max_same_row = same_row_data_coll['t_p_i'][same_row_max_idx]
        pos_max_same_row = same_row_data_coll['pos_clus_same_row'][same_row_max_idx]
        block_panel_shape_max_same_row = same_row_data_coll['block_panel_shape_same_row'][same_row_max_idx]

    if diff_row_data_coll['gtn_clus_diff_row']:
        gtn_max_diff_row = max(diff_row_data_coll['gtn_clus_diff_row'])
        diff_row_max_idx = diff_row_data_coll['gtn_clus_diff_row'].index(gtn_max_diff_row)
        t_p_i_gtn_max_diff_row = diff_row_data_coll['t_p_i'][diff_row_max_idx]
        pos_max_diff_row = diff_row_data_coll['pos_clus_diff_row'][diff_row_max_idx]
        block_panel_shape_max_diff_row = diff_row_data_coll['block_panel_shape_diff_row'][diff_row_max_idx]

    same_row_best, diff_row_best = None, None
    if gtn_max_same_row > 0:
        same_row_best = t_p_i_gtn_max_same_row, pos_max_same_row, gtn_max_same_row, block_panel_shape_max_same_row
    if gtn_max_diff_row > 0:
        diff_row_best = t_p_i_gtn_max_diff_row, pos_max_diff_row, gtn_max_diff_row, block_panel_shape_max_diff_row

    return same_row_best, diff_row_best


def getBestNewClusPosition(block_panel_shape):
    '''Find the best cluster nucleus that are not already being used but still viable that gives the
	highest generation across all allowed block configurations
	
	Parameters
	----------
	block_panel_shape : tuple of size 2
		Number of rows and columns of panels for the type of block being updated.
	
	Returns
	-------
	new_clus_best : tuple
		pos_data_r info describing the best cluster nucleus position to initiate with a block of the 
		specified shape.
	cluster_id : int
		ID of the cluster nucleus.
	
	'''
    # filter out used clusters
    v_ia_clusters_mask = clusters_nuclei_df['viable'] & ~clusters_nuclei_df['active'] & (
            clusters_nuclei_df['blockPanelShape'] == block_panel_shape)
    viable_clusters = clusters_nuclei_df[v_ia_clusters_mask].sort_values(by='total_energy', ascending=False)
    if viable_clusters.shape[0] > 0:
        # pop out top potential cluster
        top_viable_cluster = viable_clusters[['rowidx', 'colidx']].iloc[0]
        pos_new_clus = tuple(top_viable_cluster)
        t_p_i_v = viable_clusters.loc[top_viable_cluster.name, 'polygon']
        gtn_new_clus = viable_clusters.loc[top_viable_cluster.name, 'total_energy']
        cluster_id = top_viable_cluster.name
        new_clus_best = (t_p_i_v, pos_new_clus, gtn_new_clus)
        return new_clus_best, cluster_id


def decideNewClus(same_row_best, diff_row_best, pans_rem, thresholds=params.TRIG_LEVELS):
    '''Check across all available clusters and block configurations that can be laid across the polygons
	for the best cluster and block configuration which yields highest generation
	
	Parameters
	----------
	same_row_best : tuple
		pos_data info for best place to put a block in an existing row.
	diff_row_best : TYPE
		pos_data info for best place to start a new row within an existing cluster with a block.
	thresholds : tuple, optional
		trigger levels for choosing same_row, diff_row or new_clus. The default is params.TRIG_LEVELS.
	
	Returns
	-------
	is_new_cluster_chosen : bool
		Whether a new cluster is being chosen.
	new_clus_bundl : tuple
		pos_data info for the new cluster nucleus to be initiated, if chosen.
	
	'''
    hyst_new_row, hyst_new_clus = thresholds
    is_new_cluster_chosen = False
    avg_gtn_max_same_row, avg_gtn_max_diff_row, avg_gtn_new_clus = 0, 0, 0
    new_potential_cluss = dict()

    # New Best clusters
    elig_shapes_chosen = lfs.getEligibleBlockConfigs(params.ALLOWED_BLOCK_PANEL_SHAPES['newclus'],
                                                     pans_rem)

    for new_clus_block_panel_shape in elig_shapes_chosen:
        cluster = getBestNewClusPosition(new_clus_block_panel_shape)
        if cluster:
            new_potential_cluss[new_clus_block_panel_shape] = cluster
    # find the cluster with biggest irradiation
    # x[1 --> indicates dict item value][0 --> choosing cluster bundle][2 --> choosing gtn]
    if len(new_potential_cluss) > 0:
        clus_block_panel_shape, new_clus_bundl = sorted(new_potential_cluss.items(),
                                                        key=lambda x: x[1][0][2], reverse=True)[0]
    else:
        new_clus_bundl = None

    if same_row_best:
        t_p_i_gtn_max_same_row, pos_max_same_row, gtn_max_same_row, b2p_shape_samerow = same_row_best
        avg_gtn_max_same_row = gtn_max_same_row / (b2p_shape_samerow[0] * b2p_shape_samerow[1])

    if diff_row_best:
        t_p_i_gtn_max_diff_row, pos_max_diff_row, gtn_max_diff_row, b2p_shape_diffrow = diff_row_best
        avg_gtn_max_diff_row = gtn_max_diff_row / (b2p_shape_diffrow[0] * b2p_shape_diffrow[1])

    if new_clus_bundl:
        new_clus_best, cluster_id = new_clus_bundl
        t_p_i_v, pos_new_clus, gtn_new_clus = new_clus_best
        avg_gtn_new_clus = gtn_new_clus / (clus_block_panel_shape[0] * clus_block_panel_shape[1])
        new_clus_best1 = t_p_i_v, pos_new_clus, gtn_new_clus, clus_block_panel_shape
        new_clus_bundl = new_clus_best1, cluster_id

    c2 = avg_gtn_new_clus > avg_gtn_max_diff_row * (1 + hyst_new_clus)
    c3 = avg_gtn_new_clus > avg_gtn_max_same_row * (1 + hyst_new_row) * (1 + hyst_new_clus)
    if c2 and c3:
        is_new_cluster_chosen = True
    return is_new_cluster_chosen, new_clus_bundl


def decideBestPosition(same_row_best, diff_row_best, thresholds):
    '''Decide which of the best positions should be chosen for laying a block within existing clusters
	- extend an existing row, or start a new row
	
	Parameters
	----------
	same_row_best : TYPE
		DESCRIPTION.
	diff_row_best : TYPE
		DESCRIPTION.
	thresholds : TYPE, optional
		DESCRIPTION. The default is params.TRIG_LEVELS.
	
	Returns
	-------
	best : tuple
		pos_data of the chosen block and position.
	is_diff_row_chosen : bool
		Whether a new row is being started.
	
	'''
    hyst_new_row, hyst_new_clus = thresholds
    avg_gtn_max_same_row, avg_gtn_max_diff_row = 0, 0

    if same_row_best is not None:
        t_p_i_gtn_max_same_row, pos_max_same_row, gtn_max_same_row, b2p_shape_samerow = same_row_best
        avg_gtn_max_same_row = gtn_max_same_row / (b2p_shape_samerow[0] * b2p_shape_samerow[1])
    if diff_row_best is not None:
        t_p_i_gtn_max_diff_row, pos_max_diff_row, gtn_max_diff_row, b2p_shape_diffrow = diff_row_best
        avg_gtn_max_diff_row = gtn_max_diff_row / (b2p_shape_diffrow[0] * b2p_shape_diffrow[1])

    c1 = avg_gtn_max_diff_row > avg_gtn_max_same_row * (1 + hyst_new_row)

    if not c1:
        best = same_row_best
        is_diff_row_chosen = False
    else:
        best = diff_row_best
        is_diff_row_chosen = True

    return best, is_diff_row_chosen


def addBlock(panel_id, new_block_pos, one_poly, t_p_i, cluster_id, block_panel_shape, block_id=0):
    '''Add given set of panels at given position and also mark off the required exclusion zones
	'''
    global block_maps
    panel_shape = one_poly.panelShape
    gap_shape = one_poly.skipShape
    panel_layout = one_poly.panelLayout
    exclayout1 = one_poly.excLayout1
    sgpif = one_poly.totalGpiGrid

    pidnew = panel_id
    panel_entries, pids, new_panel_poses = [], [], []
    pl, eel = panel_layout.copy(), exclayout1.copy()

    mults = params.MOUNT_HEIGHTS_MULTS
    block_shape = lfs.tupMultiply(block_panel_shape, panel_shape)

    for d1 in range(block_panel_shape[0]):
        for d2 in range(block_panel_shape[1]):
            pidnew += 1
            pos_now = (new_block_pos[0] - panel_shape[0] * d1, new_block_pos[1] + panel_shape[1] * d2)
            new_panel_poses.append(pos_now)
            mult = mults[d1]
            pl = placePanel(pl, pos_now, panel_shape, pidnew)
            panel_gen = sgpif[pos_now] * mult
            panel_cuf = ch.calculateCUF(panel_gen, 1)
            panel_entry = {'panelid': pidnew, 'totalGen': panel_gen,
                           'Cuf': panel_cuf, 'polyUid': t_p_i}
            panel_entries.append(panel_entry)
            pids.append(pidnew)

    eel = lfs.markExclZone2(eel, new_block_pos, block_panel_shape, panel_shape, gap_shape)

    block_maps[t_p_i].update({block_id: [new_block_pos,
                                         (new_block_pos[0] - block_shape[0] + 1,
                                          new_block_pos[1] + block_shape[1] - 1)]
                              })
    return panel_entries, pl, eel, pids, pidnew, new_panel_poses


def getSelectedGridCells():
    '''Gather all gridcells with panels in them for output purposes'''
    global all_poly_data_structs

    gridcells_list = []

    for t_p_i, poly_struct in all_poly_data_structs.items():
        panel_layout = poly_struct.panelLayout
        gridcells_df = poly_struct.gridCellsDF
        rid, cid = np.nonzero(panel_layout)
        vals = panel_layout[rid, cid]
        bbg = list(zip(rid, cid))
        sgridcells = gridcells_df.loc[bbg]
        sgridcells = sgridcells.reset_index()
        sgridcells['uPanelid'] = vals
        gridcells_list.append(sgridcells)

    selected_gridcells = pd.concat(gridcells_list)
    return selected_gridcells


def computeNewPlacement(dataFrameDict, a_poly_ds, all_hourly_gpis,
                        no_pan, target_generation, clusters):
    """
        Computes panel placement according to new criteria respecting proximity and
        with restriction of minimum number of panels in a row
	"""
    global clusters_nuclei_df, block_maps, all_poly_data_structs
    all_poly_data_structs = a_poly_ds
    clusters_nuclei_df = clusters
    if target_generation is None:
        target_generation = np.inf

    error_conds = list()

    if clusters_nuclei_df.shape[0] == 0:
        error_cond = {'polId': -1, 'tId': 0, 'code': 'e003',
                      'msg': "No local peak of insolation could be found for panel placement"}
        error_conds.append(error_cond)
        return None, None, None, error_conds

    clusters_nuclei_df['active'] = False
    clusters_nuclei_df['viable'] = True

    touched_polygons = set()
    panel_id = 0
    selected_panels_poly_list = []
    hourly_gens_dict = {}
    total_gen = 0
    it = 0

    # while panel_id < no_pan and total_gen < target_generation:
    while total_gen < target_generation:
        # initialization of some loop local variables
        it += 1
        pans_rem = no_pan - panel_id
        gen_rem = target_generation - total_gen
        # print(str(it)+"-th iteration begun")

        # pos_clus_max --> position in cluster with max HTN
        # pos_clus_same_row --> best of nearest available position in row in some cluster
        # pos_clus_diff_row --> best of nearest available position in next row in same cluster
        # pos_newclus --> best of nearest available position in new cluster

        # tie break between pos_clus_same_row, pos_clus_diff_row and pos_newclus
        # i.e. decide to 1. extend same row? or 2. start new row in same cluster? or 3. start new cluster?

        all_poly_data_structs = lfs.updateClustersAndBlockValidMasks(all_poly_data_structs, clusters_nuclei_df)

        same_row_best, diff_row_best = getBestPositions2(touched_polygons, pans_rem)

        isnewclus, new_clus_bundl = decideNewClus(same_row_best, diff_row_best, pans_rem,
                                                  params.TRIG_LEVELS)

        if new_clus_bundl is None and same_row_best is None and diff_row_best is None:
            break

        if not isnewclus:
            best, isdiffrow = decideBestPosition(same_row_best, diff_row_best, params.TRIG_LEVELS)
            tile_polygon_id, new_block_pos, gtn_nex, b2p_shape = best
        elif isnewclus:
            new_clus_best, cluster_id = new_clus_bundl
            tile_polygon_id, new_block_pos, gtn_nex, b2p_shape = new_clus_best
            clusters_nuclei_df.loc[cluster_id, 'active'] = True
            touched_polygons.add(tile_polygon_id)
            poly_ds1 = all_poly_data_structs[tile_polygon_id]
            panel_shape = poly_ds1.panelShape
            block_shape = lfs.tupMultiply(panel_shape, b2p_shape)
            cluster_nucleus_topleft = (new_block_pos[0] - block_shape[0] + 1, new_block_pos[1])
            clus_row_conflict_mask = (clusters_nuclei_df['rowidx'] < new_block_pos[0]) \
                                     & (clusters_nuclei_df['rowidx'] >= cluster_nucleus_topleft[0]) \
                                     & (clusters_nuclei_df['polygon'] == tile_polygon_id)
            clusters_nuclei_df.loc[clus_row_conflict_mask, 'viable'] = False

            isdiffrow = False

        poly_ds = all_poly_data_structs[tile_polygon_id]
        buty = addBlock(panel_id, new_block_pos, poly_ds, tile_polygon_id, cluster_id,
                        b2p_shape, block_id=it)
        panel_entries, pdone, eedone, pids, pidnew, new_panel_poses = buty
        selected_panels_poly_list += panel_entries

        gpif = all_hourly_gpis[tile_polygon_id]
        panel_gen = 0
        for idx, pid in enumerate(pids):
            hourly_gens_dict[pid] = gpif[:, new_panel_poses[idx][0], new_panel_poses[idx][1]]
            panel_gen += panel_entries[idx]['totalGen']
        total_gen += panel_gen

        poly_ds.panelLayout = pdone
        poly_ds.excLayout1 = eedone
        all_poly_data_structs[tile_polygon_id] = poly_ds

        panel_id = pidnew

    for tile_polygon_id, onePoly in all_poly_data_structs.items():

        pdone = onePoly.panelLayout
        eedone = onePoly.excLayout1
        # vlibs.visualize_2d_np_array(array=pdone, plot_id=tile_polygon_id,
        #                             plot_title="Panel Layout ", engine="le2")
        # # visualize the panel layout
        # vlibs.visualize_2d_np_array(array=eedone, plot_id=tile_polygon_id,
        #                             plot_title="Exclusion Layout ", engine="le2")
        # visualize the exc layout

        if tile_polygon_id in block_maps:
            block_layout = lfs.get_block_layout(block_maps[tile_polygon_id], layout_shape=pdone.shape)

        # vlibs.visualize_2d_np_array(array=block_layout, plot_id=tile_polygon_id,
        #                             plot_title="Block Layout ", engine="le2")
        # visualize block layout

    if len(selected_panels_poly_list) > 0:
        selected_panels_polygons = pd.DataFrame(selected_panels_poly_list).set_index('panelid')
    else:
        error_cond = {'polId': -1, 'tId': 0, 'code': 'e004', 'msg': "Target capacity too low for minimum block size"}
        error_conds.append(error_cond)
        return None, None, None, error_conds

    hourly_gen_panels = pd.DataFrame(hourly_gens_dict)

    selected_gridcells = getSelectedGridCells()
    return selected_panels_polygons, hourly_gen_panels, selected_gridcells, error_conds
