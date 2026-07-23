"""
merged_slope_ward_pipeline.py
─────────────────────────────
Runs the complete workflow in one script:

1) Read original slope/building shapefiles.
2) Detect dominant projected CRS and calculate Area in m².
3) Spatially join ward boundary attributes.
4) Save final shapefiles only to FINAL_SHP_OUTPUT_FOLDER, e.g. Slope_Shp2.
5) Create CSV 1: unique ward-tile mapping.
6) Create CSV 2: polygon CSV mapped with Ward_Name and Ward_No.

Important:
- All user paths and options are in the CONFIGURATION block below.
- No permanent Slope_Shp1 / intermediate shapefile folder is used.
- Keep this file under a normal local/drive path and run it with Python.
"""

from __future__ import annotations

import os
import shutil
import warnings
import multiprocessing
import concurrent.futures
from pathlib import Path
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Iterable, Optional

import numpy as np
import pandas as pd
import geopandas as gpd
from tqdm import tqdm

try:
    from dbfread import DBF  # faster attribute-only reads; optional fallback below
except Exception:  # pragma: no cover
    DBF = None

warnings.filterwarnings("ignore")


# =============================================================================
# CONFIGURATION — change only this section for another city/project
# =============================================================================

# Input shapefiles before processing
INPUT_SLOPE_SHP_FOLDER = r"Z:\AP_RAJAHMUNDRY\4_CSTEP_AP_RAJAHMUNDRY_SLOPE_ASPECT\Slope_Shp"

# Ward boundary shapefile used for spatial join
WARD_BOUNDARY_SHP = r"G:\Ward_Boundries\AP\Rajahmundry_WardBoundary.shp"
WARD_NAME_FIELD = "Ward_Name"
WARD_NO_FIELD = "Ward_Numbe"      # change to Ward_No / Ward_Number if needed
SPATIAL_JOIN_PREDICATE = "intersects"

# Input polygon/MCA CSV that contains polygon_code
INPUT_POLYGON_CSV = r"Z:\AP_RAJAHMUNDRY\rajahmundry_polygons\rajahmundry_polygons.csv"

# Final shapefile output folder — this is the only shapefile output folder
FINAL_SHP_OUTPUT_FOLDER = r"G:\AP_RAJAHMUNDRY\Slope_Shp2"

# Output CSV 1: unique ward-tile mapping from final shapefiles
OUT_WARD_TILE_CSV = r"Z:\AP_RAJAHMUNDRY\rajahmundry_polygons\rajahmundry_unique_ward_tile.csv"

# Output CSV 2: input polygon CSV with Ward_Name and Ward_No added
OUT_POLYGON_WITH_WARDS_CSV = r"Z:\AP_RAJAHMUNDRY\rajahmundry_polygons\rajahmundry_polygons_with_wards.csv"

# Processing options
MAX_WORKERS = None                 # None = CPU count - 1
CLEAN_FINAL_OUTPUT_FOLDER = False  # True = delete existing shapefile sidecars in Slope_Shp2 first
COLUMNS_TO_DROP = ["RoofMatr", "Min3DL", "Max3DL", "Area3D"]

# Output ward column names kept DBF-safe for shapefile format
OUT_WARD_NAME = "Ward_Name"        # 9 chars
OUT_WARD_NO = "Ward_Numbe"            # 7 chars


# =============================================================================
# Shared helpers
# =============================================================================

_AREA_CRS = None
_WARD_GDF = None
_WORKER_COLUMNS_TO_DROP = None


def auto_workers(max_workers: Optional[int] = None) -> int:
    """Return a safe worker count."""
    return max_workers or max(1, multiprocessing.cpu_count() - 1)


