# Veterinary Practice Search and Validation Tools

A set of Python tools for discovering and validating veterinary practices using the Google Places API. These scripts were developed to support research on veterinary service accessibility and distribution.

## Overview

This repository contains two complementary tools:

1. **vet_search.py** - Discovers veterinary practices by searching around geographic points
2. **vet_validation.py** - Validates existing veterinary practice records against Google Places

## Features

### vet_search.py
- Search for veterinary practices within a specified radius of geographic points
- Process points from GeoPackage files (supports any CRS)
- Automatic deduplication of discovered practices
- Checkpoint/resume functionality for long-running searches
- Outputs results in GeoPackage format with two layers:
  - Search results with aggregated data
  - Individual discovered veterinary practices

### vet_validation.py
- Validate veterinary practice records from CSV files
- Match practices against Google Places using name and address
- Confidence scoring for match quality
- Business status detection (operational, permanently closed, etc.)
- Support for mobile veterinary practices
- Primary type verification to confirm veterinary classification
- Detailed validation report with match confidence and business status

## Requirements

- Python 3.8+
- Google Places API key (new Places API v1)

## Installation

1. Clone this repository:
```bash
git clone https://github.com/yourusername/vet-search.git
cd vet-search
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
```bash
cp .env.example .env
```

5. Edit `.env` and add your Google Places API key:
```
GOOGLE_PLACES_API_KEY=your_api_key_here
```

## Getting a Google Places API Key

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the **Places API (New)**
4. Go to Credentials and create an API key
5. (Optional) Restrict the API key to Places API for security

**Note:** The Google Places API is a paid service. Check current pricing at [Google Maps Platform Pricing](https://developers.google.com/maps/billing-and-pricing/pricing).

## Usage

### vet_search.py - Discover Veterinary Practices

This tool searches for veterinary practices around geographic points stored in a GeoPackage.

**Basic usage:**
```bash
python vet_search.py
```

The script will use settings from your `.env` file. You can customize the following parameters:

**Environment variables:**
```bash
# Required
GOOGLE_PLACES_API_KEY=your_api_key_here

# Input/Output
INPUT_GPKG=h3-beyond-20mins.gpkg          # Input GeoPackage with search points
OUTPUT_GPKG=vet_search_results.gpkg       # Output GeoPackage

# Search parameters
SEARCH_RADIUS_METERS=15000                # Search radius (default: 15km)
MAX_RESULTS_PER_SEARCH=10                 # Max results per search point
API_DELAY_SECONDS=0.2                     # Delay between API calls
CHECKPOINT_EVERY=50                       # Save progress every N points
```

**Example output:**

The output GeoPackage contains two layers:

1. **Main layer** - One record per search point with:
   - Original point geometry and attributes
   - Number of vets found
   - Search metadata
   - JSON array of discovered practices

2. **discovered_vets layer** - Individual vet locations with:
   - Point geometry (vet location)
   - Place ID
   - Name and address
   - Primary type
   - Google Maps URI

**Checkpoint/Resume:**

If the script is interrupted, it will automatically resume from the last checkpoint:
```bash
# Script creates: vet_search_results.checkpoint.json
# Simply re-run to resume:
python vet_search.py
```

### vet_validation.py - Validate Practice Records

This tool validates a list of veterinary practices from a CSV file against Google Places.

**Basic usage:**
```bash
python vet_validation.py
```

This will validate `queensland-veterinary-locations.csv` by default.

**Custom CSV file:**
```bash
python vet_validation.py my-practices.csv
```

**Input CSV format:**

The CSV should contain at least two columns:
- `Premises name` - Name of the veterinary practice
- `Business address` - Physical address (or "Mobile practice")

Example:
```csv
Premises name,Business address
Acacia Ridge Veterinary Surgery,"1102 Beaudesert Road, Acacia Ridge QLD 4110"
Smith Mobile Vet,Mobile practice
```

**Output:**

The script generates a CSV file (e.g., `queensland-veterinary-locations_validated.csv`) with the following columns:

- `original_name` - Practice name from input
- `original_address` - Address from input
- `is_mobile_practice` - Boolean flag for mobile practices
- `found_in_google` - Whether a match was found
- `confidence_score` - Match confidence (0.0 to 1.0)
- `match_reason` - Explanation of the match quality
- `business_status` - Google business status (OPERATIONAL, CLOSED_PERMANENTLY, etc.)
- `primary_type` - Google's primary type classification
- `all_types` - All Google types (comma-separated)
- `place_id` - Google Place ID
- `google_name` - Name from Google Places
- `google_address` - Address from Google Places
- `google_maps_uri` - Google Maps link
- `validation_timestamp` - When validation occurred

**Interpreting confidence scores:**

- **1.0** - Exact name and address match
- **0.8-0.9** - High confidence (exact name or very close address match)
- **0.5-0.8** - Medium confidence (partial matches)
- **0.3-0.5** - Low confidence (weak matches, review recommended)
- **0.0** - Not found or no match

**Mobile practices:**

For mobile practices, the script searches by name only (with "Queensland Australia" as regional context) since they don't have fixed addresses. Confidence scores are based on name matching only.

**Example summary output:**
```
=== Validation Summary ===
Total practices validated: 850
Found in Google: 742 (87.3%)
Not found: 108 (12.7%)

