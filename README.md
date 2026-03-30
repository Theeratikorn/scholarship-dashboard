# Scholarship Dashboard

ระบบค้นหาทุนวิจัย/ทุนการศึกษาในประเทศไทย สาขา **วิศวกรรมเครื่องกล (Mechanical Engineering)** และ **การแพทย์ (Medical)**

## แหล่งทุนที่ดึงข้อมูล
- NRCT - สำนักงานการวิจัยแห่งชาติ
- NIA - สำนักงานนวัตกรรมแห่งชาติ (สวทช.)
- NSTDA - สถาบันนโยบายวิทยาศาสตร์และเทคโนโลยี
- สกอ. - สำนักงานคณะกรรมการการอุดมศึกษา

## ติดตั้ง

```bash
cd /home/pi4eiei/scholarship-dashboard
pip install -r requirements.txt
python app.py
```

เปิดเว็บที่: http://localhost:5000

## Features
- Dashboard แสดงทุนทั้งหมดเป็น Card
- Filter ตามประเภททุน (วิจัย/ศึกษา/อบรม)
- Filter ตามสาขา (วิศวกรรมเครื่องกล/การแพทย์)
- Search box
- ปุ่ม Scrap ข้อมูลใหม่ (manual)
- Auto-scrape ทุก 3 วัน

## API
- `GET /` - Dashboard
- `POST /scrape` - รัน scrape ใหม่
- `GET /api/scholarships` - ข้อมูล JSON
