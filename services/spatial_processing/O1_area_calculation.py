import os
import geopandas as gpd
from pathlib import Path
import argparse
from pathlib import Path

def process_shapefiles_auto_crs(input_folder, output_folder):
    """
    Process all shapefiles in input folder:
    - Drop specified columns
    - Calculate area in square meters using the shapefile's own CRS when possible
    - Save to output folder
    """
    
    # Create output folder if it doesn't exist
    Path(output_folder).mkdir(parents=True, exist_ok=True)
    
    # Columns to drop
    columns_to_drop = ['RoofMatr', 'Min3DL', 'Max3DL', 'Area3D']
    
    # Find all shapefiles in the input folder
    shapefiles = [f for f in os.listdir(input_folder) if f.endswith('.shp')]
    
    print(f"Found {len(shapefiles)} shapefiles to process")
    
    processed_count = 0
    
    for shp_file in shapefiles:
        try:
            # Full path to shapefile
            input_path = os.path.join(input_folder, shp_file)
            
            print(f"\nProcessing: {shp_file}")
            
            # Read shapefile
            gdf = gpd.read_file(input_path)
            
            # Display CRS information
            print(f"  Original CRS: {gdf.crs}")
            
            # Drop specified columns if they exist
            existing_columns_to_drop = [col for col in columns_to_drop if col in gdf.columns]
            if existing_columns_to_drop:
                print(f"  Dropping columns: {existing_columns_to_drop}")
                gdf = gdf.drop(columns=existing_columns_to_drop)
            else:
                print("  No specified columns found to drop")
            
            # Calculate area based on CRS type
            if gdf.crs is None:
                print("  WARNING: No CRS defined! Area calculation may not be accurate.")
                # Calculate area anyway but warn user
                gdf['Area'] = gdf.geometry.area
                print("  ⚠️  Area calculated without CRS - values may not be in square meters")
                
            elif gdf.crs.is_geographic:
                print("  Geographic CRS detected - converting to UTM for accurate area calculation")
                # Convert to appropriate UTM zone based on data extent
                gdf_projected = convert_to_utm(gdf)
                gdf['Area'] = gdf_projected.geometry.area
                print(f"  Used CRS for area calculation: {gdf_projected.crs}")
                
            else:
                # Already in projected CRS - use directly for area calculation
                print(f"  Projected CRS detected - using directly for area calculation")
                gdf['Area'] = gdf.geometry.area
                print(f"  Area calculated using original CRS: {gdf.crs}")
            
            # Output path
            output_path = os.path.join(output_folder, shp_file)
            
            # Save processed shapefile
            gdf.to_file(output_path)
            
            # Display area statistics
            area_stats = gdf['Area'].describe()
            print(f"  Area statistics (m²):")
            print(f"    Min: {area_stats['min']:.2f}")
            print(f"    Max: {area_stats['max']:.2f}")
            print(f"    Mean: {area_stats['mean']:.2f}")
            print(f"    Total: {gdf['Area'].sum():.2f}")
            
            processed_count += 1
            print(f"  ✓ Successfully processed: {shp_file}")
            
        except Exception as e:
            print(f"  ✗ Error processing {shp_file}: {str(e)}")
    
    print(f"\n{'='*50}")
    print(f"Processing complete! {processed_count}/{len(shapefiles)} files processed successfully.")
    print(f"Output saved to: {output_folder}")

def convert_to_utm(gdf):
    """
    Convert GeoDataFrame to appropriate UTM zone based on its extent
    """
    # Get the centroid of the entire dataset
    bounds = gdf.total_bounds
    centroid_lon = (bounds[0] + bounds[2]) / 2
    centroid_lat = (bounds[1] + bounds[3]) / 2
    
    # Determine UTM zone
    utm_zone = get_utm_zone(centroid_lon, centroid_lat)
    
    try:
        return gdf.to_crs(utm_zone)
    except Exception as e:
        print(f"    Failed to convert to {utm_zone}, using EPSG:3857 as fallback")
        return gdf.to_crs('EPSG:3857')

def get_utm_zone(lon, lat):
    """
    Determine appropriate UTM zone for given coordinates
    """
    zone = int((lon + 180) / 6) + 1
    hemisphere = 'north' if lat >= 0 else 'south'
    epsg = 32600 + zone if hemisphere == 'north' else 32700 + zone
    return f'EPSG:{epsg}'

def check_shapefile_crs(input_folder):
    """
    Helper function to check CRS of all shapefiles before processing
    """
    print("Checking CRS for all shapefiles:")
    print("-" * 40)
    
    shapefiles = [f for f in os.listdir(input_folder) if f.endswith('.shp')]
    
    crs_info = {}
    
    for shp_file in shapefiles:
        input_path = os.path.join(input_folder, shp_file)
        gdf = gpd.read_file(input_path)
        
        crs_name = "Unknown" if gdf.crs is None else str(gdf.crs)
        is_geographic = "Yes" if gdf.crs and gdf.crs.is_geographic else "No"
        
        print(f"{shp_file}:")
        print(f"  CRS: {crs_name}")
        print(f"  Geographic: {is_geographic}")
        print()
        
        # Collect statistics
        if crs_name not in crs_info:
            crs_info[crs_name] = 0
        crs_info[crs_name] += 1
    
    print("CRS Summary:")
    for crs, count in crs_info.items():
        print(f"  {crs}: {count} files")

# Usage example
if __name__ == "__main__":
    args_obj = argparse.ArgumentParser()
    args_obj.add_argument("--input_file")
    args_obj.add_argument("--output_file")
    args_obj.add_argument("--check_first")
    args = args_obj.parse_args()
    # Set your input and output folders
    input_folder = Path(args.input_file)  # Change this
    output_folder = Path(args.output_file)   # Change this
    check_first = bool(args.check_first)
    
    # First, check the CRS of all files (optional)
    # print("Would you like to check CRS information first? (y/n)")
    # check_first = input().strip().lower()
    
    if check_first:
        check_shapefile_crs(input_folder)
        print("\n" + "="*50)
        print("Starting processing...")
        print("="*50)
    
    # Process all shapefiles
    print("---Processing all shapefiles---")
    process_shapefiles_auto_crs(input_folder, output_folder)