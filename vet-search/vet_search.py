import logging
import geopandas as gpd
import pandas as pd
import time
from typing import Dict, List, Optional
from datetime import datetime
import json
from pathlib import Path
import requests
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class VeterinarySearcher:
    """Search for veterinary practices using Google Places API"""
    
    def __init__(self, api_key: Optional[str] = None, delay: Optional[float] = None):
        """
        Initialise the searcher
        
        Args:
            api_key: Google Places API key (defaults to env var)
            delay: Seconds between API calls (defaults to env var)
        """
        self.api_key = api_key or os.getenv('GOOGLE_PLACES_API_KEY')
        self.delay = delay or float(os.getenv('API_DELAY_SECONDS', '0.2'))
        
        if not self.api_key:
            raise ValueError("Google Places API key must be provided via parameter or GOOGLE_PLACES_API_KEY env var")
        self.places_url = 'https://places.googleapis.com/v1/places:searchNearby'
        self.headers = {
            'Content-Type': 'application/json',
            'X-Goog-Api-Key': self.api_key,
            'X-Goog-FieldMask': (
                'places.id,places.displayName,places.formattedAddress,'
                'places.location,'
                'places.primaryType,places.types,places.businessStatus,'
                'places.googleMapsUri'
            )
        }
        self.call_count = 0
        
    def search_for_vets(self, lat: float, lon: float, radius: Optional[int] = None) -> List[Dict]:
        """
        Search for veterinary practices at a location
        
        Args:
            lat: Latitude
            lon: Longitude  
            radius: Search radius in meters (defaults to env var)
            
        Returns:
            List of found veterinary practices
        """
        if radius is None:
            radius = int(os.getenv('SEARCH_RADIUS_METERS', '15000'))
        body = {
            'includedTypes': ['veterinary_care'],
            'locationRestriction': {
                'circle': {
                    'center': {'latitude': lat, 'longitude': lon},
                    'radius': radius
                }
            },
            'maxResultCount': int(os.getenv('MAX_RESULTS_PER_SEARCH', '10')),
            'rankPreference': 'DISTANCE'
        }
        
        try:
            # Rate limiting
            time.sleep(self.delay)
            self.call_count += 1
            
            response = requests.post(
                self.places_url,
                headers=self.headers,
                json=body
            )
            response.raise_for_status()
            places = response.json().get('places', [])
            
            # Filter out permanently closed
            active_places = [
                p for p in places 
                if p.get('businessStatus') != 'CLOSED_PERMANENTLY'
            ]
            
            logger.info(f"Found {len(active_places)} vets at ({lat:.4f}, {lon:.4f})")
            return active_places
            
        except Exception as e:
            logger.error(f"Error searching at ({lat}, {lon}): {e}")
            return []
    
    def process_points(
        self,
        gpkg_path: Optional[str] = None,
        layer_name: Optional[str] = None,
        output_path: Optional[str] = None,
        checkpoint_every: Optional[int] = None
    ) -> gpd.GeoDataFrame:
        """
        Process points from a GeoPackage
        
        Args:
            gpkg_path: Path to input GeoPackage (defaults to env var)
            layer_name: Layer name in GeoPackage (if None, uses first/only layer)
            output_path: Path for output GeoPackage (defaults to env var)
            checkpoint_every: Save progress every N points (defaults to env var)
            
        Returns:
            GeoDataFrame with search results
        """
        gpkg_path = gpkg_path or os.getenv('INPUT_GPKG')
        output_path = output_path or os.getenv('OUTPUT_GPKG', 'vet_search_results.gpkg')
        checkpoint_every = checkpoint_every or int(os.getenv('CHECKPOINT_EVERY', '50'))
        
        if not gpkg_path:
            raise ValueError("Input GPKG path must be provided via parameter or INPUT_GPKG env var")
        # Load points
        logger.info(f"Loading points from {gpkg_path}")
        gdf = gpd.read_file(gpkg_path, layer=layer_name)
        logger.info(f"Loaded {len(gdf)} points to search")
        
        # Prepare results storage
        results = []
        seen_place_ids = set()
        checkpoint_path = Path(output_path).with_suffix('.checkpoint.json')
        
        # Check for existing checkpoint
        start_idx = 0
        if checkpoint_path.exists():
            with open(checkpoint_path, 'r') as f:
                checkpoint = json.load(f)
                start_idx = checkpoint['last_idx'] + 1
                results = checkpoint['results']
                # Rebuild seen_place_ids from checkpoint
                for result in results:
                    if result.get('vets_json'):
                        vets = json.loads(result['vets_json'])
                        for vet in vets:
                            if vet.get('id'):
                                seen_place_ids.add(vet['id'])
            logger.info(f"Resuming from checkpoint at index {start_idx}")
            logger.info(f"Already seen {len(seen_place_ids)} unique places")
        
        # Process each point
        for idx in range(start_idx, len(gdf)):
            row = gdf.iloc[idx]
            
            # Get coordinates (works with any CRS and geometry type)
            geom = row.geometry
            # If it's a polygon/multipolygon, use centroid
            if hasattr(geom, 'centroid'):
                geom = geom.centroid
            
            if gdf.crs and gdf.crs != 'EPSG:4326':
                # Reproject this point to WGS84 for API
                point_wgs84 = gpd.GeoSeries([geom], crs=gdf.crs).to_crs('EPSG:4326')
                lon, lat = point_wgs84.iloc[0].x, point_wgs84.iloc[0].y
            else:
                lon, lat = geom.x, geom.y
            
            # Search for vets
            vets = self.search_for_vets(lat, lon)
            
            # Filter out duplicates based on place_id
            unique_vets = []
            for vet in vets:
                place_id = vet.get('id')
                if place_id and place_id not in seen_place_ids:
                    unique_vets.append(vet)
                    seen_place_ids.add(place_id)
                elif not place_id:
                    # Keep vets without place_id (shouldn't happen but be safe)
                    unique_vets.append(vet)
            
            # Store result
            result = {
                'source_idx': idx,
                'geometry': row.geometry,
                'lat': lat,
                'lon': lon,
                'search_timestamp': datetime.now().isoformat(),
                'num_vets_found': len(vets),
                'num_unique_vets': len(unique_vets),
                'vets_json': json.dumps(unique_vets) if unique_vets else None
            }
            
            # Add any additional fields from source
            for col in gdf.columns:
                if col not in ['geometry'] and col not in result:
                    result[f'source_{col}'] = row[col]
            
            results.append(result)
            
            logger.info(f"[{idx+1}/{len(gdf)}] Found {len(vets)} vets ({len(unique_vets)} unique)")
            
            # Checkpoint
            if (idx + 1) % checkpoint_every == 0:
                self._save_checkpoint(checkpoint_path, idx, results)
                logger.info(f"Checkpoint saved at index {idx}")
        
        # Create results GeoDataFrame
        results_gdf = gpd.GeoDataFrame(results, crs=gdf.crs)
        
        # Save final results
        results_gdf.to_file(output_path, driver='GPKG')
        logger.info(f"Results saved to {output_path}")
        
        # Extract individual vets to separate layer
        self._extract_vets_layer(results_gdf, output_path)
        
        # Clean up checkpoint
        if checkpoint_path.exists():
            checkpoint_path.unlink()
        
        # Summary
        logger.info(f"\n=== Summary ===")
        logger.info(f"Total points searched: {len(results_gdf)}")
        logger.info(f"Points with vets found: {(results_gdf['num_vets_found'] > 0).sum()}")
        logger.info(f"Total vets discovered: {results_gdf['num_vets_found'].sum()}")
        logger.info(f"Total API calls made: {self.call_count}")
        
        return results_gdf
    
    def _save_checkpoint(self, path: Path, last_idx: int, results: List[Dict]):
        """Save checkpoint for recovery"""
        # Convert geometries to WKT for JSON serialisation
        checkpoint_results = []
        for r in results:
            r_copy = r.copy()
            r_copy['geometry'] = r_copy['geometry'].wkt
            checkpoint_results.append(r_copy)
        
        checkpoint = {
            'last_idx': last_idx,
            'results': checkpoint_results,
            'timestamp': datetime.now().isoformat()
        }
        with open(path, 'w') as f:
            json.dump(checkpoint, f)
    
    def _extract_vets_layer(self, results_gdf: gpd.GeoDataFrame, output_path: str):
        """Extract individual vet locations to separate layer"""
        all_vets = []
        
        for _, row in results_gdf.iterrows():
            if row['vets_json']:
                vets = json.loads(row['vets_json'])
                for vet in vets:
                    # Extract vet location
                    vet_loc = vet.get('location', {})
                    if vet_loc:
                        from shapely.geometry import Point
                        vet_point = Point(vet_loc['longitude'], vet_loc['latitude'])
                        
                        vet_record = {
                            'geometry': vet_point,
                            'place_id': vet.get('id'),
                            'name': vet.get('displayName', {}).get('text'),
                            'address': vet.get('formattedAddress'),
                            'primary_type': vet.get('primaryType'),
                            'maps_uri': vet.get('googleMapsUri'),
                            'source_point_idx': row['source_idx']
                        }
                        all_vets.append(vet_record)
        
        if all_vets:
            vets_gdf = gpd.GeoDataFrame(all_vets, crs='EPSG:4326')
            vets_gdf.to_file(output_path, layer='discovered_vets', driver='GPKG')
            logger.info(f"Saved {len(vets_gdf)} individual vet locations to 'discovered_vets' layer")


def main():
    """Run the veterinary search"""
    
    try:
        # Initialise searcher (uses environment variables)
        searcher = VeterinarySearcher()
        
        # Process the points (uses environment variables)
        results = searcher.process_points()
        
        output_path = os.getenv('OUTPUT_GPKG', 'vet_search_results.gpkg')
        print(f"\nCompleted! Results saved to {output_path}")
        print(f"Check the 'discovered_vets' layer for individual vet locations")
        
    except ValueError as e:
        print(f"Configuration error: {e}")
        print("Please check your .env file and ensure all required variables are set.")
        return 1
        
    return 0


if __name__ == "__main__":
    main()