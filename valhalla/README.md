# Valhalla Routing Engine Setup

This directory contains the Docker configuration and preprocessing scripts for running a local Valhalla routing engine instance. Valhalla is used to generate drive-time isochrones from veterinary service locations.

## Overview

Valhalla is an open-source routing engine that supports various transportation modes and can generate isochrones (travel-time polygons). For this project, it is deployed in a Docker container and configured to route across the Australian road network using OpenStreetMap data.

## Prerequisites

- Docker and Docker Compose installed
- Sufficient disk space (~1.5GB for processed tiles)
- WSL2 (if running on Windows)

## Setup Instructions

### 1. Start Valhalla Server

```bash
cd valhalla
docker compose up -d
```

This will:
- Pull the latest Valhalla Docker image (gis-ops/docker-valhalla)
- Start the routing server on port 8002
- Mount the `./custom_files` directory into the container

### 2. Monitor Server Startup

```bash
docker logs -f valhalla
```

Watch the logs to confirm the server has started successfully. The initial tile building process may take some time.

### 3. Download Road Network Data

Navigate to the `custom_files` directory and download the OpenStreetMap extract for Australia:

```bash
cd custom_files
wget https://download.geofabrik.de/australia-oceania/australia-latest.osm.pbf
```

The Valhalla container will automatically process the PBF file into routing tiles on startup.

### 4. Preprocessing: Reclassify Highway Tracks

Many rural Australian roads are tagged as `highway=track` in OpenStreetMap, which Valhalla does not consider routable by default. The `reclassify_tracks.py` script reclassifies these segments to `highway=unclassified` to include rural access roads in the routing network.

First, set up a Python virtual environment and install dependencies:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Then run the reclassification script:

```bash
python reclassify_tracks.py custom_files/australia-latest.osm.pbf custom_files/australia-latest-reclassified.osm.pbf
```

After reclassification, replace the original PBF file in `custom_files/` and restart the container to rebuild the routing tiles:

```bash
docker-compose restart valhalla
```

## Configuration

The Valhalla server is configured via `custom_files/valhalla.json`. This file contains routing profiles and costing options. If you modify this configuration:

```bash
docker-compose restart valhalla
```

## Verify Connectivity

Test that Valhalla is responding correctly:

```bash
curl -X POST http://localhost:8002/isochrone \
  -H "Content-Type: application/json" \
  -d '{
    "locations":[{"lat":-37.8136,"lon":144.9631}],
    "costing":"auto",
    "contours":[{"time":60}],
    "polygons":true
  }'
```

A successful response will return a GeoJSON polygon representing a 60-minute drive-time area.

## Files in This Directory

- `docker-compose.yml` - Docker Compose configuration for Valhalla server
- `reclassify_tracks.py` - Preprocessing script to reclassify rural roads
- `requirements.txt` - Python dependencies for reclassify_tracks.py
- `custom_files/` - Directory mounted into Docker container
  - `valhalla.json` - Valhalla routing engine configuration
  - `*.osm.pbf` - Road network data (not tracked in git)
  - `valhalla_tiles/` - Processed routing tiles (not tracked in git)

## Usage with Isochrone Tool

Once Valhalla is running, you can generate isochrones using the `vet-isochrones` tool. See the `../vet-isochrones/README.md` for details.

## Stopping the Server

```bash
docker compose down
```

## Troubleshooting

**Server not responding:**
- Check Docker is running: `docker ps`
- View logs: `docker logs valhalla`
- Ensure port 8002 is not in use by another service

**Tiles not building:**
- Verify PBF file exists in `custom_files/`
- Check Docker logs for build errors
- Ensure sufficient disk space

**Rural roads not routing:**
- Confirm you've run `reclassify_tracks.py` on the PBF file
- Restart container after replacing PBF file

## References

- Valhalla: https://github.com/valhalla/valhalla
- Docker Image: https://github.com/gis-ops/docker-valhalla
- OpenStreetMap Data: https://download.geofabrik.de/
