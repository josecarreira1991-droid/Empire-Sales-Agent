"""Web scraper for Collier County building permits (CityView Portal).

Source: https://cvportal.colliercountyfl.gov/cityviewweb/
Platform: CityView (Harris Computers)
Requires: Selenium (JavaScript-rendered, may have CAPTCHA)

Scrapes: Building permits for remodeling, roofing, construction
Target: Homeowners with active renovation projects in Collier County, FL
"""

import time
import logging
from datetime import datetime, timedelta

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from bs4 import BeautifulSoup

from db import insert_permit, log_scraping_run, complete_scraping_run

logger = logging.getLogger(__name__)

CITYVIEW_URL = "https://cvportal.colliercountyfl.gov/cityviewweb/"
PERMIT_SEARCH_URL = "https://cvportal.colliercountyfl.gov/CityViewWeb/Permit/Search"

RENOVATION_KEYWORDS = [
    "remodel", "renovation", "addition", "alteration", "interior",
    "kitchen", "bathroom", "flooring", "roof", "re-roof",
    "plumbing", "electrical", "mechanical", "hvac",
]


def get_chrome_driver() -> webdriver.Chrome:
    """Create a headless Chrome WebDriver."""
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


def scrape_collier_permits(days_back: int = 1, max_pages: int = 20) -> list[dict]:
    """
    Scrape recent building permits from Collier County CityView portal.

    Args:
        days_back: How many days back to search
        max_pages: Maximum result pages to process

    Returns:
        List of permit dictionaries
    """
    run_id = log_scraping_run("collier_county_permits")
    permits = []
    errors = 0
    driver = None

    try:
        driver = get_chrome_driver()
        logger.info("Navigating to Collier County CityView portal...")
        driver.get(PERMIT_SEARCH_URL)

        # Wait for page load
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "form"))
        )
        time.sleep(3)

        # Check for CAPTCHA
        page_source = driver.page_source.lower()
        if "captcha" in page_source or "recaptcha" in page_source:
            logger.warning("CAPTCHA detected on Collier County portal. Skipping scrape.")
            complete_scraping_run(
                run_id,
                errors=1,
                error_details="CAPTCHA detected - manual intervention required",
                status="failed",
            )
            return []

        # Set date range
        start_date = (datetime.now() - timedelta(days=days_back)).strftime("%m/%d/%Y")
        end_date = datetime.now().strftime("%m/%d/%Y")

        # Try to find and fill date fields
        date_fields = driver.find_elements(By.CSS_SELECTOR, "input[type='date'], input[type='text'][name*='date' i]")
        if len(date_fields) >= 2:
            date_fields[0].clear()
            date_fields[0].send_keys(start_date)
            date_fields[1].clear()
            date_fields[1].send_keys(end_date)

        # Submit search
        search_buttons = driver.find_elements(
            By.CSS_SELECTOR, "button[type='submit'], input[type='submit'], button.btn-primary"
        )
        if search_buttons:
            search_buttons[0].click()
            time.sleep(5)

        # Process results
        page = 1
        while page <= max_pages:
            logger.info(f"Processing page {page}...")
            page_permits = _parse_cityview_results(driver)
            permits.extend(page_permits)

            if not page_permits:
                break

            # Try next page
            try:
                next_btns = driver.find_elements(
                    By.CSS_SELECTOR, "a.next, li.next a, a[aria-label='Next']"
                )
                if next_btns:
                    next_btns[0].click()
                    time.sleep(3)
                    page += 1
                else:
                    break
            except Exception:
                break

        # Insert into database
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
        logger.info(f"Collier County: Found {len(permits)} permits, {new_count} new")

    except Exception as e:
        logger.error(f"Collier County scraper error: {e}")
        complete_scraping_run(run_id, errors=1, error_details=str(e), status="failed")

    finally:
        if driver:
            driver.quit()

    return permits


def _parse_cityview_results(driver) -> list[dict]:
    """Parse CityView search results page."""
    permits = []

    try:
        soup = BeautifulSoup(driver.page_source, "lxml")

        # CityView uses table-based results
        tables = soup.find_all("table", class_=lambda x: x and "grid" in x.lower()) or soup.find_all("table")

        for table in tables:
            rows = table.find_all("tr")[1:]  # Skip header
            for row in rows:
                cells = row.find_all("td")
                if len(cells) < 3:
                    continue

                # Extract permit data (column order may vary)
                permit_data = [_clean_text(cell) for cell in cells]

                permit = {
                    "county": "Collier",
                    "permit_number": permit_data[0] if len(permit_data) > 0 else None,
                    "permit_type": permit_data[1] if len(permit_data) > 1 else None,
                    "site_address": permit_data[2] if len(permit_data) > 2 else None,
                    "description": permit_data[3] if len(permit_data) > 3 else None,
                    "status": permit_data[4] if len(permit_data) > 4 else None,
                    "applied_date": _parse_date(permit_data[5]) if len(permit_data) > 5 else None,
                }

                # Filter for renovation-related permits
                combined = f"{permit.get('permit_type', '')} {permit.get('description', '')}".lower()
                is_renovation = any(kw in combined for kw in RENOVATION_KEYWORDS)

                if is_renovation and permit["permit_number"]:
                    permits.append(permit)

        # Also try div-based layout (some CityView versions)
        if not permits:
            cards = soup.find_all("div", class_=lambda x: x and ("card" in x.lower() or "result" in x.lower()))
            for card in cards:
                text = card.get_text(" ", strip=True).lower()
                if any(kw in text for kw in RENOVATION_KEYWORDS):
                    links = card.find_all("a")
                    permit_num = links[0].get_text(strip=True) if links else None
                    if permit_num:
                        permits.append({
                            "county": "Collier",
                            "permit_number": permit_num,
                            "description": text[:500],
                        })

    except Exception as e:
        logger.error(f"Error parsing CityView results: {e}")

    return permits


def _clean_text(element) -> str:
    """Extract and clean text from a BeautifulSoup element."""
    if element is None:
        return ""
    return " ".join(element.get_text(strip=True).split())


def _parse_date(date_str: str):
    """Parse a date string from CityView."""
    if not date_str:
        return None
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%b %d, %Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            continue
    return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = scrape_collier_permits(days_back=7)
    print(f"Scraped {len(results)} renovation permits from Collier County")
