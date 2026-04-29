"""
Scrape MB counselor list from Scoutbook and export to CSV.

Requires an active logged-in Chrome session with remote debugging enabled:
  pkill -x "Google Chrome"
  open -a "Google Chrome" --args --remote-debugging-port=9222 --no-first-run
  # Then log in to scoutbook.scouting.org in that browser

Usage:
  python3 fetch_counselors.py --url "https://scoutbook.scouting.org/mobile/dashboard/admin/counselorresults.asp?UnitID=93571&MeritBadgeID=30&Proximity=25&Availability=Available&zip=45245&formCouncilID=77&formDistrictID=2302&formFName=&formLName=&isformZipNull=False&formWorldwide=&Page=1"
  python3 fetch_counselors.py --url "<first page URL>" --output counselors.csv
"""

import argparse
import csv
import re
import sys
from urllib.parse import urlencode, urlparse, parse_qs, urlunparse

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


def parse_counselors(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    counselors = []

    for li in soup.select("ul[data-role='listview'] li[data-theme='d']"):
        c = {}

        # Distance
        miles_el = li.select_one(".miles")
        c["miles"] = miles_el.get_text(strip=True).replace(" mi", "") if miles_el else ""

        # Name
        name_div = li.select_one("div[style*='margin-left']")
        if not name_div:
            continue
        name_text = name_div.contents[0].strip() if name_div.contents else ""
        c["name"] = name_text

        # YPT expiration
        ypt_div = li.select_one(".yptDate")
        if ypt_div:
            ypt_text = ypt_div.get_text(strip=True)
            c["ypt_expires"] = ypt_text.replace("Expires:", "").strip()
        else:
            c["ypt_expires"] = ""

        # Address block
        address_div = li.select_one(".address")
        if address_div:
            addr_html = address_div.decode_contents()
            parts = [p.strip() for p in re.split(r"<br\s*/?>", addr_html) if p.strip()]
            # Strip tags from each part
            parts = [BeautifulSoup(p, "html.parser").get_text(strip=True) for p in parts]

            city_state_zip = ""
            phones = []
            for part in parts:
                if re.match(r".+,\s+[A-Z]{2}\s+\d{5}", part):
                    city_state_zip = part
                elif re.match(r"(Home|Mobile|Work)\s+\(", part):
                    phones.append(part)

            c["city_state_zip"] = city_state_zip
            c["phones"] = "; ".join(phones)

            email_el = address_div.select_one("a[href^='MAILTO:'], a[href^='mailto:']")
            c["email"] = email_el.get_text(strip=True) if email_el else ""
        else:
            c["city_state_zip"] = c["phones"] = c["email"] = ""

        # Merit badges
        badges = [el.get_text(strip=True) for el in li.select(".mb")]
        c["merit_badges"] = "; ".join(badges)
        c["badge_count"] = len(badges)

        # Working with scouts
        working_div = li.select_one(".workingWith div")
        c["working_with"] = working_div.get_text(strip=True) if working_div else ""

        counselors.append(c)

    return counselors


def build_page_url(base_url: str, page: int) -> str:
    parsed = urlparse(base_url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    params["Page"] = [str(page)]
    flat = {k: v[0] for k, v in params.items()}
    new_query = urlencode(flat)
    return urlunparse(parsed._replace(query=new_query))


def get_page_count(html: str) -> int:
    soup = BeautifulSoup(html, "html.parser")
    el = soup.select_one("input#pageCount")
    if el and el.get("value"):
        return int(el["value"])
    # Fallback: count pagination links
    links = soup.select(".mobileNavigation a[data-role='button']")
    pages = []
    for a in links:
        try:
            pages.append(int(a.get_text(strip=True)))
        except ValueError:
            pass
    return max(pages) if pages else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True, help="First-page counselor results URL")
    parser.add_argument("--output", default="counselors.csv", help="Output CSV path")
    parser.add_argument("--cdp-url", default="http://localhost:9222", help="Chrome DevTools Protocol URL")
    args = parser.parse_args()

    all_counselors = []

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(args.cdp_url)
        except Exception as e:
            print(f"ERROR: Could not connect to Chrome at {args.cdp_url}")
            print("Start Chrome with: open -a 'Google Chrome' --args --remote-debugging-port=9222 --no-first-run")
            print("Then log in to scoutbook.scouting.org")
            sys.exit(1)

        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.new_page()

        # Load page 1 to get total page count
        print(f"Fetching page 1...")
        page.goto(args.url, wait_until="domcontentloaded", timeout=30000)
        html = page.content()
        page_count = get_page_count(html)
        print(f"  Found {page_count} pages")

        counselors = parse_counselors(html)
        print(f"  Parsed {len(counselors)} counselors")
        all_counselors.extend(counselors)

        # Fetch remaining pages
        for pg in range(2, page_count + 1):
            url = build_page_url(args.url, pg)
            print(f"Fetching page {pg}/{page_count}...")
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            html = page.content()
            counselors = parse_counselors(html)
            print(f"  Parsed {len(counselors)} counselors")
            all_counselors.extend(counselors)

        page.close()

    if not all_counselors:
        print("No counselors found — check your URL and login state.")
        sys.exit(1)

    fieldnames = ["name", "miles", "city_state_zip", "phones", "email",
                  "ypt_expires", "badge_count", "merit_badges", "working_with"]

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_counselors)

    print(f"\nDone. {len(all_counselors)} counselors written to {args.output}")


if __name__ == "__main__":
    main()
