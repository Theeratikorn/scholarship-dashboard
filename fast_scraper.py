#!/usr/bin/env python3
"""
Fast Scholarship Scraper - Async + Concurrent
ใช้ aiohttp สำหรับ concurrent requests เร็วกว่า requests แบบเดิมหลายเท่า
"""

import asyncio
import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup

# ─── Setup ───────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
CONFIG_FILE = BASE_DIR / "website_configs.json"
OUTPUT_FILE = BASE_DIR / "scholarships.json"
LOG_FILE = BASE_DIR / "logs" / "fast_scraper.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger("fast_scraper")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "th,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

TIMEOUT = aiohttp.ClientTimeout(total=30)
MAX_CONCURRENT = 5  # Concurrent requests

# ─── Scholarship Keywords ─────────────────────────────────────────────────────
SCHOLARSHIP_KEYWORDS = [
    "ทุน", "ทุนการศึกษา", "ทุนวิจัย", "ทุนเรียน", "ทุนโครงการ",
    "scholarship", "fellowship", "grant", "funding", "award",
    "scholarship for", "research grant", "funding opportunity"
]

EXCLUDE_KEYWORDS = [
    "ทดลอง", "ขาย", "ราคา", "จอง", "สั่งซื้อ",
    "ประมูล", "จัดซื้อ", "รับสมัครงาน",
]

# ─── Helpers ──────────────────────────────────────────────────────────────────
def clean_text(text):
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def is_scholarship(text):
    if not text:
        return True
    text_lower = text.lower()
    
    # Must have scholarship keyword
    has_keyword = any(kw in text_lower for kw in SCHOLARSHIP_KEYWORDS)
    
    # Must not have exclude keyword
    has_exclude = any(kw in text_lower for kw in EXCLUDE_KEYWORDS)
    
    return has_keyword and not has_exclude

def extract_date(text):
    """Extract date from text"""
    patterns = [
        r"(\d{1,2})/(\d{1,2})/(\d{4})",
        r"(\d{4})-(\d{2})-(\d{2})",
        r"(\d{1,2})\s+(มกราคม|กุมภาพันธ์|มีนาคม|เมษายน|พฤษภาคม|มิถุนายน|กรกฎาคม|สิงหาคม|กันยายน|ตุลาคม|พฤศจิกายน|ธันวาคม)\s+(\d{4})",
    ]
    
    thai_months = {
        "มกราคม": 1, "กุมภาพันธ์": 2, "มีนาคม": 3, "เมษายน": 4,
        "พฤษภาคม": 5, "มิถุนายน": 6, "กรกฎาคม": 7, "สิงหาคม": 8,
        "กันยายน": 9, "ตุลาคม": 10, "พฤศจิกายน": 11, "ธันวาคม": 12
    }
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            groups = match.groups()
            if len(groups) == 3:
                if groups[2].isdigit() and int(groups[2]) > 2000:
                    # Format: DD/MM/YYYY or YYYY-MM-DD
                    if "-" in groups[2]:
                        return f"{groups[0]}-{groups[1].zfill(2)}-{groups[2].zfill(2)}"
                    else:
                        return f"{groups[2]}-{groups[1].zfill(2)}-{groups[0].zfill(2)}"
                elif len(groups[0]) == 4:  # YYYY-MM-DD
                    return f"{groups[0]}-{groups[1].zfill(2)}-{groups[2].zfill(2)}"
                else:  # DD/MM/YYYY
                    return f"{groups[2]}-{groups[1].zfill(2)}-{groups[0].zfill(2)}"
    
    return ""

def normalize_url(href, base):
    if not href:
        return ""
    if href.startswith("http"):
        return href
    return urljoin(base, href)

