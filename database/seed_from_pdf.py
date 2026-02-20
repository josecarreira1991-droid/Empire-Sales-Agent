"""Import leads from PDF files into the Empire Sales Agent database.

Extracts names, phone numbers, addresses, and emails from PDF files
using pdfplumber. Supports various PDF formats common in construction:
- Client lists
- Estimate records
- Contact sheets
- Lead lists

Usage:
    python seed_from_pdf.py <pdf_file_or_directory>
    python seed_from_pdf.py /path/to/leads.pdf
    python seed_from_pdf.py /path/to/pdfs/   (processes all PDFs in directory)
"""

import os
import re
import sys
import logging
from pathlib import Path

import pdfplumber

# Add scraper directory to path for shared modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "scraper"))
from db import insert_lead

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Regex patterns for data extraction
PHONE_PATTERN = re.compile(
    r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}"
)
EMAIL_PATTERN = re.compile(
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
)
ZIP_PATTERN = re.compile(r"\b3[34]\d{3}\b")  # SW Florida zip codes (33xxx, 34xxx)

# Florida city names in Lee & Collier County
SWFL_CITIES = [
    "fort myers", "cape coral", "lehigh acres", "bonita springs",
    "estero", "naples", "marco island", "immokalee", "golden gate",
    "north fort myers", "sanibel", "fort myers beach", "pine island",
    "matlacha", "ave maria", "everglades city",
]


def extract_leads_from_pdf(filepath: str) -> list[dict]:
    """
    Extract lead information from a PDF file.

    Tries multiple strategies:
    1. Table extraction (structured PDFs)
    2. Text extraction with regex (unstructured PDFs)

    Returns:
        List of lead dictionaries
    """
    leads = []
    logger.info(f"Processing: {filepath}")

    try:
        with pdfplumber.open(filepath) as pdf:
            # Strategy 1: Try table extraction first
            for page_num, page in enumerate(pdf.pages, 1):
                tables = page.extract_tables()
                if tables:
                    for table in tables:
                        table_leads = _parse_table(table)
                        leads.extend(table_leads)

            # Strategy 2: Text extraction with regex
            if not leads:
                full_text = ""
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        full_text += text + "\n"

                if full_text:
                    text_leads = _parse_text(full_text)
                    leads.extend(text_leads)

    except Exception as e:
        logger.error(f"Error reading PDF {filepath}: {e}")

    logger.info(f"Extracted {len(leads)} leads from {os.path.basename(filepath)}")
    return leads


def _parse_table(table: list[list]) -> list[dict]:
    """Parse a table extracted from PDF into leads."""
    leads = []
    if not table or len(table) < 2:
        return leads

    # Try to identify header row
    header = [str(cell).lower().strip() if cell else "" for cell in table[0]]

    # Map common column headers
    col_map = {}
    for i, h in enumerate(header):
        if any(w in h for w in ["name", "nome", "client", "customer", "owner"]):
            col_map["name"] = i
        elif any(w in h for w in ["phone", "tel", "cell", "mobile", "fone"]):
            col_map["phone"] = i
        elif any(w in h for w in ["email", "e-mail"]):
            col_map["email"] = i
        elif any(w in h for w in ["address", "addr", "street", "endereco"]):
            col_map["address"] = i
        elif any(w in h for w in ["city", "cidade"]):
            col_map["city"] = i
        elif any(w in h for w in ["zip", "cep", "postal"]):
            col_map["zip"] = i

    # Process data rows
    for row in table[1:]:
        if not row or all(cell is None or str(cell).strip() == "" for cell in row):
            continue

        lead = {"source": "pdf"}

        if "name" in col_map and row[col_map["name"]]:
            lead["full_name"] = str(row[col_map["name"]]).strip().title()

        if "phone" in col_map and row[col_map["phone"]]:
            phone = _normalize_phone(str(row[col_map["phone"]]))
            if phone:
                lead["phone"] = phone

        if "email" in col_map and row[col_map["email"]]:
            email = str(row[col_map["email"]]).strip().lower()
            if EMAIL_PATTERN.match(email):
                lead["email"] = email

        if "address" in col_map and row[col_map["address"]]:
            lead["address"] = str(row[col_map["address"]]).strip().title()

        if "city" in col_map and row[col_map["city"]]:
            lead["city"] = str(row[col_map["city"]]).strip().title()

        if "zip" in col_map and row[col_map["zip"]]:
            lead["zip_code"] = str(row[col_map["zip"]]).strip()[:5]

        # Only add if we have at least a name or phone
        if lead.get("full_name") or lead.get("phone"):
            # Try to detect county from city
            city = (lead.get("city") or "").lower()
            if city in ["naples", "marco island", "immokalee", "golden gate", "ave maria", "everglades city"]:
                lead["county"] = "Collier"
            elif city:
                lead["county"] = "Lee"

            lead["status"] = "new"
            lead["renovation_score"] = 30  # Base score for existing contacts
            leads.append(lead)

    # If no header mapping worked, try raw extraction
    if not col_map:
        for row in table:
            if not row:
                continue
            row_text = " ".join(str(cell) for cell in row if cell)
            text_leads = _parse_text(row_text)
            leads.extend(text_leads)

    return leads


