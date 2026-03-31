"""
Scholarship Dashboard - Flask App
ค้นหาทุนวิจัย/ทุนการศึกษา วิศวกรรมเครื่องกล + การแพทย์
"""

import os
import json
import logging
import hashlib
from datetime import datetime
from flask import Flask, render_template, request, jsonify, abort
import requests
from bs4 import BeautifulSoup
from apscheduler.schedulers.background import BackgroundScheduler

# ============ Setup ============
app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, 'scholarships.json')
LAST_UPDATE_FILE = os.path.join(BASE_DIR, 'last_update.txt')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============ Scraper ============
TARGET_KEYWORDS = [
    'mechanical', 'engineering', 'medical', 'medicine', 'health',
    'biomedical', 'biomechanics', 'manufacturing', 'automotive',
    'วิศวกรรม', 'การแพทย์', 'แพทย์', 'วิทยาศาสตร์การแพทย์',
    'ชีวการแพทย์', 'วิศวกรรมเครื่องกล', 'วิศวกรรมการแพทย์'
]

def load_scholarships():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_scholarships(data):
    ensure_ids(data)
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    with open(LAST_UPDATE_FILE, 'w') as f:
        f.write(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

def get_last_update():
    if os.path.exists(LAST_UPDATE_FILE):
        with open(LAST_UPDATE_FILE, 'r') as f:
            return f.read().strip()
    return 'ยังไม่มีการอัพเดท'

def matches_keywords(text):
    if not text:
        return False
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in TARGET_KEYWORDS)

def generate_id(title):
    """สร้าง ID จากชื่อทุน"""
    return hashlib.md5(title.encode('utf-8')).hexdigest()[:8]

def ensure_ids(data):
    """เพิ่ม id ให้ทุนที่ยังไม่มี"""
    for item in data:
        if 'id' not in item:
            item['id'] = generate_id(item['title'])
    return data

def scrape_nrct():
    """สำนักงานการวิจัยแห่งชาติ (NRCT)"""
    results = []
    try:
        # ลองดึงข้อมูลจากหน้าข่าวหลักของ NRCT
        urls_to_try = [
            'https://www.nrct.go.th/News',
            'https://www.nrct.go.th/th/news',
            'https://www.nrct.go.th/',
        ]
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'th-TH,th;q=0.9,en;q=0.8',
        }
        for url in urls_to_try:
            try:
                resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, 'lxml')
                    # ค้นหาลิงก์ที่เกี่ยวข้องกับทุนวิจัย
                    for item in soup.find_all('a', href=True):
                        title = item.get_text(strip=True)
                        href = item.get('href', '')
                        if len(title) > 15 and matches_keywords(title):
                            if not href.startswith('http'):
                                href = 'https://www.nrct.go.th' + href
                            results.append({
                                'title': title[:200],
                                'provider': 'สำนักงานการวิจัยแห่งชาติ (NRCT)',
                                'deadline': 'ตรวจสอบจากลิงก์',
                                'eligibility': 'นักวิจัยไทย',
                                'amount': 'ตามประกาศ',
                                'link': href,
                                'category': 'research',
                                'field': 'ทั่วไป'
                            })
                    if results:
                        break  # ถ้าเจอข้อมูลแล้วหยุด
            except Exception:
                continue
    except Exception as e:
        logger.warning(f'NRCT scrape error: {e}')
    return results[:20]

def scrape_nia():
    """สำนักงานนวัตกรรมแห่งชาติ (NIA)"""
    results = []
    try:
        # ดึงข้อมูลจากหน้าหลักและหน้าค้นหาของ NIA
        urls_to_try = [
            'https://www.nia.or.th/',
            'https://www.nia.or.th/advance_search/NIA',
        ]
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'th-TH,th;q=0.9,en;q=0.8',
        }
        for url in urls_to_try:
            try:
                resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, 'lxml')
                    for item in soup.find_all('a', href=True):
                        title = item.get_text(strip=True)
                        href = item.get('href', '')
                        if len(title) > 15 and matches_keywords(title):
                            if not href.startswith('http'):
                                href = 'https://www.nia.or.th' + href
                            results.append({
                                'title': title[:200],
                                'provider': 'สำนักงานนวัตกรรมแห่งชาติ (NIA)',
                                'deadline': 'ตรวจสอบจากลิงก์',
                                'eligibility': 'ผู้ประกอบการ/นักวิจัย',
                                'amount': 'ตามประกาศ',
                                'link': href,
                                'category': 'research',
                                'field': 'นวัตกรรม'
                            })
                    if results:
                        break
            except Exception:
                continue
    except Exception as e:
        logger.warning(f'NIA scrape error: {e}')
    return results[:15]

