#!/usr/bin/env python3
"""
Auto-Scrape Scholarship & Research Funding Sources in Thailand
Reads from website_configs.json and outputs to scholarships.json
Supports: BeautifulSoup (static), Selenium (JS-rendered), API
"""

import json
import logging
import os
import re
import sys
import time
import hashlib
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("scraper.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("scholarship_scraper")

# ─── Constants ───────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
CONFIG_FILE = BASE_DIR / "website_configs.json"
OUTPUT_FILE = BASE_DIR / "scholarships.json"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "th,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
REQUEST_TIMEOUT = 20
MAX_RETRIES = 3
RETRY_DELAY = 5

# ─── Relevance Keywords (for field matching) ──────────────────────────────────
RELEVANCE_KEYWORDS = [
    # Thai
    "วิศวกรรมเครื่องกล", "หุ่นยนต์", "วิศวกรรมการแพทย์", "การแพทย์",
    "ชีวกลศาสตร์", "Biomedical", "Health Tech", "MedTech",
    "ไฟฟ้า", "อิเล็กทรอนิกส์", "ควบคุม", "Smart Manufacturing",
    "Industry 4.0", "AI", "Data Science", "Robotics", "Mechanical",
    "Electronics", "Medical", "Biomechanics", "Automation",
    # English
    "engineering", "robot", "medical", "health", "biomedical",
    "electrical", "electronic", "automation", "manufacturing",
    "artificial intelligence", "machine learning", "data",
    "science", "research", "scholarship", "fellowship",
    "ทุน", "วิจัย", "การศึกษา", "นวัตกรรม",
]


# ─── Session ───────────────────────────────────────────────────────────────────
def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


# ─── Helper: Text cleaning ───────────────────────────────────────────────────
def clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_text(element) -> str:
    if element is None:
        return ""
    return clean_text(element.get_text())


def normalize_url(href: str, base: str) -> str:
    if not href:
        return ""
    if href.startswith("http"):
        return href
    return urljoin(base, href)


def is_relevant(text: str) -> bool:
    """Check if text contains any relevance keywords."""
    if not text:
        return True  # no text = can't filter, include it
    t = text.lower()
    return any(kw.lower() in t for kw in RELEVANCE_KEYWORDS)


def make_id(source_name: str, title: str, url: str) -> str:
    """Generate a stable ID for deduplication."""
    raw = f"{source_name}|{title}|{url}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def parse_amount(text: str) -> str:
    """Try to extract a monetary amount from text."""
    if not text:
        return ""
    # e.g. "100,000 บาท", "50,000"
    m = re.search(r"[\d,]+(?:\.\d+)?\s*(?:บาท|THB|USD|\$|บ\.?)", text, re.IGNORECASE)
    if m:
        return m.group(0)
    m = re.search(r"[\d,]+(?:\.\d+)?", text)
    if m:
        return m.group(0)
    return ""


def parse_deadline(text: str) -> str:
    """Try to extract a date/deadline from text."""
    if not text:
        return ""
    # Thai date patterns: 31 มีนาคม 2568, 31/03/2568, 2026-03-31
    thai_months = {
        "มกราคม": "01", "กุมภาพันธ์": "02", "มีนาคม": "03",
        "เมษายน": "04", "พฤษภาคม": "05", "มิถุนายน": "06",
        "กรกฎาคม": "07", "สิงหาคม": "08", "กันยายน": "09",
        "ตุลาคม": "10", "พฤศจิกายน": "11", "ธันวาคม": "12",
    }
    # Try standard date patterns
    patterns = [
        r"(\d{1,2})\s*(?:ม\.?\s?ค\.?|มีนาคม)\s*(\d{4})",
        r"(\d{4})-(\d{2})-(\d{2})",
        r"(\d{1,2})/(\d{1,2})/(\d{4})",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(0)
    return clean_text(text)


# ─── BeautifulSoup Scraper ────────────────────────────────────────────────────
class BeautifulSoupScraper:
    name = "beautifulsoup"

    def __init__(self, session: requests.Session):
        self.session = session

    def fetch(self, url: str) -> BeautifulSoup:
        for attempt in range(MAX_RETRIES):
            try:
                resp = self.session.get(url, timeout=REQUEST_TIMEOUT)
                resp.raise_for_status()
                resp.encoding = resp.apparent_encoding or "utf-8"
                return BeautifulSoup(resp.text, "lxml")
            except requests.RequestException as e:
                logger.warning(f"  Attempt {attempt+1}/{MAX_RETRIES} failed for {url}: {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
                else:
                    raise

    def scrape_page(self, url: str, config: dict) -> list[dict]:
        soup = self.fetch(url)
        items = []

        title_sel = config.get("title_selector", "h2, h3, .title, article")
        deadline_sel = config.get("deadline_selector", ".date, .deadline, time")
        amount_sel = config.get("amount_selector", ".amount, .budget")
        eligibility_sel = config.get("eligibility_selector", ".description, .summary, p")
        link_sel = config.get("link_selector", "a")
        base = config.get("link_base_url", url)

        # Find all article/card containers
        containers = soup.select("article, .card, .news-item, .scholarship-item, .post")
        if not containers:
            containers = soup.select("body")

        for container in containers:
            # Extract title
            title_el = container.select_one(title_sel)
            title = extract_text(title_el)
            if not title or len(title) < 5:
                continue

            # Skip non-relevant titles
            if not is_relevant(title):
                continue

            # Extract link
            link_el = container.select_one(link_sel)
            link = ""
            if link_el and link_el.get("href"):
                link = normalize_url(link_el["href"], base)

            # Extract deadline
            deadline_el = container.select_one(deadline_sel)
            deadline = parse_deadline(extract_text(deadline_el))

            # Extract amount
            amount_el = container.select_one(amount_sel)
            amount = parse_amount(extract_text(amount_el))

            # Extract eligibility/description
            eligibility_el = container.select_one(eligibility_sel)
            eligibility = extract_text(eligibility_el)
            if not eligibility:
                # Fallback: get all paragraphs
                paras = container.select("p")
                eligibility = " ".join(extract_text(p) for p in paras[:3])

            items.append({
                "title": title,
                "url": link,
                "deadline": deadline,
                "amount": amount,
                "eligibility": eligibility[:500] if eligibility else "",
                "source": config.get("name", ""),
                "source_type": config.get("type", ""),
                "fields": config.get("fields", []),
            })

        return items

    def paginate(self, url: str, config: dict) -> list[dict]:
        pag_cfg = config.get("pagination", {})
        if not pag_cfg.get("enabled", False):
            return self.scrape_page(url, config)

        max_pages = pag_cfg.get("max_pages", 5)
        next_sel = pag_cfg.get("next_button_selector", "a.next")
        all_items = []

        current_url = url
        for page in range(1, max_pages + 1):
            logger.info(f"  Page {page}: {current_url}")
            try:
                items = self.scrape_page(current_url, config)
                if not items:
                    logger.info(f"  No items found on page {page}, stopping.")
                    break
                all_items.extend(items)

                # Find next button
                soup = self.fetch(current_url)
                next_btn = soup.select_one(next_sel)
                if not next_btn or not next_btn.get("href"):
                    logger.info(f"  No next button found, stopping at page {page}.")
                    break
                next_url = normalize_url(next_btn["href"], config.get("link_base_url", url))
                if next_url == current_url:
                    break
                current_url = next_url
                time.sleep(1)
            except Exception as e:
                logger.error(f"  Error on page {page}: {e}")
                break

        return all_items


# ─── Selenium Scraper ──────────────────────────────────────────────────────────
class SeleniumScraper:
    name = "selenium"

    def __init__(self):
        self.driver = None

    def _get_driver(self):
        if self.driver is not None:
            return self.driver
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            from webdriver_manager.chrome import ChromeDriverManager

            opts = Options()
            opts.add_argument("--headless=new")
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument(f"user-agent={HEADERS['User-Agent']}")
            opts.add_experimental_option("excludeSwitches", ["enable-automation"])
            opts.add_experimental_option("useAutomationExtension", False)

            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=opts)
            self.driver.set_page_load_timeout(REQUEST_TIMEOUT)
            logger.info("Selenium WebDriver started successfully.")
        except Exception as e:
            logger.error(f"Failed to start Selenium: {e}")
            raise
        return self.driver

    def fetch(self, url: str) -> BeautifulSoup:
        driver = self._get_driver()
        for attempt in range(MAX_RETRIES):
            try:
                driver.get(url)
                time.sleep(2)  # wait for JS to render
                return BeautifulSoup(driver.page_source, "lxml")
            except Exception as e:
                logger.warning(f"  Selenium attempt {attempt+1}/{MAX_RETRIES} failed: {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
                else:
                    raise

    def scrape_page(self, url: str, config: dict) -> list[dict]:
        soup = self.fetch(url)
        scraper = BeautifulSoupScraper(None)
        return scraper.scrape_page(url, config)

    def paginate(self, url: str, config: dict) -> list[dict]:
        pag_cfg = config.get("pagination", {})
        if not pag_cfg.get("enabled", False):
            return self.scrape_page(url, config)

        max_pages = pag_cfg.get("max_pages", 5)
        next_sel = pag_cfg.get("next_button_selector", "a.next")
        all_items = []

        current_url = url
        driver = self._get_driver()
        for page in range(1, max_pages + 1):
            logger.info(f"  Page {page}: {current_url}")
            try:
                items = self.scrape_page(current_url, config)
                if not items:
                    logger.info(f"  No items found on page {page}, stopping.")
                    break
                all_items.extend(items)

                # Find next button
                soup = self.fetch(current_url)
                next_btn = soup.select_one(next_sel)
                if not next_btn or not next_btn.get("href"):
                    logger.info(f"  No next button found, stopping at page {page}.")
                    break
                next_url = normalize_url(next_btn["href"], config.get("link_base_url", url))
                if next_url == current_url:
                    break
                current_url = next_url
                time.sleep(2)
            except Exception as e:
                logger.error(f"  Error on page {page}: {e}")
                break

        return all_items

    def close(self):
        if self.driver:
            self.driver.quit()
            self.driver = None


# ─── Scraper Factory ───────────────────────────────────────────────────────────
def get_scraper(method: str):
    method = method.lower().strip()
    if method == "selenium":
        return SeleniumScraper()
    elif method == "beautifulsoup":
        return BeautifulSoupScraper(make_session())
    else:
        logger.warning(f"Unknown method '{method}', defaulting to beautifulsoup.")
        return BeautifulSoupScraper(make_session())


# ─── Deduplication ─────────────────────────────────────────────────────────────
def deduplicate(new_items: list[dict], existing: list[dict]) -> list[dict]:
    seen_ids = {item["id"] for item in existing}
    result = []
    for item in new_items:
        item_id = make_id(item["source"], item["title"], item["url"])
        item["id"] = item_id
        if item_id not in seen_ids:
            seen_ids.add(item_id)
            result.append(item)
    return result


# ─── Main Scrape ───────────────────────────────────────────────────────────────
def load_config() -> dict:
    if not CONFIG_FILE.exists():
        logger.error(f"Config file not found: {CONFIG_FILE}")
        sys.exit(1)
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return json.load(f)


def load_existing() -> list[dict]:
    if OUTPUT_FILE.exists():
        try:
            with open(OUTPUT_FILE, encoding="utf-8") as f:
                data = json.load(f)
                return data.get("scholarships", [])
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Could not load existing output: {e}, starting fresh.")
    return []


def save_output(scholarships: list[dict], config_version: str):
    output = {
        "version": config_version,
        "updated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "total": len(scholarships),
        "scholarships": scholarships,
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved {len(scholarships)} scholarships to {OUTPUT_FILE}")


def main():
    start = datetime.now()
    logger.info("=" * 60)
    logger.info(" Scholarship Scraper Started ")
    logger.info(f" Config: {CONFIG_FILE}")
    logger.info("=" * 60)

    config = load_config()
    sources = config.get("sources", [])
    config_version = config.get("version", "1.0")

    logger.info(f"Loaded {len(sources)} sources from config.")

    existing = load_existing()
    logger.info(f"Loaded {len(existing)} existing scholarship entries.")

    all_items = list(existing)
    seen_ids = {item["id"] for item in existing}

    selenium_scraper = None

    for idx, source in enumerate(sources, 1):
        name = source.get("name", f"Source-{idx}")
        url = source.get("url", "")
        method = source.get("scrape_config", {}).get("method", "beautifulsoup")
        stype = source.get("type", "")

        logger.info(f"[{idx}/{len(sources)}] Scraping: {name} ({method})")
        logger.info(f"  URL: {url}")

        try:
            # Use singleton selenium scraper to reuse browser session
            if method == "selenium":
                if selenium_scraper is None:
                    selenium_scraper = SeleniumScraper()
                scraper = selenium_scraper
            else:
                scraper = get_scraper("beautifulsoup")

            items = scraper.paginate(url, source.get("scrape_config", {}))

            # Assign IDs and deduplicate
            new_items = []
            for item in items:
                item_id = make_id(item["source"], item["title"], item["url"])
                item["id"] = item_id
                if item_id not in seen_ids:
                    seen_ids.add(item_id)
                    new_items.append(item)

            if new_items:
                all_items.extend(new_items)
                logger.info(f"  ✓ Found {len(new_items)} new scholarships (total: {len(all_items)})")
            else:
                logger.info(f"  ○ No new scholarships found.")

        except Exception as e:
            logger.error(f"  ✗ Error scraping {name}: {e}")

        time.sleep(1)  # be polite between sources

    # Close selenium if used
    if selenium_scraper:
        selenium_scraper.close()

    # Sort by source + title
    all_items.sort(key=lambda x: (x.get("source", ""), x.get("title", "")))

    save_output(all_items, config_version)

    elapsed = datetime.now() - start
    logger.info("=" * 60)
    logger.info(f" Done! Scraped {len(all_items)} total scholarships in {elapsed}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
