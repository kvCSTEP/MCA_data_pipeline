# -*- coding: utf-8 -*-
# -.-.-.-.-.-.-.-.-.-.-.-.-.-.-.-.-.-.-.-.#
# Organized imports
import json
from typing import List, Optional
from decouple import config
import numpy as np
import pandas as pd
from pydantic import BaseModel

# * File Name : params.py
#
# * Purpose :
#
# * Creation Date : 26-05-2024
#
# * Last Modified : Sun 02 Jun 2024 12:50:49 AM IST
#
# * Created By : Yaay Nands
# _._._._._._._._.._._._._._._._._._._._._.#
polygon_details = json.loads(config('DEFAULT_INPUT_POLYGON_DETAILS'))
# Default input parameters
# This dictionary holds default values for the input parameters.
default_input = {
    "sanctionLoad": config('DEFAULT_INPUT_SANCTION_LOAD'),
    "typeOfComputation": config('DEFAULT_INPUT_TYPE_OF_COMPUTATION'),
    "polygonDetails": polygon_details,
    "city": config('DEFAULT_INPUT_CITY')
}

# Constants
GRIDCELL_SIZE = None  # in metre

# Panel Parameters
PANEL_WATTAGE = None
PANEL_DIMEN = ()
PANEL_ENERGY_EFF = None
PANEL_SIZE = None

# Minimum requirements for panel arrangements
MIN_PANELS_IN_ROW = None
LAT_LON_LEN_STR = None  # max length of string required to hold lat-long grid id

# Trigger levels for new rows and clusters
TRIG_LVL_NEW_ROW = None
TRIG_LVL_NEW_CLUS = None
TRIG_LEVELS = (TRIG_LVL_NEW_ROW, TRIG_LVL_NEW_CLUS)

# Orientation constants
LANDSCAPE = 1
PORTRAIT = 2

# Multipliers for mounting heights
MOUNT_HEIGHTS_MULTS = None

# Slope and aspect parameters
slope = None
aspect = None


# Function to calculate grid area
# Returns the area of a grid cell based on its size.
def gridArea():
    return GRIDCELL_SIZE ** 2


# Function to calculate panel size
# Returns the size of a panel based on its dimensions and grid cell size.
def panelSize():
    return PANEL_DIMEN[0] / GRIDCELL_SIZE * PANEL_DIMEN[1] / GRIDCELL_SIZE


ALLOWED_BLOCK_PANEL_SHAPES = dict()  # Allowed shapes for block panels
ROOF_ALBEDO = None
SOLAR_CONSTANT = None

from dataclasses import dataclass


@dataclass
class Polygon:
    """This class encapsulates all the pieces of data that pertain to a polygon.

    Attributes
    ----------
    gridMask
        2D-array with each element representing one grid-cell, sized to the bounding box of the contained polygon. Henceforth such an array is called a grid-cell-map. For gridmask_arr specificaly, each element is 1 if it is inside the polygon, or 0 if it is not.

    totalGpiGrid
        A grid-cell-map of generation from a panel placed at each position

    panelShape
        A tuple representing the shape of panel (#rows, #columns) to be laid

    skipShape
        A 2x2 array representing the dependence of shadow extents on block dimensions
        - (0,0) -> ll - Ratio of shadow length (rows) beyond the block on block length (rows)
        - (0,1) -> lw - Ratio of shadow length (rows) beyond the block on block width (columns)
        - (1,0) -> wl - Ratio of shadow width (columns) beyond the block on block length (rows)
        - (1,1) -> ww - Ratio of shadow width (columns) beyond the block on block width (columns)

    mesh
        3D-array with [0,:,:] and [1,:,:] being grid-cell map. They represent x- and y- coordinate of each grid-cell respectively.

    gridCellsDF
        Table of grid-cells with row and column index, plus northing and easting

    blockGPISums
        Collection of grid-cell-maps of generation from blocks of different sizes placed at each position

    panelLayout
        A grid-cell-map showing the panel layout over grid-cells. Elements have a value equal to the ID of the panel on each grid-cell, if present, else 0 if there is no panel.

    excLayout1
        A grid-cell-map showing grid-cells forbidden for panel laying. Elements have a value of -1 if it is forbidden to have a panel on it, or 0 if it is permitted.

    blockValidMasks
        Collection of grid-cell-maps showing grid-cell positions where it is valid to place blocks of different sizes

    """
    gridMask: np.ndarray
    totalGpiGrid: np.ndarray
    panelShape: tuple
    skipShape: np.ndarray
    mesh: np.ndarray
    gridCellsDF: pd.DataFrame
    blockGPISums: np.ndarray
    panelLayout: np.ndarray
    excLayout1: np.ndarray
    blockValidMasks: dict


class PolygonDetails(BaseModel):
    """Class for polygon details."""
    tileId: str
    buildingId: int
    polygonId: int


class DInput(BaseModel):
    """Class for input data parameters."""
    sanctionLoad: int
    typeOfComputation: str
    polygonDetails: List[dict]
    city: str
    targetGen: Optional[float] = None  # Optimized type for target generation