def print_section(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def validate_path_exists(path: str, label: str) -> None:
    if not Path(path).exists():
        raise FileNotFoundError(f"{label} not found: {path}")


def prepare_output_folder(folder: str, clean: bool = False) -> None:
    """Create output folder. Optionally remove old shapefile sidecars only."""
    out = Path(folder)
    out.mkdir(parents=True, exist_ok=True)

    if not clean:
        return

    shapefile_sidecars = {
        ".shp", ".shx", ".dbf", ".prj", ".cpg", ".qix", ".fix",
        ".sbn", ".sbx", ".aih", ".ain", ".atx", ".xml",
    }
    for file_path in out.iterdir():
        if file_path.is_file() and file_path.suffix.lower() in shapefile_sidecars:
            file_path.unlink()
        elif file_path.is_dir() and file_path.name.lower().endswith(".shp"):
            shutil.rmtree(file_path)


def get_utm_zone(lon: float, lat: float) -> str:
    """Return EPSG code for the UTM zone covering lon/lat."""
    zone = int((lon + 180) / 6) + 1
    epsg = 32600 + zone if lat >= 0 else 32700 + zone
    return f"EPSG:{epsg}"


def crs_epsg(crs_value) -> Optional[int]:
    """Extract EPSG int when possible."""
    try:
        return gpd.GeoSeries([], crs=crs_value).crs.to_epsg()
    except Exception:
        try:
            return int(str(crs_value).split(":")[1])
        except Exception:
            return None


def same_crs(left, right) -> bool:
    """Robust CRS comparison."""
    if left is None or right is None:
        return False

    left_epsg = crs_epsg(left)
    right_epsg = crs_epsg(right)
    if left_epsg is not None and right_epsg is not None:
        return left_epsg == right_epsg

    try:
        return left.to_wkt() == right.to_wkt()
    except Exception:
        return str(left) == str(right)


def ensure_projected(gdf: gpd.GeoDataFrame, target_crs: str) -> tuple[gpd.GeoDataFrame, str]:
    """
    Return gdf in a projected CRS for area calculation.
    This follows your Step 1 logic: no CRS is assigned to target_crs, geographic CRS is reprojected,
    and other projected CRS values are aligned to target_crs.
    """
    if gdf.crs is None:
        return (
            gdf.set_crs(target_crs, allow_override=True).to_crs(target_crs),
            f"No CRS → assigned/reprojected to {target_crs}",
        )

    if same_crs(gdf.crs, target_crs):
        return gdf, f"Already in target CRS {target_crs}"

    if gdf.crs.is_geographic:
        return gdf.to_crs(target_crs), f"Geographic CRS {gdf.crs} → {target_crs}"

    return gdf.to_crs(target_crs), f"Projected CRS {gdf.crs} → {target_crs}"


def normalize_id(value) -> Optional[str]:
    """Normalize Poly_ID / polygon_code for safe matching."""
    if pd.isna(value):
        return None

    s = str(value).strip()
    if s == "" or s.lower() in {"none", "nan"}:
        return None

    try:
        f = float(s)
        if f.is_integer():
            return str(int(f))
        return str(f)
    except Exception:
        return s


def find_col(columns: Iterable[str], *prefixes: str) -> Optional[str]:
    """
    Return first column whose lowercase name starts with the supplied prefixes.
    Prefix order is respected, so Ward_Name is preferred before a generic Name field.
    """
    for prefix in prefixes:
        p = prefix.lower()
        for col in columns:
            if str(col).lower().startswith(p):
                return col
    return None


def read_attributes_only(shp_path: str) -> pd.DataFrame:
    """
    Read shapefile attributes only.
    Uses dbfread when available; otherwise falls back to GeoPandas.
    """
    shp = Path(shp_path)
    dbf_path = shp.with_suffix(".dbf")

    if DBF is not None and dbf_path.exists():
        table = DBF(str(dbf_path), load=True)
        return pd.DataFrame(iter(table))

    try:
        gdf = gpd.read_file(shp_path, engine="pyogrio")
    except Exception:
        gdf = gpd.read_file(shp_path)

    return pd.DataFrame(gdf.drop(columns="geometry", errors="ignore"))


# =============================================================================
# Step 1 helper: dominant CRS detection for area calculation
# =============================================================================

def _read_crs_and_count(args):
    shp_path, shp_name = args
    try:
        gdf_head = gpd.read_file(shp_path, rows=0)
        crs_str = str(gdf_head.crs) if gdf_head.crs else "None"

        # Keep the original script's polygon-count logic.
        # It is used only for selecting the dominant CRS by total features.
        poly_count = len(gpd.read_file(shp_path))
        return shp_name, crs_str, poly_count, None
    except Exception as exc:
        return shp_name, "None", 0, str(exc)


def detect_dominant_projected_crs(input_folder: str, shapefiles: list[Path], workers: int) -> str:
    """
    Detect dominant CRS by total polygon count. If dominant CRS is geographic,
    switch to a UTM fallback based on sample bounds.
    """
    print_section("STEP 1A — Detecting dominant CRS for area calculation")

    args = [(str(path), path.name) for path in shapefiles]
    crs_polygon_counts = Counter()
    file_crs_map = {}

    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_read_crs_and_count, arg): arg[1] for arg in args}
        for future in as_completed(futures):
            shp_name, crs_str, poly_count, err = future.result()
            if err:
                print(f"  ✗ {shp_name}: {err}")
                continue

            file_crs_map[shp_name] = crs_str
            if crs_str != "None":
                crs_polygon_counts[crs_str] += poly_count
            print(f"  ✓ {shp_name}: CRS={crs_str} | polygons={poly_count:,}")

    if not crs_polygon_counts:
        raise RuntimeError("Could not determine CRS from any input shapefile.")

    dominant_crs, _ = crs_polygon_counts.most_common(1)[0]
    print(f"\nDominant CRS selected: {dominant_crs}")

    try:
        import pyproj

        crs_obj = pyproj.CRS(dominant_crs)
        if crs_obj.is_geographic:
            print("Dominant CRS is geographic, resolving UTM fallback...")
            sample_file = next(name for name, crs in file_crs_map.items() if crs == dominant_crs)
            sample_gdf = gpd.read_file(str(Path(input_folder) / sample_file), rows=1)
            bounds = sample_gdf.total_bounds
            lon = (bounds[0] + bounds[2]) / 2
            lat = (bounds[1] + bounds[3]) / 2
            dominant_crs = get_utm_zone(lon, lat)
            print(f"UTM fallback CRS: {dominant_crs}")
    except Exception as exc:
        print(f"Could not verify/convert dominant CRS ({exc}); using {dominant_crs}")

    return dominant_crs


