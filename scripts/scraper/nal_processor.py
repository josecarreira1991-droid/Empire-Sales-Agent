"""Processor for Florida Dept of Revenue NAL (Name-Address-Legal) files.

NAL files contain comprehensive property data for all parcels in a county:
- Owner names and mailing addresses
- Site addresses
- Year built, square footage
- Assessed and market values
- Homestead exemption status
- Sale history

Source: Request from PTOTechnology@floridarevenue.com
Counties: Lee (code 36), Collier (code 11)
Format: CSV
"""

import os
import logging
from datetime import datetime

import pandas as pd

from db import insert_lead, log_scraping_run, complete_scraping_run
from lead_scorer import calculate_score

logger = logging.getLogger(__name__)

# NAL file column mappings (Florida DOR standard format)
# These may need adjustment based on the actual file received
NAL_COLUMNS = {
    "CO_NO": "county_code",
    "PARCEL_ID": "parcel_id",
    "OWN_NAME": "full_name",
    "OWN_ADDR1": "mailing_addr1",
    "OWN_ADDR2": "mailing_addr2",
    "OWN_CITY": "mailing_city",
    "OWN_STATE": "mailing_state",
    "OWN_ZIPCD": "mailing_zip",
    "S_ADDR": "address",
    "S_CITY": "city",
    "S_ZIPCD": "zip_code",
    "DOR_UC": "property_use_code",
    "ACT_YR_BLT": "year_built",
    "TOT_LVG_AR": "square_footage",
    "NO_BULDNG": "num_buildings",
    "NO_RES_UNT": "num_units",
    "JV": "assessed_value",
    "JV_HMSTD": "homestead_value",
    "AV_HMSTD": "homestead_assessed",
    "TV_NSD": "taxable_value",
    "SALE_PRC1": "last_sale_price",
    "SALE_DT1": "last_sale_date",
    "SALE_PRC2": "prev_sale_price",
    "SALE_DT2": "prev_sale_date",
}

COUNTY_MAP = {"36": "Lee", "11": "Collier"}

# Residential property use codes (DOR)
RESIDENTIAL_USE_CODES = [
    "01",  # Single family
    "02",  # Mobile home
    "03",  # Multi-family (10 units or less)
    "04",  # Condominium
    "05",  # Cooperatives
    "06",  # Retirement homes
    "07",  # Miscellaneous residential
    "08",  # Multi-family (10+ units)
]


def process_nal_file(filepath: str, county_code: str = None) -> dict:
    """
    Process a Florida DOR NAL file and import leads into the database.

    Args:
        filepath: Path to the NAL CSV file
        county_code: Override county code (auto-detected from filename if not provided)

    Returns:
        Dict with processing stats
    """
    if not os.path.exists(filepath):
        logger.error(f"NAL file not found: {filepath}")
        return {"error": "File not found"}

    # Detect county from filename if not provided
    if not county_code:
        filename = os.path.basename(filepath).lower()
        if "36" in filename or "lee" in filename:
            county_code = "36"
        elif "11" in filename or "collier" in filename:
            county_code = "11"
        else:
            logger.error("Cannot detect county from filename. Provide county_code.")
            return {"error": "Unknown county"}

    county_name = COUNTY_MAP.get(county_code, "Unknown")
    run_id = log_scraping_run(f"nal_{county_name.lower()}")

    logger.info(f"Processing NAL file for {county_name} County: {filepath}")

    try:
        # Read NAL file
        df = pd.read_csv(
            filepath,
            dtype=str,
            low_memory=False,
            encoding="latin-1",
        )

        logger.info(f"Loaded {len(df)} records from NAL file")

        # Rename columns to our standard names
        rename_map = {}
        for orig, new in NAL_COLUMNS.items():
            if orig in df.columns:
                rename_map[orig] = new
        df = df.rename(columns=rename_map)

        # Filter residential properties only
        if "property_use_code" in df.columns:
            df["property_use_code"] = df["property_use_code"].str.strip().str.zfill(2)
            df = df[df["property_use_code"].isin(RESIDENTIAL_USE_CODES)]
            logger.info(f"Filtered to {len(df)} residential properties")

        # Clean and convert data
        df = _clean_nal_data(df, county_name)

        # Score and insert leads
        inserted = 0
        skipped = 0
        scored = 0

        for _, row in df.iterrows():
            lead = row.to_dict()

            # Remove NaN values
            lead = {k: v for k, v in lead.items() if pd.notna(v)}

            # Calculate renovation score
            score, reasons = calculate_score(lead)
            lead["renovation_score"] = score
            lead["score_reasons"] = reasons
            lead["source"] = "scraper_nal"

            # Only import leads with score >= 20 (some renovation potential)
            if score >= 20:
                result = insert_lead(lead)
                if result:
                    inserted += 1
                    scored += 1
                else:
                    skipped += 1

        complete_scraping_run(
            run_id,
            records_found=len(df),
            records_new=inserted,
            records_updated=0,
            errors=0,
        )

        stats = {
            "county": county_name,
            "total_records": len(df),
            "leads_inserted": inserted,
            "leads_skipped": skipped,
            "avg_score": scored,
        }
        logger.info(f"NAL processing complete: {stats}")
        return stats

    except Exception as e:
        logger.error(f"Error processing NAL file: {e}")
        complete_scraping_run(run_id, errors=1, error_details=str(e), status="failed")
        return {"error": str(e)}


def _clean_nal_data(df: pd.DataFrame, county_name: str) -> pd.DataFrame:
    """Clean and transform NAL data for lead insertion."""
    df["county"] = county_name

    # Convert numeric fields
    for col in ["year_built", "square_footage"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in ["assessed_value", "taxable_value", "last_sale_price", "prev_sale_price"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Parse sale dates (YYYYMMDD format from DOR)
    for col in ["last_sale_date", "prev_sale_date"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], format="%Y%m%d", errors="coerce")
            df[col] = df[col].dt.date

    # Homestead detection
    if "homestead_value" in df.columns:
        df["homestead"] = pd.to_numeric(df["homestead_value"], errors="coerce").fillna(0) > 0
    else:
        df["homestead"] = False

    # Market value (use assessed if no separate market value)
    if "market_value" not in df.columns and "assessed_value" in df.columns:
        df["market_value"] = df["assessed_value"]

    # Clean address
    if "address" in df.columns:
        df["address"] = df["address"].str.strip().str.title()

    if "city" in df.columns:
        df["city"] = df["city"].str.strip().str.title()

    if "full_name" in df.columns:
        df["full_name"] = df["full_name"].str.strip().str.title()

    # Select only the columns we need for the leads table
    keep_cols = [
        "full_name", "address", "city", "county", "zip_code", "parcel_id",
        "year_built", "square_footage", "assessed_value", "market_value",
        "last_sale_price", "last_sale_date", "homestead", "property_use_code",
    ]
    available = [c for c in keep_cols if c in df.columns]
    df = df[available].copy()

    # Drop rows without an address
    if "address" in df.columns:
        df = df.dropna(subset=["address"])

    return df


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) < 2:
        print("Usage: python nal_processor.py <path_to_nal_file.csv> [county_code]")
        print("  county_code: 36 (Lee) or 11 (Collier)")
        sys.exit(1)

    filepath = sys.argv[1]
    county = sys.argv[2] if len(sys.argv) > 2 else None
    result = process_nal_file(filepath, county)
    print(f"Result: {result}")
