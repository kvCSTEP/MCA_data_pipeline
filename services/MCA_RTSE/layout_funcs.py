# -*- coding: utf-8 -*-
# -.-.-.-.-.-.-.-.-.-.-.-.-.-.-.-.-.-.-.-.#

from functools import cache

# * File Name : 3d_voxels_visuals.py
#
# * Purpose :
#
# * Creation Date : 21-05-2024
#
# * Last Modified : Fri 07 Jun 2024 12:59:44 PM IST
#
# * Created By : Yaay Nands
# _._._._._._._._._._._._._._._._._._._._._.#
import numpy as np
import pandas as pd
import scipy.ndimage as nd
from scipy.ndimage import generate_binary_structure

# parameters for defines
import params


@cache
def tupMultiply(tup1, tup2):
    return tup1[0] * tup2[0], tup1[1] * tup2[1]


def argsortGridcellIdxs(rft, reqdidxs):
    ir, ic = reqdidxs
    vals = rft[ir, ic]
    ip = np.c_[ir, ic]
    iddx = np.argsort(vals)[::-1]
    ip1 = ip[iddx]
    vals1 = vals[iddx]
    return ip1, vals1


def getPanelAngleParams(roof_slope, latitude, panel_orientation, roof_azimuth):
    if roof_slope <= 15:
        tilt_panel = latitude
        shadow_extent_mult = np.array([[0.5, 0],
                                       [0.5, 0]])
    elif roof_slope > 15:
        tilt_panel = roof_slope
        shadow_extent_mult = np.array([[0, 0],
                                       [0, 0]])

    if panel_orientation == params.PORTRAIT:
        panel_rows = params.PANEL_DIMEN[0] / params.GRIDCELL_SIZE
        panel_cols = params.PANEL_DIMEN[1] / params.GRIDCELL_SIZE
    elif panel_orientation == params.LANDSCAPE:
        panel_rows = params.PANEL_DIMEN[1] / params.GRIDCELL_SIZE
        panel_cols = params.PANEL_DIMEN[0] / params.GRIDCELL_SIZE

    eff_panel_rows = int(np.ceil(np.cos(np.radians(tilt_panel)) * panel_rows))
    eff_panel_cols = int(panel_cols)
    eff_panel_shape = (eff_panel_rows, eff_panel_cols)

    #            block              l   w
    # shadow_extent_mult = np.array([[?, ?],  # shadow length multipliers
    #                               [?, ?]]) # shadow width multipliers
    # Multipliers representing dependence of shadow length on block dimensions. For now,
    # the max height of the block is assumed from a proxy of block length. Since shadow
    # length depends upon height, and we have a fixed inclination here, we define dependence
    # upon length only.
    #

    if -45 <= roof_azimuth <= 45:
        orientation_roof = 0

    elif 46 <= roof_azimuth <= 135:
        orientation_roof = 90

    elif roof_azimuth >= 136 and roof_azimuth <= 180:
        orientation_roof = 180

    elif roof_azimuth >= -135 and roof_azimuth <= -46:
        orientation_roof = -90

    else:
        orientation_roof = -180

    return eff_panel_shape, tilt_panel, shadow_extent_mult, orientation_roof


def get_block_layout(block_maps, layout_shape=None):
    assert layout_shape, "Tell me the layout shape"
    plottable_bmap = np.zeros(layout_shape)
    for block_id, corners in block_maps.items():
        bottom_left = corners[0]
        top_right = corners[1]
        plottable_bmap[top_right[0]: bottom_left[0] + 1, bottom_left[1]:top_right[1] + 1] = block_id
    return plottable_bmap