# =============================================================================
# Combined Step 1 + Step 2: area calculation + ward join to final folder
# =============================================================================

def _init_area_ward_worker(ward_wkb_list, ward_names, ward_numbers, ward_crs, area_crs, columns_to_drop):
    """Initializer for worker processes."""
    global _WARD_GDF, _AREA_CRS, _WORKER_COLUMNS_TO_DROP

    from shapely import wkb as shapely_wkb

    geoms = [shapely_wkb.loads(item) for item in ward_wkb_list]
    _WARD_GDF = gpd.GeoDataFrame(
        {OUT_WARD_NAME: ward_names, OUT_WARD_NO: ward_numbers},
        geometry=geoms,
        crs=ward_crs,
    ).copy()
    _AREA_CRS = area_crs
    _WORKER_COLUMNS_TO_DROP = list(columns_to_drop)


def _process_area_and_ward_file(args):
    """Worker: calculate Area and spatially join ward fields, then save final shapefile."""
    shp_path, output_folder, predicate = args
    fname = Path(shp_path).name
    out_path = Path(output_folder) / fname

    try:
        try:
            gdf = gpd.read_file(shp_path, engine="pyogrio")
        except Exception:
            gdf = gpd.read_file(shp_path)

        if gdf.empty:
            for col in _WORKER_COLUMNS_TO_DROP:
                if col in gdf.columns:
                    gdf = gdf.drop(columns=[col])
            gdf["Area"] = []
            gdf[OUT_WARD_NAME] = []
            gdf[OUT_WARD_NO] = []
            gdf.to_file(str(out_path), index=False)
            return True, f"{fname}: empty file saved"

        original_crs = str(gdf.crs)

        drop_cols = [col for col in _WORKER_COLUMNS_TO_DROP if col in gdf.columns]
        if drop_cols:
            gdf = gdf.drop(columns=drop_cols)

        # Area is calculated in the detected projected CRS.
        gdf_area, crs_action = ensure_projected(gdf, _AREA_CRS)
        gdf_area["Area"] = gdf_area.geometry.area

        ward = _WARD_GDF
        if ward.crs is None:
            return False, f"{fname}: ward CRS is undefined"

        # Match ward CRS for the spatial join and final shapefile output.
        if not same_crs(gdf_area.crs, ward.crs):
            gdf_join = gdf_area.to_crs(ward.crs)
            join_crs_note = f"join/output CRS changed to ward CRS {ward.crs}"
        else:
            gdf_join = gdf_area.copy()
            join_crs_note = "join/output CRS already matches ward CRS"

        # Avoid suffixes if re-running on already joined data.
        for col in [OUT_WARD_NAME, OUT_WARD_NO]:
            if col in gdf_join.columns:
                gdf_join = gdf_join.drop(columns=[col])

        bounds = gdf_join.total_bounds
        if not np.isfinite(bounds).all():
            joined = gdf_join.copy()
            joined[OUT_WARD_NAME] = None
            joined[OUT_WARD_NO] = None
            null_count = len(joined)
            dupe_count = 0
        else:
            candidate_idx = list(ward.sindex.intersection(bounds))
            if not candidate_idx:
                joined = gdf_join.copy()
                joined[OUT_WARD_NAME] = None
                joined[OUT_WARD_NO] = None
                null_count = len(joined)
                dupe_count = 0
            else:
                ward_candidates = ward.iloc[candidate_idx].copy()
                joined = gpd.sjoin(gdf_join, ward_candidates, how="left", predicate=predicate)

                if "index_right" in joined.columns:
                    joined = joined.drop(columns=["index_right"])

                n_before = len(joined)
                joined = joined[~joined.index.duplicated(keep="first")].copy()
                dupe_count = n_before - len(joined)

                for col in [OUT_WARD_NAME, OUT_WARD_NO]:
                    if col not in joined.columns:
                        joined[col] = None

                null_count = joined[OUT_WARD_NO].isna().sum()

        joined.to_file(str(out_path), index=False)

        area_total = joined["Area"].sum() if "Area" in joined.columns else 0
        return (
            True,
            f"{fname}: {len(joined):,} features | Area total={area_total:.2f} m² | "
            f"dropped={drop_cols or 'none'} | {crs_action} | {join_crs_note} | "
            f"dup ward matches dropped={dupe_count} | outside wards={null_count}",
        )

    except Exception as exc:
        return False, f"{fname}: {exc}"


