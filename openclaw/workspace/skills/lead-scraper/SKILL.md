---
name: lead-scraper
description: "Runs web scraping scripts to collect homeowner leads from Lee and Collier County public records. Use for daily automated scraping, manual scrape triggers, or NAL file imports. Scrapes building permits and property records using Python with BeautifulSoup and Selenium."
tools:
  - Bash
  - Read
---

# Lead Scraper - Web Scraping for Homeowner Leads

Collects leads from public government records in Lee and Collier County, Florida.

## Daily Automated Scrape (Cron: 06:00 AM ET)

Run the full daily scrape:
```bash
cd ~/empire-sales-agent && source venv/bin/activate && python scripts/scraper/main_scraper.py --once
```

This will:
1. Scrape Lee County Accela portal for new building permits (last 24h)
2. Scrape Collier County CityView portal for new building permits (last 24h)
3. Score each new lead using the lead_scorer
4. Insert qualified leads (score >= 20) into the database
5. Log the run in scraping_runs table

## Manual Scrape Commands

### Scrape Lee County only:
```bash
cd ~/empire-sales-agent && source venv/bin/activate && python scripts/scraper/main_scraper.py --lee --days 7
```

### Scrape Collier County only:
```bash
cd ~/empire-sales-agent && source venv/bin/activate && python scripts/scraper/main_scraper.py --collier --days 7
```

### Import NAL file (Florida Dept of Revenue):
```bash
cd ~/empire-sales-agent && source venv/bin/activate && python scripts/scraper/main_scraper.py --nal /path/to/file.csv --county 36
```
County codes: 36 = Lee, 11 = Collier

## Check scraping status

```bash
psql -U empire -d empire_leads -c "
SELECT source, started_at, status, records_found, records_new, errors
FROM scraping_runs ORDER BY started_at DESC LIMIT 10
"
```

## Lead sources explained

| Source | How we get it | Data quality |
|--------|---------------|-------------|
| FL DOR NAL files | Email request, CSV download | Best — full property records |
| Lee County GIS | Direct shapefile download | Great — parcel + ownership |
| Lee County Accela | Selenium scraping | Good — active permits |
| Collier County CityView | Selenium scraping | Good — active permits (CAPTCHA risk) |

## Troubleshooting

### Scraper failing?
- Check Chrome/Chromium is installed: `which chromium-browser`
- Check ChromeDriver: `which chromedriver`
- Check logs: `cat ~/empire-sales-agent/data/scraper.log`
- Check scraping_runs for errors: `SELECT * FROM scraping_runs WHERE status = 'failed' ORDER BY id DESC LIMIT 5`

### CAPTCHA on Collier County?
- CityView sometimes shows CAPTCHA. The scraper detects this and skips.
- Fallback: submit a public records request for bulk permit data
