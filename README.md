# Veterinary Service Accessibility Analysis for Australia

This repository contains the reproducible geospatial workflow used to assess access to veterinary services across Australia. The methodology relies exclusively on open, globally available datasets and open-source software, ensuring replicability in other jurisdictions with minimal adaptation.

## Overview

This study models the spatial distribution of population beyond a one-hour drive from veterinary service locations (VSLs) and estimates the number of people potentially affected. The workflow consists of three main components:

1. **Data compilation and augmentation** - Combining open baseline datasets with targeted API searches
2. **Routing infrastructure** - Local Valhalla instance for generating drive-time isochrones
3. **Accessibility modeling** - Generating isochrones and applying them to population data

## Repository Structure

```
vet-accessibility-aus/
├── vet-search/           # Google Places API tools for discovering and validating VSLs
├── valhalla/             # Docker-based Valhalla routing engine setup
├── vet-isochrones/       # Python tool for generating drive-time isochrones
└── README.md             # This file
```

### Component Descriptions

#### 1. vet-search/
Tools for discovering and validating veterinary service locations using the Google Places API.

**Key scripts:**
- `vet_search.py` - Targeted search for veterinary practices around H3 grid centroids
- `vet_validation.py` - Validation of veterinary practice records against Google Places

This component implements the H3-based targeted augmentation strategy described in the paper, focusing API queries on geographic areas where additional VSLs would meaningfully alter the accessibility surface.

See [vet-search/README.md](vet-search/README.md) for detailed documentation.

#### 2. valhalla/
Docker configuration and preprocessing scripts for running a local Valhalla routing engine.

**Key files:**
- `docker-compose.yml` - Valhalla server configuration
- `reclassify_tracks.py` - Preprocessing to include rural Australian roads

Valhalla processes OpenStreetMap road network data and provides isochrone generation capabilities via a local API endpoint.

See [valhalla/README.md](valhalla/README.md) for setup instructions.

#### 3. vet-isochrones/
Python tool for generating drive-time isochrones from veterinary service locations.

**Key script:**
- `valhalla_isochrones.py` - Multi-threaded isochrone generation and polygon merging

This tool queries the local Valhalla instance to generate 60-minute drive-time polygons from all VSL points, then merges them into a national accessibility surface.

See [vet-isochrones/README.md](vet-isochrones/README.md) for usage examples.

## Workflow Summary

The complete analysis workflow is:

1. **Baseline Dataset**: Extract veterinary services from Overture Maps Foundation "Places" dataset
2. **Completeness Benchmarking**: Validate coverage using official registers (e.g., Queensland VSB)
3. **H3 Grid Generation**: Create population-weighted hexagonal grid at resolution 5
4. **Cell Elimination**: Remove H3 cells already within 20-minute drive of existing VSLs
5. **Targeted Augmentation**: Search remaining cells using Google Places API (`vet_search.py`)
6. **Road Network Preparation**: Download OSM data and reclassify rural tracks (`reclassify_tracks.py`)
7. **Valhalla Deployment**: Build routing tiles and start server (`docker compose up`)
8. **Isochrone Generation**: Generate 60-minute drive-time polygons (`valhalla_isochrones.py`)
9. **Population Analysis**: Apply isochrone mask to GHSL population raster (QGIS)

## Data Sources

All data sources are freely available and globally accessible:

- **Overture Maps Foundation** - Baseline veterinary service locations
- **Google Places API** - Targeted augmentation and validation
- **OpenStreetMap** (via Geofabrik) - Road network data
- **Global Human Settlement Layer (GHSL)** - Population distribution at 100m resolution
- **Australian Bureau of Statistics (ABS)** - Administrative boundaries (ASGS)

## Requirements

### Software
- Python 3.8+
- QGIS 3.44+ (for spatial analysis and visualization)
- Docker and Docker Compose (for Valhalla)
- WSL2 (if running on Windows)

### Python Dependencies
Each component has its own `requirements.txt` file:
- `vet-search/requirements.txt`
- `vet-isochrones/requirements.txt`

### API Keys
- Google Places API key (required for `vet-search` component only)

## Quick Start

### 1. Clone the repository
```bash
git clone https://github.com/pukallus/vet-accessibility-aus.git
cd vet-accessibility-aus
```

### 2. Set up Valhalla routing engine
```bash
cd valhalla
docker compose up -d
```

See [valhalla/README.md](valhalla/README.md) for detailed setup including road network preparation.

### 3. Set up Python environments

For each component (`vet-search` and `vet-isochrones`):

```bash
cd vet-search  # or vet-isochrones
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Configure API key (vet-search only)

```bash
cd vet-search
cp .env.example .env
# Edit .env and add your Google Places API key
```

### 5. Run the tools

Refer to individual README files for usage examples:
- [vet-search/README.md](vet-search/README.md) - VSL discovery and validation
- [vet-isochrones/README.md](vet-isochrones/README.md) - Isochrone generation

## Reproducibility

This workflow is designed for global reproducibility:

- All data sources have open licenses and global coverage
- All software tools are open-source and freely available
- The methodology uses standardized geographic frameworks (H3, WGS84)
- Parameters are tunable for different jurisdictions (drive times, population thresholds, H3 resolution)

To replicate this analysis in another country:
1. Download Overture Places data for your region
2. Obtain regional road network from Geofabrik (OpenStreetMap)
3. Download GHSL population tiles for your area
4. Adjust H3 resolution and drive-time parameters as needed
5. Run the same workflow using the provided scripts

## Citation

If you use this workflow in your research, please cite:

```
[Full paper citation once published]
```

## License

MIT

## Paper Reference

This repository accompanies the paper:

> [Full paper citation once published]

## Contact

For questions or issues, please open an issue on GitHub or connect via LinkedIn:
- [B.D. Orr](https://www.linkedin.com/in/bronwyn-orr-30632262/)
- [D. Pukallus](https://www.linkedin.com/in/doug-pukallus-39128547/)

## Acknowledgments

This research was conducted using open data from:
- Overture Maps Foundation
- OpenStreetMap contributors
- European Commission Joint Research Centre (GHSL)
- Australian Bureau of Statistics

Routing engine provided by the Valhalla open-source community.