def scrape_nstd():
    """สถาบันนโยบายวิทยาศาสตร์และเทคโนโลยีแห่งชาติ (NSTDA/สวทช.)"""
    results = []
    try:
        urls_to_try = [
            'https://www.nstda.or.th/',
            'https://www.nstda.or.th/en/',
        ]
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'th-TH,th;q=0.9,en;q=0.8',
        }
        for url in urls_to_try:
            try:
                resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, 'lxml')
                    for item in soup.find_all('a', href=True):
                        title = item.get_text(strip=True)
                        href = item.get('href', '')
                        if len(title) > 15 and matches_keywords(title):
                            if not href.startswith('http'):
                                href = 'https://www.nstda.or.th' + href
                            results.append({
                                'title': title[:200],
                                'provider': 'สถาบันนโยบายวิทยาศาสตร์และเทคโนโลยีแห่งชาติ (NSTDA)',
                                'deadline': 'ตรวจสอบจากลิงก์',
                                'eligibility': 'นักวิจัย/ภาคเอกชน',
                                'amount': 'ตามประกาศ',
                                'link': href,
                                'category': 'research',
                                'field': 'วิทยาศาสตร์/เทคโนโลยี'
                            })
                    if results:
                        break
            except Exception:
                continue
    except Exception as e:
        logger.warning(f'NSTDA scrape error: {e}')
    return results[:15]

def scrape_scholar():
    """รวบรวมข้อมูลทุนตัวอย่าง (MVP - ยังไม่มีเว็บจริง)"""
    return [
        {
            'title': 'ทุนวิจัยเพื่อนวัตกรรมด้านวิศวกรรมเครื่องกล',
            'provider': 'สำนักงานการวิจัยแห่งชาติ (NRCT)',
            'deadline': '2026-06-30',
            'eligibility': 'นักวิจัยไทย สาขาวิศวกรรมเครื่องกล',
            'amount': 'ไม่เกิน 1,000,000 บาท',
            'link': 'https://www.nrct.go.th',
            'category': 'research',
            'field': 'วิศวกรรมเครื่องกล'
        },
        {
            'title': 'ทุนสนับสนุนงานวิจัยด้านเทคโนโลยีชีวภาพทางการแพทย์',
            'provider': 'สำนักงานนวัตกรรมแห่งชาติ (NIA)',
            'deadline': '2026-05-15',
            'eligibility': 'นักวิจัย/สถาบันวิจัย สาขาการแพทย์',
            'amount': 'ไม่เกิน 500,000 บาท',
            'link': 'https://www.nia.or.th',
            'category': 'research',
            'field': 'การแพทย์'
        },
        {
            'title': 'ทุนพัฒนาอุปกรณ์การแพทย์ขั้นสูง',
            'provider': 'สถาบันนโยบายวิทยาศาสตร์และเทคโนโลยี (NSTDA)',
            'deadline': '2026-04-30',
            'eligibility': 'บุคลากรทางการแพทย์/วิศวกรรม',
            'amount': 'ไม่เกิน 2,000,000 บาท',
            'link': 'https://www.nstda.or.th',
            'category': 'research',
            'field': 'การแพทย์ + วิศวกรรม'
        },
        {
            'title': 'ทุนสกอ. ระดับบัณฑิตศึกษา สาขาวิศวกรรม',
            'provider': 'สำนักงานคณะกรรมการการอุดมศึกษา (สกอ.)',
            'deadline': '2026-03-31',
            'eligibility': 'นักศึกษาปริญญาโท-เอก สาขาวิศวกรรม',
            'amount': '15,000 - 25,000 บาท/เดือน',
            'link': 'https://www.mhesi.go.th',
            'category': 'education',
            'field': 'วิศวกรรม'
        },
        {
            'title': 'ทุนวิจัยขั้นแม่นยำด้านวิศวกรรมชีวกำลัง (Biomechanics)',
            'provider': 'NRCT',
            'deadline': '2026-07-15',
            'eligibility': 'นักวิจัยไทย สาขาชีวกลศาสตร์',
            'amount': 'ไม่เกิน 1,500,000 บาท',
            'link': 'https://www.nrct.go.th',
            'category': 'research',
            'field': 'วิศวกรรมเครื่องกล + การแพทย์'
        },
        {
            'title': 'ทุนรางวัลนักวิจัยรุ่นใหม่ สาขาแพทยศาสตร์',
            'provider': 'สำนักงานการวิจัยแห่งชาติ',
            'deadline': '2026-08-01',
            'eligibility': 'นักวิจัยอายุไม่เกิน 40 ปี',
            'amount': '500,000 บาท',
            'link': 'https://www.nrct.go.th',
            'category': 'research',
            'field': 'การแพทย์'
        },
        {
            'title': 'ทุนสนับสนุนเทคโนโลยีการผลิตชั้นสูง (Smart Manufacturing)',
            'provider': 'สำนักงานนวัตกรรมแห่งชาติ',
            'deadline': '2026-05-30',
            'eligibility': 'อาจารย์/นักวิจัย/ภาคอุตสาหกรรม',
            'amount': 'ไม่เกิน 3,000,000 บาท',
            'link': 'https://www.nia.or.th',
            'category': 'research',
            'field': 'วิศวกรรมเครื่องกล'
        },
        {
            'title': 'ทุนโครงการ i4.0 ด้านวิศวกรรมยานยนต์',
            'provider': 'สถาบันนโยบายวิทยาศาสตร์',
            'deadline': '2026-06-15',
            'eligibility': 'มหาวิทยาลัย/สถาบันวิจัย',
            'amount': 'ไม่เกิน 5,000,000 บาท',
            'link': 'https://www.nstda.or.th',
            'category': 'research',
            'field': 'วิศวกรรมเครื่องกล'
        },
        {
            'title': 'ทุนพัฒนาหุ่นยนต์ทางการแพทย์ (Medical Robotics)',
            'provider': 'NIA + NRCT',
            'deadline': '2026-09-30',
            'eligibility': 'ทีมวิจัยข้ามสาขา (แพทย์+วิศวกร)',
            'amount': 'ไม่เกิน 2,500,000 บาท',
            'link': 'https://www.nia.or.th',
            'category': 'research',
            'field': 'วิศวกรรมเครื่องกล + การแพทย์'
        },
        {
            'title': 'ทุนอบรมเชิงปฏิบัติการด้านวิศวกรรมชีวภาพ',
            'provider': 'กระทรวงวิทยาศาสตร์',
            'deadline': '2026-04-15',
            'eligibility': 'อาจารย์/นักศึกษาระดับบัณฑิตศึกษา',
            'amount': 'ครอบคลุมค่าใช้จ่าย',
            'link': 'https://www.nstda.or.th',
            'category': 'training',
            'field': 'การแพทย์ + วิศวกรรม'
        },
    ]