def run_area_and_ward_join(
    input_folder: str,
    ward_shapefile_path: str,
    output_folder: str,
    ward_name_field: str,
    ward_no_field: str,
    predicate: str,
    max_workers: Optional[int] = None,
    clean_output_folder: bool = False,
) -> None:
    """Run merged Step 1 + Step 2 and write final shapefiles to output_folder."""
    validate_path_exists(input_folder, "Input slope shapefile folder")
    validate_path_exists(ward_shapefile_path, "Ward boundary shapefile")

    shapefiles = sorted(Path(input_folder).glob("*.shp"))
    if not shapefiles:
        raise FileNotFoundError(f"No .shp files found in: {input_folder}")

    workers = auto_workers(max_workers)
    prepare_output_folder(output_folder, clean=clean_output_folder)

    print_section("PIPELINE START")
    print(f"Input shapefiles : {input_folder}")
    print(f"Ward boundary   : {ward_shapefile_path}")
    print(f"Final shp folder : {output_folder}")
    print(f"Files found      : {len(shapefiles):,}")
    print(f"Workers          : {workers}")

    area_crs = detect_dominant_projected_crs(input_folder, shapefiles, workers)

    print_section("STEP 1B + STEP 2 — Calculating Area and joining wards")
    wards_gdf = gpd.read_file(ward_shapefile_path)
    missing = [col for col in [ward_name_field, ward_no_field] if col not in wards_gdf.columns]
    if missing:
        raise ValueError(
            f"Ward field(s) missing: {missing}\nAvailable columns: {list(wards_gdf.columns)}"
        )
    if wards_gdf.crs is None:
        raise ValueError("Ward boundary CRS is undefined. Please define CRS before running.")

    wards_small = gpd.GeoDataFrame(
        {
            OUT_WARD_NAME: wards_gdf[ward_name_field].tolist(),
            OUT_WARD_NO: wards_gdf[ward_no_field].tolist(),
        },
        geometry=wards_gdf.geometry,
        crs=wards_gdf.crs,
    )

    print(f"Area CRS         : {area_crs}")
    print(f"Ward/output CRS  : {wards_small.crs}")
    print(f"Join predicate   : {predicate}")

    ward_wkb = [geom.wkb for geom in wards_small.geometry]
    ward_names = wards_small[OUT_WARD_NAME].tolist()
    ward_numbers = wards_small[OUT_WARD_NO].tolist()

    task_args = [(str(shp), output_folder, predicate) for shp in shapefiles]

    success = 0
    failed = 0

    with tqdm(total=len(task_args), unit="file") as pbar:
        with concurrent.futures.ProcessPoolExecutor(
            max_workers=workers,
            initializer=_init_area_ward_worker,
            initargs=(ward_wkb, ward_names, ward_numbers, wards_small.crs, area_crs, COLUMNS_TO_DROP),
        ) as executor:
            futures = {executor.submit(_process_area_and_ward_file, arg): arg[0] for arg in task_args}
            for future in concurrent.futures.as_completed(futures):
                ok, msg = future.result()
                if ok:
                    success += 1
                    pbar.set_description(f"✓ {Path(msg.split(':')[0]).name}")
                else:
                    failed += 1
                    tqdm.write(f"  ✗ {msg}")
                pbar.update(1)
                tqdm.write(f"  {'✓' if ok else '✗'} {msg}")

    print(f"\nArea + ward join completed: {success} succeeded | {failed} failed")
    print(f"Final shapefiles saved in: {output_folder}")

    if failed:
        raise RuntimeError(f"{failed} shapefile(s) failed during area + ward join step.")


