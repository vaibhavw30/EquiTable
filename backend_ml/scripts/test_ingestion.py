"""
Test Ingestion Script - Verify Firecrawl scraping works correctly

Scrapes sample pantry URLs and saves results to scraped_samples.json
in the project root for inspection. Does not interact with the database.

Usage: python -m scripts.test_ingestion
"""

import json
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.scraper import ScraperService

targets = [
    "https://midtownassistancecenter.org/assistance",
    "https://tocohills.org/food-pantry",
    "https://svdpgeorgia.org/get-help/food-assistance/",
]

# Output file path (in project root)
OUTPUT_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "scraped_samples.json"
)


def main():
    """Scrape target URLs and save results to JSON."""
    print("=" * 60)
    print("EquiTable - Firecrawl Ingestion Test (Phase 2)")
    print("=" * 60)
    print(f"Targets: {len(targets)} URLs\n")

    # Initialize scraper
    try:
        scraper = ScraperService()
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    results = []

    for i, url in enumerate(targets, 1):
        print(f"[{i}/{len(targets)}] Scraping: {url}")

        data = scraper.scrape_url(url)

        if data:
            results.append({"url": url, "raw_content": data})
            print(f"  SUCCESS - {len(data)} characters\n")
        else:
            print(f"  FAILED - No content returned\n")

    # Summary
    print("=" * 60)
    print(f"Results: {len(results)}/{len(targets)} succeeded")
    print("=" * 60)

    # Save to JSON
    print(f"\nSaving to: {OUTPUT_FILE}")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print("Done!")


if __name__ == "__main__":
    main()
