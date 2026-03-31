"""
Scholarship Dashboard - Flask App
ค้นหาทุนวิจัย/ทุนการศึกษา วิศวกรรมเครื่องกล + การแพทย์
"""

import os
import sys
import json
import logging
from datetime import datetime
from flask import Flask, render_template, request, jsonify, abort
from apscheduler.schedulers.background import BackgroundScheduler

# ============ Setup ============
app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, 'scholarships.json')
LAST_UPDATE_FILE = os.path.join(BASE_DIR, 'last_update.txt')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============ Load New Scraper ============
import auto_scraper

def load_manual_scholarships():
    """โหลดทุนจากไฟล์ manual_scholarships.json"""
    manual_file = os.path.join(BASE_DIR, 'manual_scholarships.json')
    if os.path.exists(manual_file):
        with open(manual_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def run_scrape():
    """เรียก auto_scraper.main() เพื่อ scrape ข้อมูลทุกแหล่ง"""
    logger.info('เริ่ม scrape ข้อมูลทุนจากทุกแหล่ง...')
    
    # เรียก main() จาก auto_scraper
    try:
        auto_scraper.main()
    except Exception as e:
        logger.error(f'Auto scraper error: {e}')
    
    # โหลดผลลัพธ์หลัง scrape เสร็จ
    scraped = []
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            # Handle nested format
            if isinstance(raw, dict) and 'scholarships' in raw:
                scraped = raw['scholarships']
            elif isinstance(raw, dict) and 'data' in raw:
                scraped = raw['data']
            elif isinstance(raw, list):
                scraped = raw
        except:
            scraped = []
    
    # รวมกับ manual scholarships
    manual = load_manual_scholarships()
    all_data = scraped + manual
    
    # ลบซ้ำ
    seen = set()
    unique = []
    for item in all_data:
        key = item.get('title', item.get('id', ''))[:50]
        if key not in seen:
            seen.add(key)
            unique.append(item)
    
    # บันทึกรวมใน format เดิม
    output = {
        'version': '1.0',
        'updated_at': datetime.now().isoformat(),
        'total': len(unique),
        'scholarships': unique
    }
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    with open(LAST_UPDATE_FILE, 'w') as f:
        f.write(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    
    logger.info(f'เก็บข้อมูลได้ {len(unique)} รายการ (scrape: {len(scraped)}, manual: {len(manual)})')
    return unique

# ============ Helper Functions ============
def load_scholarships():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # Handle nested format
        if isinstance(data, dict) and 'scholarships' in data:
            return data['scholarships']
        elif isinstance(data, dict) and 'data' in data:
            return data['data']
        elif isinstance(data, list):
            return data
        elif isinstance(data, dict):
            # Return dict values if it's a dict of scholarships
            return list(data.values()) if data else []
    return []

def get_last_update():
    if os.path.exists(LAST_UPDATE_FILE):
        with open(LAST_UPDATE_FILE, 'r') as f:
            return f.read().strip()
    return 'ยังไม่มีข้อมูล'

# ============ Routes ============
@app.route('/health')
def health():
    """Health check endpoint"""
    return 'OK', 200

@app.route('/')
def index():
    scholarships = load_scholarships()
    count = len(scholarships)
    last_update = get_last_update()
    return render_template('index.html', 
                         scholarships=scholarships, 
                         count=count,
                         last_update=last_update)

@app.route('/scrape', methods=['POST'])
def scrape():
    try:
        logger.info('Scrape requested via API')
        
        # Run scrape in background and return immediately
        import threading
        
        def do_scrape():
            try:
                run_scrape()
            except Exception as e:
                logger.error(f'Background scrape error: {e}')
        
        thread = threading.Thread(target=do_scrape)
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True, 
            'count': 'กำลัง scrape...', 
            'updated': 'กรุณารอสักครู่ แล้วกดรีเฟรชหน้า'
        })
    except Exception as e:
        logger.error(f'Scrape error: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/scholarships')
def api_scholarships():
    return jsonify(load_scholarships())

@app.route('/scholarship/<scholarship_id>')
def scholarship_detail(scholarship_id):
    scholarships = load_scholarships()
    for s in scholarships:
        if s.get('id') == scholarship_id:
            return render_template('detail.html', s=s)
    abort(404)

# ============ Scheduler ============
scheduler = BackgroundScheduler()

# ============ Start ============
if __name__ == '__main__':
    # รัน scrape ครั้งแรกถ้ายังไม่มีข้อมูล (เฉพาะ LOCAL)
    if os.environ.get('RAILWAY_ENVIRONMENT') is None:
        if not os.path.exists(DATA_FILE) or os.path.getsize(DATA_FILE) < 100:
            logger.info('เริ่ม scrape ครั้งแรก...')
            run_scrape()
        scheduler.add_job(run_scrape, 'interval', days=3, id='scheduled_scrape')
        scheduler.start()
    
    app.run(host='0.0.0.0', port=5010, debug=False)
