# Veterinary Isochrones Tool

## Project Overview
Generate isochrones (travel time polygons) for veterinary service points using Valhalla routing engine. The tool reads point locations from a GPKG file and creates merged catchment areas showing 60-minute travel accessibility.

## Architecture
```
Input: GPKG with point geometries → Valhalla API → Individual isochrones → Merged polygon → Output GPKG
```

## Key Features
- Point-by-point isochrone generation via Valhalla API
- CRS conversion (auto-converts to WGS84)
- Geometry validation and fixing
- Polygon merging using unary_union
- Configurable travel time, costing model, and request delays
- Veterinary access options (ignores gates, private roads, restrictions)
- Multi-threading (configurable via arg)
- Comprehensive logging and error handling
- Command-line interface with argparse

## Development Setup
```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate

# Activate Valhalla
cd ~/valhalla
docker compose up -d
docker logs -f valhalla

# If a change is made to valhalla.json (in custom_files)
docker-compose restart valhalla

# Install dependencies
pip install -r requirements.txt

# Verify Valhalla connectivity (optional)
curl -X POST http://localhost:8002/isochrone -H "Content-Type: application/json" -d '{"locations":[{"lat":-37.8136,"lon":144.9631}],"costing":"auto","contours":[{"time":60}],"polygons":true}'
```

## Usage Example
```bash
# Standard usage
python valhalla_isochrones.py points.gpkg -o catchment_area.geojson -t 60 -c auto

# With veterinary access (ignores gates, private roads)
python valhalla_isochrones.py vet-clinics-national-20mins-merged.gpkg -o vet-isochrones-merged-60mins-tracks.gpkg -t 60 --vet-access --threads 8
```

## Project Requirements

**Use Case**: Determine population outside 60-minute service window from Australian veterinary clinics
- Points represent veterinary clinic locations (lat/lon only needed)
- Travel by car/vehicle including ferries (standard automotive routing)
- Output: Merged isochrone polygon for population raster analysis in QGIS
- Local Valhalla instance (no rate limiting concerns)
- Failure handling: Count and report failed points in summary statistics
- Environment: pip-based dependency management