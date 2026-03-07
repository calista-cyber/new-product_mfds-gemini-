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

# 2. 날짜 설정 (최근 1주일)
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

def clean_text(td):
    """모바일 라벨 등 모든 불필요한 태그를 제거하고 순수 데이터만 추출"""
    temp_soup = BeautifulSoup(str(td), "html.parser")
    for tag in temp_soup.find_all(['span', 'strong', 'label']):
        tag.decompose()
    return temp_soup.get_text(strip=True)

def run_scraper():
    print(f"=== 🚀 최종 필터링 수집 시작 ===")
    search_url = (f"https://nedrug.mfds.go.kr/pbp/CCBAE01/getItemPermitIntro?page=1&limit=100&searchYn=true&sDateGb=date&"
                  f"sYear={today.year}&sMonth={today.month}&sPermitDateStart={start_date.strftime('%Y-%m-%d')}&"
                  f"sPermitDateEnd={today.strftime('%Y-%m-%d')}&btnSearch=")
    
    driver.get(search_url)
    time.sleep(5)
    rows = BeautifulSoup(driver.page_source, "html.parser").find("tbody").find_all("tr")
    
    existing_data = worksheet.get_all_records()
    existing_seqs = [str(r.get('품목기준코드', '')) for r in existing_data]

    count = 0
    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 6: continue
        
        # 🛡️ 1단계: 취소/취하일자 검사 (숫자가 하나라도 보이면 취하된 제품)
        cancel_val = clean_text(cols[4])
        if cancel_val and re.search(r'\d', cancel_val):
            print(f"⏩ 취하 제품 제외: {clean_text(cols[1])}")
            continue

        # 🛡️ 2단계: 허가일자 검사 (2021년 등 과거 데이터 원천 차단)
        approval_date_str = clean_text(cols[3])
        try:
            app_dt = datetime.strptime(approval_date_str, "%Y-%m-%d").replace(tzinfo=KST)
            if app_dt < start_date:
                print(f"⏩ 과거 허가 데이터 패스: {approval_date_str}")
                continue
        except: continue

        try:
            item_seq = re.search(r"(\d{9})", str(cols[1].find("a"))).group(1)
            if item_seq in existing_seqs: continue
            
            detail_url = f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
            
            # 수집 데이터 정리
            new_row = [
                item_seq, clean_text(cols[1]), "상세정보 로딩 대기", clean_text(cols[2]), 
                approval_date_str, clean_text(cols[5]), "", "", 
                f'=HYPERLINK("{detail_url}", "클릭")', "", "", today.strftime("%Y-%m-%d %H:%M:%S")
            ]
            
            worksheet.append_row(new_row, value_input_option='USER_ENTERED')
            existing_seqs.append(item_seq)
            count += 1
        except: continue

    print(f"✅ 필터링 완료: 신규 허가 {count}건 업데이트!")
    driver.quit()

if __name__ == "__main__":
    run_scraper()
