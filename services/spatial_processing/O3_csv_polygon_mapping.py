from os import path

import pandas as pd
import geopandas as gpd
from pathlib import Path
import warnings
import argparse
from pathlib import Path

warnings.filterwarnings("ignore")


def normalize_id(x):
    """Normalize Poly_ID / polygon_code for safe matching"""
    if pd.isna(x):
        return None
    s = str(x).strip()
    if s == "" or s.lower() in {"none", "nan"}:
        return None
    try:
        f = float(s)
        if f.is_integer():
            return str(int(f))
        return str(f)
    except Exception:
        return s


def build_lookup_from_shapefiles(shp_folder):
    """
    Build lookup table:
    Poly_ID_norm -> Ward_Name, Ward_Numbe
    Uses 'Name' if 'Ward_Name' is missing
    """
    shp_folder = Path(shp_folder)
    shapefiles = list(shp_folder.rglob("*.shp"))

    if not shapefiles:
        raise FileNotFoundError(f"No shapefiles found in {shp_folder}")

    print(f"Found {len(shapefiles)} shapefiles in {shp_folder}")

    records = []
    total_polygons = 0

    for i, shp in enumerate(shapefiles, 1):
        print(f"Processing shapefile {i}/{len(shapefiles)}: {shp.name}")

        try:
            gdf = gpd.read_file(shp)
            total_polygons += len(gdf)

            # Required base columns
            if "Poly_ID" not in gdf.columns or "Ward_Numbe" not in gdf.columns:
                print(f"  ❌ Skipping {shp.name} (missing Poly_ID or Ward_Numbe)")
                continue

            # Ward name column logic
            if "Ward_Name" in gdf.columns:
                ward_name_col = "Ward_Name"
            elif "Name" in gdf.columns:
                ward_name_col = "Name"
            else:
                print(f"  ❌ Skipping {shp.name} (no Ward_Name / Name column)")
                continue

            # Build lookup rows
            tmp = gdf[["Poly_ID", ward_name_col, "Ward_Numbe"]].copy()
            tmp["Poly_ID_norm"] = tmp["Poly_ID"].apply(normalize_id)

            tmp.rename(columns={ward_name_col: "Ward_Name"}, inplace=True)

            records.append(
                tmp[["Poly_ID_norm", "Ward_Name", "Ward_Numbe"]]
            )

        except Exception as e:
            print(f"  ❌ Error processing {shp.name}: {e}")

    if not records:
        raise RuntimeError("No valid shapefile data found")

    lookup_df = (
        pd.concat(records, ignore_index=True)
        .dropna(subset=["Poly_ID_norm"])
        .drop_duplicates(subset=["Poly_ID_norm"])
    )

    print(f"\nProcessed {total_polygons} polygons")
    print(f"Unique Poly_IDs collected: {len(lookup_df)}")

    return lookup_df


def process_shapefiles_and_csv(shp_folder, csv_path, output_csv_path):
    print(f"Reading CSV file2: {csv_path}")
    df_csv = pd.read_csv(csv_path)

    if "polygon_code" not in df_csv.columns:
        raise ValueError("polygon_code column not found in CSV")

    print(f"CSV loaded with {len(df_csv)} rows")

    # Normalize polygon_code
    df_csv["polygon_code_norm"] = df_csv["polygon_code"].apply(normalize_id)

    # Build lookup from shapefiles
    lookup_df = build_lookup_from_shapefiles(shp_folder)

    print("\nMerging CSV with shapefile lookup...")
    df_out = df_csv.merge(
        lookup_df,
        left_on="polygon_code_norm",
        right_on="Poly_ID_norm",
        how="left"
    )

    # Cleanup
    df_out.drop(columns=["polygon_code_norm", "Poly_ID_norm"], inplace=True)

    matches = df_out["Ward_Name"].notna().sum()
    print(f"\nMatching complete!")
    print(f"Matched {matches} / {len(df_out)} rows")
    print(f"Match rate: {matches / len(df_out) * 100:.2f}%")

    df_out.to_csv(output_csv_path, index=False)
    print(f"\nOutput written to: {output_csv_path}")

    return df_out


def main(shp_folder, csv_path, output_csv_path):
    shp_folder = Path(shp_folder)
    csv_path = Path(csv_path)
    output_csv_path = Path(output_csv_path)
    df = process_shapefiles_and_csv(shp_folder, csv_path, output_csv_path)
    
    print("\nSample output:")
    print(df[["polygon_code", "Ward_Name", "Ward_Numbe"]].head(10))


if __name__ == "__main__":
    args_obj = argparse.ArgumentParser()
    args_obj.add_argument("--shp_folder")
    args_obj.add_argument("--csv_path")
    args_obj.add_argument("--output_csv_path")
    args = args_obj.parse_args()
    
    shp_folder, csv_path, output_csv_path = args.shp_folder, args.csv_path, args.output_csv_path
    main(shp_folder, csv_path, output_csv_path)