def getValidPosits_PPS(panel_layout, panel_shape, block_2_panel_shape, shadow_extent_mult):
    '''Checks each grid-cell position if a new block casts a shadow that falls onto any existing
	panel
	'''
    block_shape = tupMultiply(panel_shape, block_2_panel_shape)
    ttup = getShadowShape(block_2_panel_shape, panel_shape, shadow_extent_mult)
    if ttup == (0, 0):
        return np.ones_like(panel_layout, dtype=bool)

    sts_rows_shadowonly, sts_cols_overhang = ttup
    sts_cols = block_shape[1] + 2 * sts_cols_overhang
    sts_rows = block_shape[0] + sts_rows_shadowonly

    shadow_template_shape = (sts_rows, sts_cols)
    shadow_template = np.zeros(shadow_template_shape)

    block_bottom_left = (shadow_template_shape[0] - 1, sts_cols_overhang)

    shadow_layout = markExclZone2(shadow_template, block_bottom_left,
                                  block_2_panel_shape, panel_shape, shadow_extent_mult)
    shadow_temp1 = np.zeros_like(shadow_template, dtype=bool)
    shadow_temp1[shadow_layout == -1] = True

    default_filter_origin = (shadow_temp1.shape[0] // 2, shadow_temp1.shape[1] // 2)
    orgxy1 = (block_bottom_left[0] - default_filter_origin[0], block_bottom_left[1] - default_filter_origin[1])

    shadow_intersect = nd.maximum_filter(panel_layout, footprint=shadow_temp1, mode='constant', cval=0, origin=orgxy1)
    shadow_intersect_bool = np.zeros(shadow_intersect.shape, dtype=bool)
    shadow_intersect_bool[shadow_intersect > 0] = True
    shadow_intersect_bool1 = ~shadow_intersect_bool

    return shadow_intersect_bool1


def getValidPosits_EPS(exclayout1, panel_layout, panel_shape, block_2_panel_shape):
    '''Checks, for a new block, each grid-cell position if there's any shadow that is being
	being cast by any existing panel
	'''
    block_shape = tupMultiply(panel_shape, block_2_panel_shape)
    allowed_layout = ~(exclayout1 == -1)
    no_panel_present_layout = ~(panel_layout > 0)
    e1pe = (no_panel_present_layout & allowed_layout).astype(int)

    orgxy = (+1 * (block_shape[0] // 2) - 1, -1 * (block_shape[1] // 2))
    block_valid_pos = nd.minimum_filter(e1pe, size=block_shape,
                                        mode='constant', cval=0, origin=orgxy)
    block_valid_mask = block_valid_pos == 1
    return block_valid_mask


def getEligibleBlockConfigs(b2p_shapes, panels_remaining):
    elig_shapes_excess = {}

    for block_2_panel_shape in b2p_shapes:
        block_no_pans = block_2_panel_shape[0] * block_2_panel_shape[1]
        elig_shapes_excess[block_2_panel_shape] = panels_remaining - block_no_pans

    elig_shapes_excess_sorted = [k for k, v in sorted(elig_shapes_excess.items(),
                                                      key=lambda item: item[1], reverse=True)]
    elig_shapes_chosen = set()
    for shap in elig_shapes_excess_sorted:
        excess = elig_shapes_excess[shap]
        if excess < 0:
            break
        elig_shapes_chosen.add(shap)

    return elig_shapes_chosen


def getShadowShape(block_2_panel_shape, panel_shape, shadow_extent_mult):
    sha_ll = shadow_extent_mult[0, 0]
    sha_wl = shadow_extent_mult[1, 0]

    # shadow_template_shape = (int(panel_shape[0]*(1+sha_l)),panel_shape[1]*(1+2*sha_w))
    block_shape = tupMultiply(panel_shape, block_2_panel_shape)
    sts_cols_overhang = int(block_shape[0] * sha_wl)
    sts_rows_shadowonly = int(block_shape[0] * sha_ll)

    return sts_rows_shadowonly, sts_cols_overhang


def markExclZone2(exclayout, block_pos, block_2_panel_shape, panel_shape, shadow_extent_mult):
    ''' Marks off shadowed regions above and on either side of the chosen block
	position (south-west corner) with -1 
	We interpret the gap to mean (a) a rectangle right above, and 
	(b) a rectangle with a corner on the north-west and north-east of the block 
	'''

    exclayout1 = exclayout.copy()
    block_shape = tupMultiply(panel_shape, block_2_panel_shape)

    ttup = getShadowShape(block_2_panel_shape, panel_shape, shadow_extent_mult)
    sts_rows_shadowonly, sts_cols_overhang = ttup

    br, bc = block_pos
    bl, bw = block_shape
    sl = sts_rows_shadowonly
    sw = sts_cols_overhang
    el, ew = exclayout1.shape

    exclayout1[max(0, br - bl - sl + 1):br - bl + 1, max(0, bc - sw): min(ew, bc + bw + sw)] = -1

    return exclayout1


def blockSumGPI(total_gpi_grid, panel_shape, block_panel_shape,
                mount_height_mults=params.MOUNT_HEIGHTS_MULTS):
    """Returns grid-cell-wise map of total generation by a panel placed at each valid location (specifically
	    with its north-west corner)"""
    panel_template = np.zeros(panel_shape, dtype=float)
    app_mount_height_mults = mount_height_mults[0:block_panel_shape[0]].reshape(-1, 1).repeat(block_panel_shape[1],
                                                                                              axis=1)
    block_panel_template = app_mount_height_mults * np.ones(block_panel_shape, dtype=float)
    panel_template[0, 0] = 1
    block_template = np.kron(block_panel_template, panel_template)
    panel_template1 = block_template[0:(block_panel_shape[0] - 1) * panel_shape[0] + 1,
                      0:(block_panel_shape[1] - 1) * panel_shape[1] + 1]
    org = (-panel_template1.shape[0] // 2 + 1, panel_template1.shape[1] // 2)
    block_sum_gpi = nd.convolve(total_gpi_grid, panel_template1, mode='constant', cval=0.0, origin=org)

    return block_sum_gpi


def updateClustersAndBlockValidMasks(all_poly_data_structs, clusters_nuclei_df):
    """Update block valid masks for all polygons and all applicable block shapes, and cluster validity for all
    polygons"""

    block_panel_shapes = set(params.ALLOWED_BLOCK_PANEL_SHAPES['newclus'] + \
                             params.ALLOWED_BLOCK_PANEL_SHAPES['diffrow'] + \
                             params.ALLOWED_BLOCK_PANEL_SHAPES['samerow'])

    for t_p_i, onePoly in all_poly_data_structs.items():
        exclayout1 = onePoly.excLayout1
        panel_layout = onePoly.panelLayout
        panel_shape = onePoly.panelShape
        shadow_extent_mult = onePoly.skipShape
        blockValidMasks = {}
        for b2p_shape in block_panel_shapes:
            block_valid_mask1 = getValidPosits_EPS(exclayout1, panel_layout, panel_shape, b2p_shape)
            if b2p_shape in params.ALLOWED_BLOCK_PANEL_SHAPES['newclus']:
                block_valid_mask2 = getValidPosits_PPS(panel_layout, panel_shape, b2p_shape, shadow_extent_mult)
                block_unshadowed_mask = block_valid_mask1 & block_valid_mask2
                updateClusterViabilityAndValidity(clusters_nuclei_df, b2p_shape, block_unshadowed_mask, t_p_i)
            blockValidMasks[b2p_shape] = block_valid_mask1
        onePoly.blockValidMasks = blockValidMasks
    all_poly_data_structs[t_p_i] = onePoly

    return all_poly_data_structs


def updateClusterViabilityAndValidity(clusters_nuclei_df, block_panel_shape, block_valid_mask, t_p_i):
    '''
	Get clusters DF corresponding to block_panel_shape, mark any clusters that 
	fall in a now invalid position
	
	Parameters
	----------
	block_panel_shape : tuple of size 2
		Number of rows and columns of panels for the type of block being updated.
	
	Returns
	-------
	None.
	
	'''

    v_ia_clusters_mask = clusters_nuclei_df['viable'] & ~clusters_nuclei_df['active'] & (
            clusters_nuclei_df['blockPanelShape'] == block_panel_shape)
    viable_clusters = clusters_nuclei_df[v_ia_clusters_mask]
    t_p_i_cluster_nuclei = viable_clusters[viable_clusters['polygon'] == t_p_i]
    rcids = t_p_i_cluster_nuclei[['rowidx', 'colidx']].values
    invalid_clus_map = ~block_valid_mask[rcids[:, 0], rcids[:, 1]]
    invalid_clus_idxs = t_p_i_cluster_nuclei.loc[invalid_clus_map].index
    clusters_nuclei_df.loc[invalid_clus_idxs, 'viable'] = False


# visualize the clusters
# vlibs.visualize_clusters(clusters_nuclei_df, tpi=t_p_i)


def markClustersAtLocalMinPanelPeaks2(block_sum_gpi, block_panel_shape):
    """ Returns list of cluster nuclei positions - which are local minima of GPI for polygons """
    neare = generate_binary_structure(2, 2)
    peaks = nd.maximum_filter(block_sum_gpi, footprint=neare) == block_sum_gpi

    cluster_nuclei, cluster_vals = argsortGridcellIdxs(block_sum_gpi, np.nonzero(peaks))
    # avg_cluster_vals = cluster_vals/(block_panel_shape[0]*block_panel_shape[1])
    cluster_nuclei_df = pd.DataFrame(cluster_nuclei, columns=['rowidx', 'colidx'])
    cluster_nuclei_df['total_energy'] = cluster_vals
    cluster_nuclei_df = cluster_nuclei_df[cluster_nuclei_df['total_energy'] > 0]

    return cluster_nuclei_df
