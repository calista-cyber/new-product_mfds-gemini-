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

# 2. 날짜 설정 (KST 2026-03-08 기준)
KST = timezone(timedelta(hours=9))
today = datetime.now(KST)
start_date = today - timedelta(days=10) # 7일 대신 10일로 조금 더 넉넉하게 설정

# 3. 셀레니움 설정
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)

def clean_text(td):
    """모바일 라벨(span) 제거 로직"""
    temp_soup = BeautifulSoup(str(td), "html.parser")
    for span in temp_soup.find_all("span"): span.decompose()
    return temp_soup.get_text(strip=True)

def run_scraper():
    print(f"=== 🚀 정밀 필터링 수집 시작 (기준: {start_date.strftime('%Y-%m-%d')} 이후) ===")
    
    # 팀장님의 '완벽한 URL' 구조 그대로 활용
    search_url = (f"https://nedrug.mfds.go.kr/pbp/CCBAE01/getItemPermitIntro?page=1&limit=100&searchYn=true&sDateGb=date&"
                  f"sYear={today.year}&sMonth={today.month}&sPermitDateStart={start_date.strftime('%Y-%m-%d')}&"
                  f"sPermitDateEnd={today.strftime('%Y-%m-%d')}&btnSearch=")
    
    driver.get(search_url)
    time.sleep(8) # 페이지 렌더링을 위해 대기 시간을 8초로 늘림
    
    soup = BeautifulSoup(driver.page_source, "html.parser")
    tbody = soup.find("tbody")
    if not tbody:
        print("❌ 게시판 테이블을 찾을 수 없습니다.")
        driver.quit()
        return

    rows = tbody.find_all("tr")
    print(f"📊 검색된 전체 행 개수: {len(rows)}개")

    existing_seqs = [str(r.get('품목기준코드', '')) for r in worksheet.get_all_records()]
    count = 0

    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 6: continue
        
        product_name = clean_text(cols[1])
        approval_date_str = clean_text(cols[3])
        cancel_date = clean_text(cols[4])

        # 🛡️ 1단계: 취소/취하 여부 정밀 검사
        if cancel_date and re.search(r'\d', cancel_date):
            print(f"   ⏩ 패스: [{product_name}] - 취하된 제품 ({cancel_date})")
            continue

        # 🛡️ 2단계: 신규 허가 날짜 검사 (2021년 등 과거 데이터 원천 차단)
        try:
            app_dt = datetime.strptime(approval_date_str, "%Y-%m-%d").replace(tzinfo=KST)
            if app_dt < start_date:
                print(f"   ⏩ 패스: [{product_name}] - 과거 허가건 ({approval_date_str})")
                continue
        except Exception as e:
            print(f"   ⚠️ 날짜 분석 오류: [{product_name}] {e}")
            continue

        # 🛡️ 3단계: 중복 체크
        try:
            item_seq = re.search(r"(\d{9})", str(cols[1].find("a"))).group(1)
            if item_seq in existing_seqs:
                continue
            
            print(f"   ✅ 수집 확정: [{product_name}]")
            detail_url = f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
            
            new_row = [
                item_seq, product_name, "상세정보 확인 중", clean_text(cols[2]), 
                approval_date_str, clean_text(cols[5]), "", "", 
                f'=HYPERLINK("{detail_url}", "클릭")', "", "", today.strftime("%Y-%m-%d %H:%M:%S")
            ]
            worksheet.append_row(new_row, value_input_option='USER_ENTERED')
            existing_seqs.append(item_seq)
            count += 1
        except Exception as e:
            print(f"   ⚠️ 항목 처리 중 예외 발생: {e}")
            continue

    print(f"🏁 수집 종료: 신규 허가 {count}건 업데이트 완료!")
    driver.quit()

if __name__ == "__main__":
    run_scraper()
