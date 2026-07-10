
import geopandas as gpd
import os
from pathlib import Path
import concurrent.futures
from tqdm import tqdm
import argparse
from pathlib import Path

def threaded_ward_join(
    ward_shapefile_path,
    input_folder,
    output_folder,
    max_workers=10,
    ward_name_field="Ward_Name",
    ward_no_field="Ward_No",
    predicate="intersects",
):
    """
    Thread-based concurrent processing (best for I/O-bound work like reading/writing many shapefiles).

    Joins each input shapefile with ward polygons and writes the result (same filename) to output_folder.

    Ward fields used (from your screenshot):
      - Ward_Name
      - WARD_NO
    Output fields created:
      - Ward_Name   (from ward layer)
      - Ward_Number (renamed from WARD_NO)
    """

    print("Loading ward boundaries...")
    wards_gdf = gpd.read_file(ward_shapefile_path)

    # Basic validations
    if "geometry" not in wards_gdf.columns:
        raise ValueError("Ward shapefile has no geometry column.")

    if ward_name_field not in wards_gdf.columns or ward_no_field not in wards_gdf.columns:
        raise ValueError(
            f"Expected ward fields not found.\n"
            f"Missing: {[c for c in [ward_name_field, ward_no_field] if c not in wards_gdf.columns]}\n"
            f"Available columns: {list(wards_gdf.columns)}"
        )

    # Keep only required ward columns (smaller = faster)
    wards_small = wards_gdf[[ward_name_field, ward_no_field, "geometry"]].copy()

    # Create output folder
    os.makedirs(output_folder, exist_ok=True)

    # Collect all shapefiles
    shapefiles = list(Path(input_folder).glob("*.shp"))
    print(f"Processing {len(shapefiles)} files with {max_workers} threads...")

    def process_file(shp_path: Path):
        try:
            gdf = gpd.read_file(shp_path)

            # Ensure CRS match
            if gdf.crs is None:
                return False, f"{shp_path.name}: Input shapefile CRS is None/undefined."
            if wards_small.crs is None:
                return False, f"{shp_path.name}: Ward shapefile CRS is None/undefined."

            if gdf.crs != wards_small.crs:
                gdf = gdf.to_crs(wards_small.crs)

            # Spatial join
            joined = gpd.sjoin(
                gdf,
                wards_small,
                how="left",
                predicate=predicate,
            )

            # Rename ward number field in output
            # (ward_name_field stays as Ward_Name already)
            joined = joined.rename(columns={ward_no_field: "Ward_Number"})

            # Drop GeoPandas join helper column
            if "index_right" in joined.columns:
                joined = joined.drop(columns=["index_right"])

            # If multiple wards intersect the same feature, keep first match
            # (If you want a different rule, tell me)
            joined = joined[~joined.index.duplicated(keep="first")]

            # Write output
            out_path = Path(output_folder) / shp_path.name
            joined.to_file(out_path)

            return True, shp_path.name

        except Exception as e:
            return False, f"{shp_path.name}: {e}"

    success_count = 0
    with tqdm(total=len(shapefiles)) as pbar:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_file = {executor.submit(process_file, shp): shp for shp in shapefiles}

            for future in concurrent.futures.as_completed(future_to_file):
                ok, msg = future.result()
                if ok:
                    success_count += 1
                    pbar.set_description(f"Processed: {msg}")
                else:
                    print(f"\nError: {msg}")
                pbar.update(1)

    print(f"\nCompleted: {success_count}/{len(shapefiles)} files successfully processed")


# ===== Usage =====

if __name__=="__main__":
    args_obj = argparse.ArgumentParser()
    args_obj.add_argument("--ward_shapefile_path")
    args_obj.add_argument("--input_folder")
    args_obj.add_argument("--output_folder")
    args_obj.add_argument("--max_workers")
    args_obj.add_argument("--ward_name_field")
    args_obj.add_argument("--ward_no_field")
    args_obj.add_argument("--predicate")
    args = args_obj.parse_args()
    
    
    
threaded_ward_join(
    ward_shapefile_path=Path(args.ward_shapefile_path),
    input_folder=Path(args.input_folder),
    output_folder=Path(args.output_folder),
    max_workers=int(args.max_workers),
    ward_name_field=args.ward_name_field,
    ward_no_field=args.ward_no_field,
    predicate=args.predicate
)