import logging
import pandas as pd
import time
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import requests
import os
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class VeterinaryValidator:
    """Validate veterinary practices against Google Places API"""

    def __init__(self, api_key: Optional[str] = None, delay: Optional[float] = None):
        """
        Initialise the validator

        Args:
            api_key: Google Places API key (defaults to env var)
            delay: Seconds between API calls (defaults to env var)
        """
        self.api_key = api_key or os.getenv('GOOGLE_PLACES_API_KEY')
        self.delay = delay or float(os.getenv('API_DELAY_SECONDS', '0.2'))

        if not self.api_key:
            raise ValueError("Google Places API key must be provided via parameter or GOOGLE_PLACES_API_KEY env var")

        self.text_search_url = 'https://places.googleapis.com/v1/places:searchText'
        self.headers = {
            'Content-Type': 'application/json',
            'X-Goog-Api-Key': self.api_key,
            'X-Goog-FieldMask': (
                'places.id,places.displayName,places.formattedAddress,'
                'places.location,places.businessStatus,'
                'places.googleMapsUri,places.types'
            )
        }
        self.call_count = 0

    def search_by_text(self, practice_name: str, address: str) -> List[Dict]:
        """
        Search for a veterinary practice by name and address

        Args:
            practice_name: Name of the veterinary practice
            address: Business address

        Returns:
            List of matching places from Google
        """
        # Construct search query
        query = f"{practice_name} {address}"

        body = {
            'textQuery': query,
            'includedType': 'veterinary_care',
            'maxResultCount': 5
        }

        try:
            # Rate limiting
            time.sleep(self.delay)
            self.call_count += 1

            response = requests.post(
                self.text_search_url,
                headers=self.headers,
                json=body
            )
            response.raise_for_status()
            places = response.json().get('places', [])

            logger.debug(f"Found {len(places)} results for: {practice_name}")
            return places

        except Exception as e:
            logger.error(f"Error searching for '{practice_name}': {e}")
            return []

    def calculate_match_confidence(
        self,
        original_name: str,
        original_address: str,
        google_name: str,
        google_address: str
    ) -> Tuple[float, str]:
        """
        Calculate confidence score for a match

        Args:
            original_name: Name from CSV
            original_address: Address from CSV
            google_name: Name from Google Places
            google_address: Address from Google Places

        Returns:
            Tuple of (confidence_score, match_reason)
        """
        # Simple string matching (normalise to lowercase)
        orig_name_lower = original_name.lower().strip()
        orig_addr_lower = original_address.lower().strip()
        google_name_lower = google_name.lower().strip()
        google_addr_lower = google_address.lower().strip()

        # Check for exact matches
        name_exact = orig_name_lower == google_name_lower
        addr_exact = orig_addr_lower == google_addr_lower

        if name_exact and addr_exact:
            return 1.0, "Exact name and address match"

        # Check for name containment
        name_in_google = orig_name_lower in google_name_lower
        google_in_name = google_name_lower in orig_name_lower

        # Check for address containment
        addr_in_google = orig_addr_lower in google_addr_lower
        google_in_addr = google_addr_lower in orig_addr_lower

        # Calculate score based on partial matches
        score = 0.0
        reasons = []

        if name_exact:
            score += 0.5
            reasons.append("exact name")
        elif name_in_google or google_in_name:
            score += 0.3
            reasons.append("partial name")

        if addr_exact:
            score += 0.5
            reasons.append("exact address")
        elif addr_in_google or google_in_addr:
            score += 0.3
            reasons.append("partial address")

        # Check for key address components (street number, street name)
        if score < 0.6:
            # Extract numbers from addresses
            import re
            orig_numbers = set(re.findall(r'\d+', orig_addr_lower))
            google_numbers = set(re.findall(r'\d+', google_addr_lower))

            if orig_numbers and orig_numbers & google_numbers:
                score += 0.1
                reasons.append("matching street number")

        reason_str = ", ".join(reasons) if reasons else "No significant match"
        return min(score, 1.0), reason_str

    def validate_practice(
        self,
        practice_name: str,
        address: str
    ) -> Dict:
        """
        Validate a single veterinary practice

        Args:
            practice_name: Name of the practice
            address: Business address

        Returns:
            Dictionary with validation results
        """
        # Handle mobile practices - search by name only
        is_mobile = address.lower().strip() == "mobile practice"

        if is_mobile:
            logger.debug(f"Mobile practice detected: {practice_name}")
            places = self.search_by_text(practice_name, "Queensland Australia")
        else:
            # Search Google Places with full address
            places = self.search_by_text(practice_name, address)

        if not places:
            return {
                'found': False,
                'confidence': 0.0,
                'match_reason': 'No results from Google Places',
                'business_status': 'NOT_FOUND',
                'primary_type': None,
                'all_types': None,
                'place_id': None,
                'google_name': None,
                'google_address': None,
                'maps_uri': None,
                'is_mobile_practice': is_mobile
            }

        # Find best match
        best_match = None
        best_score = 0.0
        best_reason = ""

        for place in places:
            google_name = place.get('displayName', {}).get('text', '')
            google_address = place.get('formattedAddress', '')

            if not google_name:
                continue

            # For mobile practices, only match on name
            if is_mobile:
                # Simple name matching for mobile practices
                orig_name_lower = practice_name.lower().strip()
                google_name_lower = google_name.lower().strip()

                if orig_name_lower == google_name_lower:
                    score = 0.9  # High confidence for exact name match
                    reason = "Exact name match (mobile practice)"
                elif orig_name_lower in google_name_lower or google_name_lower in orig_name_lower:
                    score = 0.6  # Medium confidence for partial match
                    reason = "Partial name match (mobile practice)"
                else:
                    score = 0.3  # Low confidence
                    reason = "Weak name match (mobile practice)"
            else:
                # Regular matching with address
                if not google_address:
                    continue
                score, reason = self.calculate_match_confidence(
                    practice_name, address, google_name, google_address
                )

            if score > best_score:
                best_score = score
                best_match = place
                best_reason = reason

        if best_match:
            return {
                'found': True,
                'confidence': best_score,
                'match_reason': best_reason,
                'business_status': best_match.get('businessStatus', 'UNKNOWN'),
                'primary_type': best_match.get('primaryType'),
                'all_types': ', '.join(best_match.get('types', [])),
                'place_id': best_match.get('id'),
                'google_name': best_match.get('displayName', {}).get('text'),
                'google_address': best_match.get('formattedAddress'),
                'maps_uri': best_match.get('googleMapsUri'),
                'is_mobile_practice': is_mobile
            }
        else:
            return {
                'found': False,
                'confidence': 0.0,
                'match_reason': 'No confident match found',
                'business_status': 'NOT_FOUND',
                'primary_type': None,
                'all_types': None,
                'place_id': None,
                'google_name': None,
                'google_address': None,
                'maps_uri': None,
                'is_mobile_practice': is_mobile
            }

    def validate_csv(
        self,
        input_csv: str,
        output_csv: Optional[str] = None,
        name_column: str = 'Premises name',
        address_column: str = 'Business address'
    ) -> pd.DataFrame:
        """
        Validate all practices in a CSV file

        Args:
            input_csv: Path to input CSV file
            output_csv: Path to output CSV (defaults to input_name_validated.csv)
            name_column: Column name containing practice names
            address_column: Column name containing addresses

        Returns:
            DataFrame with validation results
        """
        # Load CSV (try different encodings)
        logger.info(f"Loading practices from {input_csv}")
        try:
            df = pd.read_csv(input_csv, encoding='utf-8')
        except UnicodeDecodeError:
            logger.info("UTF-8 failed, trying latin-1 encoding")
            df = pd.read_csv(input_csv, encoding='latin-1')
        logger.info(f"Loaded {len(df)} practices to validate")

        # Validate required columns
        if name_column not in df.columns or address_column not in df.columns:
            raise ValueError(f"CSV must contain '{name_column}' and '{address_column}' columns")

        # Prepare output path
        if output_csv is None:
            input_path = Path(input_csv)
            output_csv = str(input_path.parent / f"{input_path.stem}_validated.csv")

        # Validate each practice
        results = []
        for idx, row in df.iterrows():
            practice_name = row[name_column]
            address = row[address_column]

            logger.info(f"[{idx+1}/{len(df)}] Validating: {practice_name}")

            validation = self.validate_practice(practice_name, address)

            # Combine original data with validation results
            result = {
                'original_name': practice_name,
                'original_address': address,
                'is_mobile_practice': validation['is_mobile_practice'],
                'found_in_google': validation['found'],
                'confidence_score': validation['confidence'],
                'match_reason': validation['match_reason'],
                'business_status': validation['business_status'],
                'primary_type': validation['primary_type'],
                'all_types': validation['all_types'],
                'place_id': validation['place_id'],
                'google_name': validation['google_name'],
                'google_address': validation['google_address'],
                'google_maps_uri': validation['maps_uri'],
                'validation_timestamp': datetime.now().isoformat()
            }

            results.append(result)

            # Log status
            status = validation['business_status']
            conf = validation['confidence']
            logger.info(f"  → Status: {status}, Confidence: {conf:.2f}")

        # Create results DataFrame
        results_df = pd.DataFrame(results)

        # Save results
        results_df.to_csv(output_csv, index=False)
        logger.info(f"\nResults saved to {output_csv}")

        # Generate summary
        self._print_summary(results_df)

        return results_df

    def _print_summary(self, df: pd.DataFrame):
        """Print validation summary statistics"""
        logger.info("\n=== Validation Summary ===")
        logger.info(f"Total practices validated: {len(df)}")

        # Found vs not found
        found = df['found_in_google'].sum()
        not_found = len(df) - found
        logger.info(f"Found in Google: {found} ({found/len(df)*100:.1f}%)")
        logger.info(f"Not found: {not_found} ({not_found/len(df)*100:.1f}%)")

        # Business status breakdown (for found practices)
        if found > 0:
            logger.info("\nBusiness Status (for found practices):")
            status_counts = df[df['found_in_google']]['business_status'].value_counts()
            for status, count in status_counts.items():
                logger.info(f"  {status}: {count}")

        # Confidence distribution
        logger.info("\nConfidence Score Distribution:")
        high_conf = (df['confidence_score'] >= 0.8).sum()
        med_conf = ((df['confidence_score'] >= 0.5) & (df['confidence_score'] < 0.8)).sum()
        low_conf = ((df['confidence_score'] > 0.0) & (df['confidence_score'] < 0.5)).sum()
        no_conf = (df['confidence_score'] == 0.0).sum()

        logger.info(f"  High (≥0.8): {high_conf}")
        logger.info(f"  Medium (0.5-0.8): {med_conf}")
        logger.info(f"  Low (0.0-0.5): {low_conf}")
        logger.info(f"  None (0.0): {no_conf}")

        # Mobile practices
        mobile = df['is_mobile_practice'].sum()
        if mobile > 0:
            logger.info(f"\nMobile practices (from CSV): {mobile}")

        # Primary type breakdown (for found practices)
        if found > 0:
            logger.info("\nPrimary Type Distribution:")
            type_counts = df[df['found_in_google']]['primary_type'].value_counts()
            for ptype, count in type_counts.items():
                logger.info(f"  {ptype}: {count}")

            # Check how many are actually veterinary_care
            vet_care_count = (df[df['found_in_google']]['primary_type'] == 'veterinary_care').sum()
            logger.info(f"\nConfirmed as veterinary_care: {vet_care_count}/{found} ({vet_care_count/found*100:.1f}%)")

        logger.info(f"\nTotal API calls made: {self.call_count}")


def main():
    """Run the veterinary practice validation"""

    try:
        # Initialise validator (uses environment variables)
        validator = VeterinaryValidator()

        # Default input file
        input_csv = "queensland-veterinary-locations.csv"

        # Allow override from command line
        import sys
        if len(sys.argv) > 1:
            input_csv = sys.argv[1]

        # Validate practices
        results = validator.validate_csv(input_csv)

        print(f"\nCompleted! Check the output CSV for detailed results.")

    except ValueError as e:
        print(f"Configuration error: {e}")
        print("Please check your .env file and ensure GOOGLE_PLACES_API_KEY is set.")
        return 1
    except FileNotFoundError as e:
        print(f"File not found: {e}")
        return 1

    return 0


if __name__ == "__main__":
    main()
