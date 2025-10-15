#!/usr/bin/env python3
"""
Valhalla Isochrone Generator Script

This script reads points from a GPKG file, generates 60-minute isochrones 
for each point using a Valhalla instance, and merges them into a single polygon.

Requirements:
- geopandas
- requests
- shapely

Install with: pip install geopandas requests shapely
"""

import geopandas as gpd
import requests
import json
from shapely.geometry import shape
from shapely.ops import unary_union
import logging
from pathlib import Path
import argparse
from typing import List, Optional
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Veterinary access costing options for rural Australia
VET_COSTING_OPTIONS = {
    "ignore_access": True,
    "ignore_restrictions": True, 
    "ignore_oneways": True,
    "ignore_closures": True,
    "exclude_unpaved": 0,
    "use_tracks": 1,
    "use_trails": 0.5,
    "private_access_penalty": 0,
    "gate_penalty": 0,
    "gate_cost": 0,
    "service_penalty": 0,
    "use_ferry": 1
}

class ValhallaIsochrone:
    def __init__(self, valhalla_url: str = "http://localhost:8002"):
        """
        Initialize Valhalla isochrone generator.
        
        Args:
            valhalla_url: Base URL of Valhalla instance
        """
        self.valhalla_url = valhalla_url.rstrip('/')
        self.isochrone_endpoint = f"{self.valhalla_url}/isochrone"
        
    def generate_isochrone(self, lat: float, lon: float, time_minutes: int = 60,
                          costing: str = "auto", denoise: float = 0.01, 
                          generalize: int = 30, costing_options: Optional[dict] = None) -> Optional[dict]:
        """
        Generate isochrone for a single point.
        
        Args:
            lat: Latitude
            lon: Longitude  
            time_minutes: Travel time in minutes
            costing: Valhalla costing model (auto, bicycle, pedestrian, etc.)
            denoise: Noise reduction factor
            generalize: Generalization distance in meters
            costing_options: Additional costing options for the routing model
            
        Returns:
            GeoJSON feature dict or None if failed
        """
        payload = {
            "locations": [{"lat": lat, "lon": lon}],
            "costing": costing,
            "contours": [{"time": time_minutes}],
            "polygons": True,
            "denoise": denoise,
            "generalize": generalize
        }
        
        # Add costing options if provided
        if costing_options:
            payload["costing_options"] = {costing: costing_options}

        # Debug: Log the full request payload for first request
        if not hasattr(self, '_logged_payload'):
            logger.info(f"Sample Valhalla request payload: {json.dumps(payload, indent=2)}")
            self._logged_payload = True

        try:
            response = requests.post(
                self.isochrone_endpoint,
                headers={"Content-Type": "application/json"},
                data=json.dumps(payload),
                timeout=30
            )
            response.raise_for_status()
            
            geojson_data = response.json()
            
            # Return the first (and should be only) feature
            if geojson_data.get('features'):
                return geojson_data['features'][0]
            else:
                logger.warning(f"No isochrone generated for point ({lat}, {lon})")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed for point ({lat}, {lon}): {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response for point ({lat}, {lon}): {e}")
            return None
            
    def process_points_from_gpkg(self, gpkg_path: str, time_minutes: int = 60,
                                costing: str = "auto", delay_seconds: float = 0.1,
                                costing_options: Optional[dict] = None, max_workers: int = 1) -> List[dict]:
        """
        Process all points from a GPKG file and generate isochrones.

        Args:
            gpkg_path: Path to GPKG file
            time_minutes: Travel time in minutes
            costing: Valhalla costing model
            delay_seconds: Delay between requests to avoid overwhelming server (ignored if max_workers > 1)
            costing_options: Additional costing options for the routing model
            max_workers: Number of concurrent threads (1 = sequential processing)

        Returns:
            List of GeoJSON feature dictionaries
        """
        # Read GPKG
        try:
            gdf = gpd.read_file(gpkg_path)
        except Exception as e:
            logger.error(f"Failed to read GPKG file {gpkg_path}: {e}")
            return []

        # Ensure CRS is WGS84 for Valhalla
        if gdf.crs != 'EPSG:4326':
            logger.info(f"Converting from {gdf.crs} to EPSG:4326")
            gdf = gdf.to_crs('EPSG:4326')

        # Extract coordinates
        gdf['lon'] = gdf.geometry.x
        gdf['lat'] = gdf.geometry.y

        logger.info(f"Processing {len(gdf)} points from {gpkg_path}")

        if max_workers > 1:
            return self._process_parallel(gdf, time_minutes, costing, costing_options, max_workers)
        else:
            return self._process_sequential(gdf, time_minutes, costing, costing_options, delay_seconds)

    def _process_sequential(self, gdf, time_minutes: int, costing: str,
                           costing_options: Optional[dict], delay_seconds: float) -> List[dict]:
        """Sequential processing (original implementation)."""
        isochrones = []

        for idx, row in gdf.iterrows():
            logger.info(f"Processing point {idx + 1}/{len(gdf)}: ({row['lat']:.4f}, {row['lon']:.4f})")

            isochrone = self.generate_isochrone(
                lat=row['lat'],
                lon=row['lon'],
                time_minutes=time_minutes,
                costing=costing,
                costing_options=costing_options
            )

            if isochrone:
                # Add original point info to properties
                isochrone['properties']['original_point_id'] = idx
                isochrone['properties']['original_lat'] = row['lat']
                isochrone['properties']['original_lon'] = row['lon']
                isochrones.append(isochrone)
            elif idx == 0:
                # If the first point fails, assume Valhalla is down and abort
                logger.error("First point failed - assuming Valhalla service is unavailable. Aborting processing.")
                return []

            # Small delay to be nice to the server
            if delay_seconds > 0:
                time.sleep(delay_seconds)

        logger.info(f"Successfully generated {len(isochrones)} isochrones out of {len(gdf)} points")
        return isochrones

    def _process_parallel(self, gdf, time_minutes: int, costing: str,
                         costing_options: Optional[dict], max_workers: int) -> List[dict]:
        """Parallel processing using ThreadPoolExecutor."""
        logger.info(f"Using {max_workers} concurrent threads")

        isochrones = []
        failed_count = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_point = {
                executor.submit(
                    self.generate_isochrone,
                    row['lat'], row['lon'],
                    time_minutes, costing,
                    costing_options=costing_options
                ): (idx, row)
                for idx, row in gdf.iterrows()
            }

            # Collect results as they complete
            completed = 0
            for future in as_completed(future_to_point):
                idx, row = future_to_point[future]
                completed += 1

                try:
                    isochrone = future.result()

                    if isochrone:
                        # Add original point info to properties
                        isochrone['properties']['original_point_id'] = idx
                        isochrone['properties']['original_lat'] = row['lat']
                        isochrone['properties']['original_lon'] = row['lon']
                        isochrones.append(isochrone)
                        logger.info(f"Completed {completed}/{len(gdf)}: Point {idx} ({row['lat']:.4f}, {row['lon']:.4f})")
                    else:
                        failed_count += 1
                        logger.warning(f"Failed {completed}/{len(gdf)}: Point {idx} ({row['lat']:.4f}, {row['lon']:.4f})")

                except Exception as e:
                    failed_count += 1
                    logger.error(f"Exception for point {idx} ({row['lat']:.4f}, {row['lon']:.4f}): {e}")

        logger.info(f"Successfully generated {len(isochrones)} isochrones out of {len(gdf)} points ({failed_count} failed)")
        return isochrones
        
    def merge_isochrones(self, isochrones: List[dict]) -> Optional[dict]:
        """
        Merge multiple isochrone polygons into a single polygon.
        
        Args:
            isochrones: List of GeoJSON feature dictionaries
            
        Returns:
            Single GeoJSON feature with merged polygon or None if failed
        """
        if not isochrones:
            logger.warning("No isochrones to merge")
            return None
            
        try:
            # Convert GeoJSON features to Shapely geometries
            polygons = []
            for iso in isochrones:
                geom = shape(iso['geometry'])
                if geom.is_valid:
                    polygons.append(geom)
                else:
                    logger.warning("Invalid geometry found, attempting to fix")
                    fixed_geom = geom.buffer(0)  # Often fixes invalid geometries
                    if fixed_geom.is_valid:
                        polygons.append(fixed_geom)
                        
            if not polygons:
                logger.error("No valid polygons to merge")
                return None
                
            # Merge all polygons
            logger.info(f"Merging {len(polygons)} polygons")
            merged_polygon = unary_union(polygons)
            
            # Create GeoJSON feature
            merged_feature = {
                "type": "Feature",
                "properties": {
                    "merged_isochrones_count": len(polygons),
                    "travel_time_minutes": isochrones[0]['properties'].get('contour', 60),
                    "costing_model": "auto"  # Could be extracted from original if needed
                },
                "geometry": merged_polygon.__geo_interface__
            }
            
            return merged_feature
            
        except Exception as e:
            logger.error(f"Failed to merge isochrones: {e}")
            return None
            
    def save_output(self, feature: dict, output_path: str) -> bool:
        """
        Save feature to file (GPKG or GeoJSON based on extension).

        Args:
            feature: GeoJSON feature dictionary
            output_path: Output file path

        Returns:
            True if successful, False otherwise
        """
        try:
            output_path_obj = Path(output_path)

            # Default to GPKG if no extension provided, otherwise check extension
            if output_path_obj.suffix.lower() == '.geojson':
                # Save as GeoJSON
                geojson_data = {
                    "type": "FeatureCollection",
                    "features": [feature] if isinstance(feature, dict) and feature.get('type') == 'Feature' else feature
                }

                with open(output_path, 'w') as f:
                    json.dump(geojson_data, f, indent=2)

                logger.info(f"Saved merged isochrone to {output_path} (GeoJSON format)")
            else:
                # Save as GPKG (default, or if .gpkg extension specified)
                # Add .gpkg extension if no extension provided
                if not output_path_obj.suffix:
                    output_path = str(output_path_obj) + '.gpkg'

                geom = shape(feature['geometry'])
                gdf = gpd.GeoDataFrame([feature['properties']], geometry=[geom], crs='EPSG:4326')
                gdf.to_file(output_path, driver='GPKG')
                logger.info(f"Saved merged isochrone to {output_path} (GPKG format)")

            return True

        except Exception as e:
            logger.error(f"Failed to save output to {output_path}: {e}")
            return False


def main():
    parser = argparse.ArgumentParser(description="Generate and merge isochrones from GPKG points")
    parser.add_argument("gpkg_path", help="Path to input GPKG file")
    parser.add_argument("-o", "--output", default="merged_isochrone.gpkg", 
                       help="Output file path - GPKG or GeoJSON based on extension (default: merged_isochrone.gpkg)")
    parser.add_argument("-u", "--url", default="http://localhost:8002",
                       help="Valhalla server URL (default: http://localhost:8002)")
    parser.add_argument("-t", "--time", type=int, default=60,
                       help="Travel time in minutes (default: 60)")
    parser.add_argument("-c", "--costing", default="auto",
                       help="Valhalla costing model (default: auto)")
    parser.add_argument("-d", "--delay", type=float, default=0.1,
                       help="Delay between requests in seconds (default: 0.1, ignored if --threads > 1)")
    parser.add_argument("--threads", type=int, default=1,
                       help="Number of concurrent threads for parallel processing (default: 1). Recommended: 10-20 for local Valhalla")
    parser.add_argument("--vet-access", action="store_true",
                       help="Use veterinary access options (ignore gates, private roads, etc.)")
    
    args = parser.parse_args()
    
    # Validate input file
    if not Path(args.gpkg_path).exists():
        logger.error(f"Input file does not exist: {args.gpkg_path}")
        return 1
        
    # Initialize generator
    generator = ValhallaIsochrone(valhalla_url=args.url)
    
    # Determine costing options
    costing_options = VET_COSTING_OPTIONS if args.vet_access else None
    if args.vet_access:
        logger.info("Using veterinary access options (ignoring gates, private roads, etc.)")
    
    # Process points
    isochrones = generator.process_points_from_gpkg(
        gpkg_path=args.gpkg_path,
        time_minutes=args.time,
        costing=args.costing,
        delay_seconds=args.delay,
        costing_options=costing_options,
        max_workers=args.threads
    )
    
    if not isochrones:
        logger.error("No isochrones were generated successfully")
        return 1
        
    # Merge isochrones
    merged_isochrone = generator.merge_isochrones(isochrones)
    
    if not merged_isochrone:
        logger.error("Failed to merge isochrones")
        return 1
        
    # Save result
    if generator.save_output(merged_isochrone, args.output):
        logger.info(f"Process completed successfully. Merged isochrone saved to {args.output}")
        return 0
    else:
        logger.error("Failed to save merged isochrone")
        return 1


if __name__ == "__main__":
    exit(main())