# ─── Scraper ──────────────────────────────────────────────────────────────────
async def scrape_page(session, url, source_name, semaphore):
    """Scrape a single page"""
    async with semaphore:
        try:
            async with session.get(url, headers=HEADERS, timeout=TIMEOUT) as response:
                if response.status != 200:
                    logger.warning(f"  ⚠ {source_name}: HTTP {response.status}")
                    return []
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                results = []
                
                # Find all links
                for link in soup.find_all('a', href=True):
                    href = link.get('href', '')
                    text = clean_text(link.get_text())
                    
                    # Skip if no text
                    if len(text) < 10:
                        continue
                    
                    # Check if it's a scholarship link
                    if is_scholarship(text) or any(kw in href for kw in ['ทุน', 'scholarship', 'grant']):
                        # Clean URL
                        full_url = normalize_url(href, url)
                        
                        # Skip if already exists or invalid
                        if not full_url or full_url.startswith('#') or 'javascript' in full_url:
                            continue
                        
                        # Extract date if present
                        date = extract_date(text)
                        
                        results.append({
                            'title': text[:200],
                            'url': full_url,
                            'source': source_name,
                            'deadline': date,
                            'found_at': datetime.now().isoformat()
                        })
                
                return results
                
        except asyncio.TimeoutError:
            logger.warning(f"  ⏱ {source_name}: Timeout")
            return []
        except Exception as e:
            logger.warning(f"  ✗ {source_name}: {str(e)[:50]}")
            return []

async def scrape_source(source, semaphore):
    """Scrape a single source (can have multiple pages)"""
    name = source.get('name', 'Unknown')
    url = source.get('url', '')
    
    if not url:
        return []
    
    connector = aiohttp.TCPConnector(limit=10)
    async with aiohttp.ClientSession(connector=connector) as session:
        results = await scrape_page(session, url, name, semaphore)
        return results

async def main():
    """Main async function"""
    logger.info("=" * 60)
    logger.info("🚀 Fast Scholarship Scraper Started")
    logger.info("=" * 60)
    
    # Load configs
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        configs = json.load(f)
    
    sources = configs.get('sources', [])
    logger.info(f"Loaded {len(sources)} sources")
    
    # Load existing scholarships
    existing_file = OUTPUT_FILE
    existing_scholarships = []
    existing_urls = set()
    
    if existing_file.exists():
        with open(existing_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            existing_scholarships = data.get('scholarships', [])
            existing_urls = {s.get('url', '') for s in existing_scholarships if s.get('url')}
    
    logger.info(f"Existing scholarships: {len(existing_scholarships)}")
    
    # Create semaphore for concurrency control
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    
    # Scrape all sources
    all_results = []
    
    # Process in batches
    batch_size = 10
    for i in range(0, len(sources), batch_size):
        batch = sources[i:i+batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(sources) + batch_size - 1) // batch_size
        
        logger.info(f"\n📦 Batch {batch_num}/{total_batches}: Sources {i+1}-{min(i+batch_size, len(sources))}")
        
        tasks = [scrape_source(source, semaphore) for source in batch]
        batch_results = await asyncio.gather(*tasks)
        
        for results in batch_results:
            all_results.extend(results)
        
        logger.info(f"  Found so far: {len(all_results)}")
    
    # Filter out duplicates and existing
    new_scholarships = []
    new_urls = set()
    
    for s in all_results:
        url = s.get('url', '')
        if url and url not in existing_urls and url not in new_urls:
            new_scholarships.append(s)
            new_urls.add(url)
    
    # Merge with existing
    all_scholarships = existing_scholarships + new_scholarships
    
    # Save
    output_data = {
        "version": "1.1",
        "updated_at": datetime.now().isoformat(),
        "total": len(all_scholarships),
        "new_found": len(new_scholarships),
        "scholarships": all_scholarships
    }
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    # Update last_update
    with open(BASE_DIR / "last_update.txt", 'w') as f:
        f.write(datetime.now().isoformat())
    
    logger.info("\n" + "=" * 60)
    logger.info(f"✅ Done! Total: {len(all_scholarships)} scholarships")
    logger.info(f"   New found: {len(new_scholarships)}")
    logger.info(f"   Output: {OUTPUT_FILE}")
    logger.info("=" * 60)
    
    return len(new_scholarships), len(all_scholarships)

# ─── Run ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    new_count, total = asyncio.run(main())