# =============================================================================
# Step 3: ward-tile mapping CSV
# =============================================================================

def _read_ward_tile_from_shapefile(shp_path: str):
    shp = Path(shp_path)
    try:
        df = read_attributes_only(shp_path)
        columns = list(df.columns)

        ward_name_col = find_col(columns, "ward_name", "ward_nam", "name")
        ward_no_col = find_col(columns, "ward_no", "ward_num")
        tile_col = find_col(columns, "tile_id", "tileid", "tile_no")

        if not all([ward_name_col, ward_no_col, tile_col]):
            missing = [
                name for name, col in [
                    ("Ward_Name", ward_name_col),
                    ("Ward_No", ward_no_col),
                    ("Tile_ID", tile_col),
                ] if col is None
            ]
            return False, f"{shp.name}: missing columns {missing} | available: {columns}", None

        result = (
            df[[ward_name_col, ward_no_col, tile_col]]
            .drop_duplicates()
            .rename(columns={
                ward_name_col: "Ward_Name",
                ward_no_col: "Ward_Number",
                tile_col: "Tile_ID",
            })
        )
        return True, shp.name, result

    except Exception as exc:
        return False, f"{shp.name}: {exc}", None


def build_ward_tile_mapping(shape_folder: str, out_csv: str, max_workers: Optional[int] = None) -> pd.DataFrame:
    print_section("STEP 3 — Creating unique ward-tile CSV")

    shapefiles = sorted(Path(shape_folder).glob("*.shp"))
    if not shapefiles:
        raise FileNotFoundError(f"No final shapefiles found in: {shape_folder}")

    workers = auto_workers(max_workers)
    all_frames = []
    failed = []

    print(f"Final shapefile folder: {shape_folder}")
    print(f"CSV output            : {out_csv}")
    print(f"Files found           : {len(shapefiles):,}")
    print(f"Workers               : {workers}")

    with tqdm(total=len(shapefiles), unit="file") as pbar:
        with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_read_ward_tile_from_shapefile, str(shp)): shp.name for shp in shapefiles}
            for future in concurrent.futures.as_completed(futures):
                ok, msg, df = future.result()
                if ok:
                    all_frames.append(df)
                    pbar.set_description(f"✓ {msg}")
                else:
                    failed.append(msg)
                    tqdm.write(f"  ✗ {msg}")
                pbar.update(1)

    if not all_frames:
        raise RuntimeError("No usable shapefiles found for ward-tile CSV.")

    combined = (
        pd.concat(all_frames, ignore_index=True)
        .drop_duplicates()
        .sort_values(["Ward_Name", "Ward_Number", "Tile_ID"])
        .reset_index(drop=True)
    )

    combined.insert(0, "S.No", range(1, len(combined) + 1))
    combined = combined.rename(columns={
        "Ward_Name": "Ward Name",
        "Ward_Number": "Ward Number",
        "Tile_ID": "Tile ID",
    })

    Path(out_csv).parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(out_csv, index=False, encoding="utf-8-sig")

    print(f"Rows written: {len(combined):,}")
    print(f"Saved CSV   : {out_csv}")
    if failed:
        print(f"Skipped files: {len(failed)}")

    return combined


