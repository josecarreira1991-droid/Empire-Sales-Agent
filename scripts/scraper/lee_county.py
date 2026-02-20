"""Web scraper for Lee County building permits (Accela Citizen Access).

Source: https://aca-prod.accela.com/LEECO/
Platform: Accela Citizen Access (ASP.NET with ViewState)
Requires: Selenium (JavaScript-rendered pages)

Scrapes: Building permits for remodeling, roofing, electrical, plumbing
Target: Homeowners with active renovation projects in Lee County, FL
"""

import time
import logging
from datetime import datetime, timedelta

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from bs4 import BeautifulSoup

from db import insert_permit, log_scraping_run, complete_scraping_run

logger = logging.getLogger(__name__)

ACCELA_URL = "https://aca-prod.accela.com/LEECO/Cap/CapHome.aspx?module=Permitting&TabName=Home"

# Permit types that signal renovation intent
RENOVATION_PERMIT_TYPES = [
    "Building",
    "Residential",
    "Alteration",
    "Addition",
    "Remodel",
    "Interior",
    "Roof",
    "Re-Roof",
]


def get_chrome_driver() -> webdriver.Chrome:
    """Create a headless Chrome WebDriver for scraping."""
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    try:
        import undetected_chromedriver as uc
        driver = uc.Chrome(options=options, headless=True)
    except ImportError:
        service = Service()
        driver = webdriver.Chrome(service=service, options=options)

    driver.implicitly_wait(10)
    return driver


def scrape_lee_permits(days_back: int = 1, max_pages: int = 20) -> list[dict]:
    """
    Scrape recent building permits from Lee County Accela portal.

    Args:
        days_back: How many days back to search (default: 1 for daily runs)
        max_pages: Maximum result pages to process

    Returns:
        List of permit dictionaries
    """
    run_id = log_scraping_run("lee_county_permits")
    permits = []
    errors = 0
    driver = None

    try:
        driver = get_chrome_driver()
        logger.info("Navigating to Lee County Accela portal...")
        driver.get(ACCELA_URL)

        # Wait for page to load
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.ID, "ctl00_PlaceHolderMain_generalSearchForm_txtGSStartDate"))
        )
        time.sleep(2)  # Extra wait for ASP.NET ViewState

        # Set date range
        start_date = (datetime.now() - timedelta(days=days_back)).strftime("%m/%d/%Y")
        end_date = datetime.now().strftime("%m/%d/%Y")

        start_field = driver.find_element(
            By.ID, "ctl00_PlaceHolderMain_generalSearchForm_txtGSStartDate"
        )
        start_field.clear()
        start_field.send_keys(start_date)

        end_field = driver.find_element(
            By.ID, "ctl00_PlaceHolderMain_generalSearchForm_txtGSEndDate"
        )
        end_field.clear()
        end_field.send_keys(end_date)

        # Click search
        search_btn = driver.find_element(
            By.ID, "ctl00_PlaceHolderMain_btnNewSearch"
        )
        search_btn.click()

        # Wait for results
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CLASS_NAME, "ACA_Grid_OverFlow"))
        )
        time.sleep(2)

        # Process result pages
        page = 1
        while page <= max_pages:
            logger.info(f"Processing page {page}...")
            page_permits = _parse_results_page(driver)
            permits.extend(page_permits)

            if not page_permits:
                break

            # Try to go to next page
            try:
                next_link = driver.find_element(
                    By.XPATH, "//a[contains(@class, 'aca_pagination_PrevNext') and contains(text(), 'Next')]"
                )
                next_link.click()
                time.sleep(3)  # Rate limiting
                page += 1
            except Exception:
                break  # No more pages

        # Insert permits into database
        new_count = 0
        for permit in permits:
            result = insert_permit(permit)
            if result:
                new_count += 1

        complete_scraping_run(
            run_id,
            records_found=len(permits),
            records_new=new_count,
            errors=errors,
        )
        logger.info(f"Lee County: Found {len(permits)} permits, {new_count} new")

    except Exception as e:
        logger.error(f"Lee County scraper error: {e}")
        complete_scraping_run(run_id, errors=1, error_details=str(e), status="failed")
        errors += 1

    finally:
        if driver:
            driver.quit()

    return permits


def _parse_results_page(driver) -> list[dict]:
    """Parse a single page of Accela search results."""
    permits = []

    try:
        soup = BeautifulSoup(driver.page_source, "lxml")
        rows = soup.select("table.ACA_Grid_OverFlow tr[class*='ACA_TabRow']")

        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 5:
                continue

            permit = {
                "county": "Lee",
                "permit_number": _clean_text(cells[1]),
                "permit_type": _clean_text(cells[2]),
                "description": _clean_text(cells[3]),
                "site_address": _clean_text(cells[4]),
                "status": _clean_text(cells[5]) if len(cells) > 5 else None,
                "applied_date": _parse_date(_clean_text(cells[6])) if len(cells) > 6 else None,
            }

            # Only keep renovation-related permits
            combined = f"{permit['permit_type']} {permit['description']}".lower()
            is_renovation = any(
                kw.lower() in combined for kw in RENOVATION_PERMIT_TYPES
            )

            if is_renovation and permit["permit_number"]:
                permits.append(permit)

    except Exception as e:
        logger.error(f"Error parsing results page: {e}")

    return permits


def _clean_text(element) -> str:
    """Extract and clean text from a BeautifulSoup element."""
    if element is None:
        return ""
    text = element.get_text(strip=True)
    return " ".join(text.split())


def _parse_date(date_str: str):
    """Parse a date string from Accela (MM/DD/YYYY format)."""
    if not date_str:
        return None
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = scrape_lee_permits(days_back=7)
    print(f"Scraped {len(results)} renovation permits from Lee County")
