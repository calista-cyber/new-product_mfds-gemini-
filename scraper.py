import os, time, json, requests, urllib.parse, re
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
import gspread
from google.oauth2.service_account import Credentials
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# 1. 설정
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
gcp_secret = os.environ.get("GCP_SERVICE_ACCOUNT")
sheet_id = os.environ.get("GOOGLE_SHEET_ID")
mfds_api_key = os.environ.get("MFDS_API_KEY") 

credentials = Credentials.from_service_account_info(json.loads(gcp_secret), scopes=scope)
gc = gspread.authorize(credentials)
worksheet = gc.open_by_key(sheet_id).sheet1

# 2. 날짜 설정 (최근 7일)
KST = timezone(timedelta(hours=9))
today = datetime.now(KST)
start_date = today - timedelta(days=7) 

# 3. 셀레니움 설정
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)

def smart_clean(td):
    """라벨(span)만 제거하고 실제 데이터는 보존하는 지능형 정제"""
    soup = BeautifulSoup(str(td), "html.parser")
    # '업체명', '허가일자' 등 라벨 텍스트가 포함된 span만 골라서 삭제
    labels = ["업체명", "허가일자", "전문/일반", "취소/취하일자", "구분"]
    for span in soup.find_all("span"):
        if any(label in span.get_text() for label in labels):
            span.decompose()
    return soup.get_text(strip=True)

def run_scraper():
    print(f"=== 🚀 데이터 수집 시작 ({start_date.strftime('%Y-%m-%d')} ~) ===")
    search_url = (f"https://nedrug.mfds.go.kr/pbp/CCBAE01/getItemPermitIntro?page=1&limit=100&searchYn=true&sDateGb=date&"
                  f"sYear={today.year}&sMonth={today.month}&sPermitDateStart={start_date.strftime('%Y-%m-%d')}&"
                  f"sPermitDateEnd={today.strftime('%Y-%m-%d')}&btnSearch=")
    
    driver.get(search_url)
    time.sleep(7)
    rows = BeautifulSoup(driver.page_source, "html.parser").find("tbody").find_all("tr")
    
    existing_seqs = [str(r.get('품목기준코드', '')) for r in worksheet.get_all_records()]
    count = 0

    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 6: continue
        
        name = smart_clean(cols[1])
        app_date_str = smart_clean(cols[3])
        cancel_date = smart_clean(cols[4])

        # 🛡️ 검문 1: 취하 제품 패스
        if cancel_date and re.search(r'\d', cancel_date): continue

        # 🛡️ 검문 2: 날짜 필터링 (최근 7일 이내만)
        try:
            app_dt = datetime.strptime(app_date_str, "%Y-%m-%d").replace(tzinfo=KST)
            if app_dt < start_date: continue
        except: continue

        try:
            item_seq = re.search(r"(\d{9})", str(cols[1].find("a"))).group(1)
            if item_seq in existing_seqs: continue
            
            detail_url = f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
            new_row = [item_seq, name, "상세정보 확인 중", smart_clean(cols[2]), app_date_str, smart_clean(cols[5]), 
                       "", "", f'=HYPERLINK("{detail_url}", "클릭")', "", "", today.strftime("%Y-%m-%d %H:%M:%S")]
            
            worksheet.append_row(new_row, value_input_option='USER_ENTERED')
            existing_seqs.append(item_seq)
            count += 1
            print(f"   ✅ 수집됨: {name}")
        except: continue

    print(f"🏁 신규 {count}건 업데이트 완료!")
    driver.quit()

if __name__ == "__main__":
    run_scraper()