# =============================================================================
# Step 4: polygon CSV mapped with Ward_Name and Ward_No
# =============================================================================

def _lookup_from_one_shapefile(shp_path: str):
    shp = Path(shp_path)
    try:
        df = read_attributes_only(shp_path)
        columns = list(df.columns)

        poly_col = "Poly_ID" if "Poly_ID" in columns else find_col(columns, "poly_id", "polyid")
        ward_name_col = find_col(columns, "ward_name", "ward_nam", "name")
        ward_no_col = find_col(columns, "ward_no", "ward_num")

        if not poly_col:
            return False, f"{shp.name}: Poly_ID missing", None
        if not ward_name_col:
            return False, f"{shp.name}: Ward_Name/Name missing", None
        if not ward_no_col:
            return False, f"{shp.name}: Ward_No missing", None

        tmp = df[[poly_col, ward_name_col, ward_no_col]].copy()
        tmp["Poly_ID_norm"] = tmp[poly_col].apply(normalize_id)
        tmp = tmp.rename(columns={
            ward_name_col: "Ward_Name",
            ward_no_col: "Ward_No",
        })

        return True, shp.name, tmp[["Poly_ID_norm", "Ward_Name", "Ward_No"]]

    except Exception as exc:
        return False, f"{shp.name}: {exc}", None


def build_lookup_from_final_shapefiles(shp_folder: str, max_workers: Optional[int] = None) -> pd.DataFrame:
    shapefiles = sorted(Path(shp_folder).rglob("*.shp"))
    if not shapefiles:
        raise FileNotFoundError(f"No shapefiles found in {shp_folder}")

    workers = auto_workers(max_workers)
    results = []
    failed = []

    print(f"Building Poly_ID → Ward lookup from {len(shapefiles):,} shapefiles")

    with tqdm(total=len(shapefiles), unit="file") as pbar:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_lookup_from_one_shapefile, str(shp)): shp.name for shp in shapefiles}
            for future in as_completed(futures):
                ok, msg, df = future.result()
                if ok:
                    results.append(df)
                    pbar.set_description(f"✓ {msg}")
                else:
                    failed.append(msg)
                    tqdm.write(f"  ✗ {msg}")
                pbar.update(1)

    if not results:
        raise RuntimeError("No valid shapefiles found for Poly_ID lookup.")

    lookup_df = (
        pd.concat(results, ignore_index=True)
        .dropna(subset=["Poly_ID_norm"])
        .drop_duplicates(subset=["Poly_ID_norm"])
    )

    print(f"Unique Poly_ID values collected: {len(lookup_df):,}")
    if failed:
        print(f"Skipped files: {len(failed)}")

    return lookup_df


