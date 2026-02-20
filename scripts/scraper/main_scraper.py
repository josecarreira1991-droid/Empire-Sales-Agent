"""Main scraper orchestrator for Empire Sales Agent.

Runs all scrapers on schedule or on-demand.
Daily cron at 06:00 AM ET via OpenClaw.
"""

import sys
import time
import logging
import argparse
from datetime import datetime

import schedule

from lee_county import scrape_lee_permits
from collier_county import scrape_collier_permits
from nal_processor import process_nal_file

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/app/data/scraper.log" if sys.platform == "linux" else "scraper.log"),
    ],
)
logger = logging.getLogger("main_scraper")


def run_daily_scrape():
    """Run all daily scraping tasks."""
    logger.info("=" * 60)
    logger.info(f"Starting daily scrape: {datetime.now()}")
    logger.info("=" * 60)

    results = {"lee_permits": 0, "collier_permits": 0, "errors": []}

    # 1. Scrape Lee County permits
    try:
        logger.info("--- Lee County Permits ---")
        lee_permits = scrape_lee_permits(days_back=1)
        results["lee_permits"] = len(lee_permits)
    except Exception as e:
        logger.error(f"Lee County scraper failed: {e}")
        results["errors"].append(f"Lee County: {e}")

    # Rate limiting between county scrapes
    time.sleep(10)

    # 2. Scrape Collier County permits
    try:
        logger.info("--- Collier County Permits ---")
        collier_permits = scrape_collier_permits(days_back=1)
        results["collier_permits"] = len(collier_permits)
    except Exception as e:
        logger.error(f"Collier County scraper failed: {e}")
        results["errors"].append(f"Collier County: {e}")

    # Summary
    logger.info("=" * 60)
    logger.info(f"Daily scrape complete: {results}")
    logger.info("=" * 60)

    return results


def run_nal_import(filepath: str, county_code: str = None):
    """One-time NAL file import."""
    logger.info(f"Importing NAL file: {filepath}")
    result = process_nal_file(filepath, county_code)
    logger.info(f"NAL import result: {result}")
    return result


def daemon_mode():
    """Run scraper in daemon mode with daily schedule."""
    logger.info("Starting scraper daemon (daily at 06:00 AM ET)...")

    # Schedule daily scrape at 6 AM
    schedule.every().day.at("06:00").do(run_daily_scrape)

    # Run immediately on first start
    run_daily_scrape()

    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Empire Sales Agent - Web Scraper")
    parser.add_argument("--daemon", action="store_true", help="Run in daemon mode (daily schedule)")
    parser.add_argument("--once", action="store_true", help="Run all scrapers once and exit")
    parser.add_argument("--lee", action="store_true", help="Scrape Lee County only")
    parser.add_argument("--collier", action="store_true", help="Scrape Collier County only")
    parser.add_argument("--nal", type=str, help="Import a NAL CSV file")
    parser.add_argument("--county", type=str, help="County code for NAL import (36=Lee, 11=Collier)")
    parser.add_argument("--days", type=int, default=1, help="Days back to scrape (default: 1)")

    args = parser.parse_args()

    if args.daemon:
        daemon_mode()
    elif args.nal:
        run_nal_import(args.nal, args.county)
    elif args.lee:
        scrape_lee_permits(days_back=args.days)
    elif args.collier:
        scrape_collier_permits(days_back=args.days)
    elif args.once:
        run_daily_scrape()
    else:
        parser.print_help()