Business Status (for found practices):
  OPERATIONAL: 698
  CLOSED_PERMANENTLY: 32
  CLOSED_TEMPORARILY: 12

Confidence Score Distribution:
  High (≥0.8): 612
  Medium (0.5-0.8): 98
  Low (0.0-0.5): 32
  None (0.0): 108

Mobile practices (from CSV): 45

Primary Type Distribution:
  veterinary_care: 710
  pet_store: 18
  health: 14

Confirmed as veterinary_care: 710/742 (95.7%)

Total API calls made: 850
```

## API Rate Limiting

Both scripts include rate limiting to avoid exceeding Google's quota:
- Default delay: 0.2 seconds between requests
- Adjust `API_DELAY_SECONDS` in `.env` if needed

Monitor your API usage in the [Google Cloud Console](https://console.cloud.google.com/).

## Data Privacy and Ethics

When using these tools for research:

1. **API Terms of Service** - Ensure compliance with [Google Maps Platform Terms](https://cloud.google.com/maps-platform/terms)
2. **Data Storage** - Review Google's requirements for storing Places data
3. **Attribution** - Include proper attribution when displaying results
4. **Privacy** - Handle business data responsibly, especially for academic publication

## Citation

If you use these tools in academic research, please cite:

```
[Your citation format here]
```

## Troubleshooting

### Common Issues

**"Configuration error: Google Places API key must be provided"**
- Make sure `.env` file exists with `GOOGLE_PLACES_API_KEY=your_key`

**"UTF-8 codec can't decode byte"**
- CSV encoding issue - the script will automatically try latin-1 encoding

**"No results from Google Places"**
- Verify your API key is valid and Places API (New) is enabled
- Check that you haven't exceeded quota limits
- Verify the practice name/address format

**Slow performance**
- Increase `API_DELAY_SECONDS` if hitting rate limits
- For large datasets, run during off-peak hours
- Consider splitting large CSVs into batches

### API Errors

**403 Forbidden**
- API key not valid or Places API not enabled
- Check API key restrictions in Google Cloud Console

**429 Too Many Requests**
- Rate limit exceeded
- Increase `API_DELAY_SECONDS` in `.env`

**RESOURCE_EXHAUSTED**
- Daily quota exceeded
- Check quota in Google Cloud Console
- Request quota increase if needed

## License

[Your chosen license - e.g., MIT, GPL-3.0, etc.]

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

## Contact

For questions or issues, please contact [your contact information] or open an issue on GitHub.

## Acknowledgments

Developed for research on veterinary service accessibility. Thanks to [acknowledge any collaborators, funding sources, etc.].