def map_polygon_csv_with_wards(
    shp_folder: str,
    csv_path: str,
    output_csv_path: str,
    max_workers: Optional[int] = None,
) -> pd.DataFrame:
    print_section("STEP 4 — Creating polygon CSV with wards")

    validate_path_exists(csv_path, "Input polygon CSV")

    df_csv = pd.read_csv(csv_path)
    if "polygon_code" not in df_csv.columns:
        raise ValueError(f"polygon_code column not found in CSV: {csv_path}")

    print(f"Input CSV rows: {len(df_csv):,}")
    df_csv["polygon_code_norm"] = df_csv["polygon_code"].apply(normalize_id)

    lookup_df = build_lookup_from_final_shapefiles(shp_folder, max_workers=max_workers)

    df_out = df_csv.merge(
        lookup_df,
        left_on="polygon_code_norm",
        right_on="Poly_ID_norm",
        how="left",
    )

    df_out = df_out.drop(columns=["polygon_code_norm", "Poly_ID_norm"], errors="ignore")

    matches = df_out["Ward_Name"].notna().sum() if "Ward_Name" in df_out.columns else 0
    match_rate = (matches / len(df_out) * 100) if len(df_out) else 0

    Path(output_csv_path).parent.mkdir(parents=True, exist_ok=True)
    df_out.to_csv(output_csv_path, index=False, encoding="utf-8-sig")

    print(f"Matched rows: {matches:,}")
    print(f"Total rows  : {len(df_out):,}")
    print(f"Match rate  : {match_rate:.2f}%")
    print(f"Saved CSV   : {output_csv_path}")

    return df_out


# =============================================================================
# Main pipeline
# =============================================================================

def run_full_pipeline() -> None:
    """Run all four original scripts as one merged workflow."""
    workers = auto_workers(MAX_WORKERS)

    run_area_and_ward_join(
        input_folder=INPUT_SLOPE_SHP_FOLDER,
        ward_shapefile_path=WARD_BOUNDARY_SHP,
        output_folder=FINAL_SHP_OUTPUT_FOLDER,
        ward_name_field=WARD_NAME_FIELD,
        ward_no_field=WARD_NO_FIELD,
        predicate=SPATIAL_JOIN_PREDICATE,
        max_workers=workers,
        clean_output_folder=CLEAN_FINAL_OUTPUT_FOLDER,
    )

    ward_tile_df = build_ward_tile_mapping(
        shape_folder=FINAL_SHP_OUTPUT_FOLDER,
        out_csv=OUT_WARD_TILE_CSV,
        max_workers=workers,
    )

    polygon_ward_df = map_polygon_csv_with_wards(
        shp_folder=FINAL_SHP_OUTPUT_FOLDER,
        csv_path=INPUT_POLYGON_CSV,
        output_csv_path=OUT_POLYGON_WITH_WARDS_CSV,
        max_workers=workers,
    )

    print_section("ALL TASKS COMPLETED")
    print(f"Final shapefiles folder: {FINAL_SHP_OUTPUT_FOLDER}")
    print(f"CSV 1 ward-tile       : {OUT_WARD_TILE_CSV} | rows={len(ward_tile_df):,}")
    print(f"CSV 2 polygon-wards   : {OUT_POLYGON_WITH_WARDS_CSV} | rows={len(polygon_ward_df):,}")


if __name__ == "__main__":
    multiprocessing.freeze_support()  # required for ProcessPoolExecutor on Windows
    run_full_pipeline()