def run_scrape():
    """รวมข้อมูลจากทุกแหล่ง"""
    logger.info('เริ่ม scrape ข้อมูลทุน...')
    all_data = []
    
    # เพิ่มข้อมูลตัวอย่าง
    all_data.extend(scrape_scholar())
    
    # ลอง scrape จริง
    all_data.extend(scrape_nrct())
    all_data.extend(scrape_nia())
    all_data.extend(scrape_nstd())
    
    # ลบรายการซ้ำ
    seen = set()
    unique = []
    for item in all_data:
        key = item['title'][:100]
        if key not in seen:
            seen.add(key)
            unique.append(item)
    
    save_scholarships(unique)
    logger.info(f'เก็บข้อมูลได้ {len(unique)} รายการ')
    return unique

# ============ Scheduler ============
scheduler = BackgroundScheduler()
# ถ้าเป็น Railway ให้ใช้ cron job แทน APScheduler
if os.environ.get('RAILWAY_ENVIRONMENT') is None:
    scheduler.add_job(run_scrape, 'interval', days=3, id='scheduled_scrape')

# ============ Routes ============
@app.route('/health')
def health():
    """Health check endpoint - Railway needs this"""
    import logging
    logging.warning('HEALTH CHECK HIT')
    return 'OK', 200

@app.route('/')
def index():
    scholarships = load_scholarships()
    last_update = get_last_update()
    
    # Filter
    category = request.args.get('category', '')
    field = request.args.get('field', '')
    search = request.args.get('search', '').strip().lower()
    
    filtered = scholarships
    if category:
        filtered = [s for s in filtered if s.get('category') == category]
    if field:
        filtered = [s for s in filtered if field.lower() in s.get('field', '').lower()]
    if search:
        filtered = [s for s in filtered 
                    if search in s.get('title', '').lower() 
                    or search in s.get('provider', '').lower()
                    or search in s.get('field', '').lower()]
    
    return render_template('index.html', 
                         scholarships=filtered,
                         total=len(scholarships),
                         filtered=len(filtered),
                         last_update=last_update,
                         categories=['research', 'education', 'training'],
                         fields=['วิศวกรรมเครื่องกล', 'การแพทย์', 'วิศวกรรมเครื่องกล + การแพทย์']
                        )

@app.route('/scrape', methods=['POST'])
def scrape():
    try:
        data = run_scrape()
        return jsonify({'success': True, 'count': len(data), 'updated': get_last_update()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/scholarships')
def api_scholarships():
    return jsonify(ensure_ids(load_scholarships()))

@app.route('/scholarship/<scholarship_id>')
def scholarship_detail(scholarship_id):
    scholarships = ensure_ids(load_scholarships())
    for s in scholarships:
        if s.get('id') == scholarship_id:
            return render_template('detail.html', s=s)
    abort(404)

# ============ Start ============
if __name__ == '__main__':
    # รัน scrape ครั้งแรกถ้ายังไม่มีข้อมูล (เฉพาะ LOCAL ไม่ใช่ Railway)
    if os.environ.get('RAILWAY_ENVIRONMENT') is None:
        if not os.path.exists(DATA_FILE):
            logger.info('เริ่ม scrape ครั้งแรก...')
            run_scrape()
        scheduler.start()
    
    app.run(host='0.0.0.0', port=5010, debug=False)