def _parse_text(text: str) -> list[dict]:
    """Extract leads from unstructured text using regex patterns."""
    leads = []

    # Find all phone numbers
    phones = PHONE_PATTERN.findall(text)
    emails = EMAIL_PATTERN.findall(text)

    # Split text into lines for context
    lines = text.split("\n")

    for phone in phones:
        normalized = _normalize_phone(phone)
        if not normalized:
            continue

        lead = {
            "phone": normalized,
            "source": "pdf",
            "status": "new",
            "renovation_score": 25,
        }

        # Try to find name near the phone number
        for line in lines:
            if phone in line:
                # Look for a name before the phone
                name_part = line.split(phone)[0].strip()
                # Clean up common separators
                name_part = re.sub(r"[:\-|,]+$", "", name_part).strip()
                if name_part and len(name_part) > 2 and not name_part.isdigit():
                    lead["full_name"] = name_part.title()

                # Look for email in the same line
                line_emails = EMAIL_PATTERN.findall(line)
                if line_emails:
                    lead["email"] = line_emails[0].lower()

                # Look for zip code
                zips = ZIP_PATTERN.findall(line)
                if zips:
                    lead["zip_code"] = zips[0]

                break

        leads.append(lead)

    return leads


def _normalize_phone(raw: str) -> str | None:
    """Normalize a phone number to +1XXXXXXXXXX format."""
    digits = re.sub(r"\D", "", raw)

    if len(digits) == 10:
        return f"+1{digits}"
    elif len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    elif len(digits) == 7:
        return None  # Too short, skip

    return None


def process_path(path: str) -> dict:
    """Process a file or directory of PDFs."""
    stats = {"files": 0, "leads_found": 0, "leads_inserted": 0, "leads_skipped": 0}

    path = Path(path)

    if path.is_file() and path.suffix.lower() == ".pdf":
        files = [path]
    elif path.is_dir():
        files = sorted(path.glob("*.pdf"))
    else:
        logger.error(f"Invalid path: {path}")
        return stats

    for pdf_file in files:
        stats["files"] += 1
        leads = extract_leads_from_pdf(str(pdf_file))
        stats["leads_found"] += len(leads)

        for lead in leads:
            result = insert_lead(lead)
            if result:
                stats["leads_inserted"] += 1
            else:
                stats["leads_skipped"] += 1

    return stats


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python seed_from_pdf.py <pdf_file_or_directory>")
        print("  python seed_from_pdf.py leads.pdf")
        print("  python seed_from_pdf.py /path/to/pdfs/")
        sys.exit(1)

    result = process_path(sys.argv[1])
    print(f"\nImport Results:")
    print(f"  Files processed: {result['files']}")
    print(f"  Leads found:     {result['leads_found']}")
    print(f"  Leads inserted:  {result['leads_inserted']}")
    print(f"  Leads skipped:   {result['leads_skipped']} (duplicates)")
