import os
import time
import json
import requests
import urllib.parse
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
import gspread
from google.oauth2.service_account import Credentials
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# 1. API 및 구글 시트 연동 설정
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
gcp_secret = os.environ.get("GCP_SERVICE_ACCOUNT")
sheet_id = os.environ.get("GOOGLE_SHEET_ID")
mfds_api_key = os.environ.get("MFDS_API_KEY") # 🌟 식약처 OpenAPI 키

if not gcp_secret or not sheet_id or not mfds_api_key:
    print("🚨 환경변수(구글 키, 시트 ID, 또는 식약처 API 키)가 설정되지 않았습니다.")
    exit()

credentials = Credentials.from_service_account_info(json.loads(gcp_secret), scopes=scope)
gc = gspread.authorize(credentials)
worksheet = gc.open_by_key(sheet_id).sheet1

# 2. 날짜 설정 (최근 1주일)
KST = timezone(timedelta(hours=9))
today = datetime.now(KST)
start_date = today - timedelta(days=7)

str_start = start_date.strftime("%Y-%m-%d")
str_end = today.strftime("%Y-%m-%d")

# 3. 셀레니움(크롬 브라우저 원격조종) 설정
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)

def get_api_data(item_seq):
    """식약처 OpenAPI를 호출하여 주성분 등 정확한 정보를 추출합니다."""
    # 의약품 제품 허가 상세정보 API Endpoint
    api_url = "http://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService07/getDrugPrdtPrmsnDtlInq06"
    decoded_key = urllib.parse.unquote(mfds_api_key) # 키 인코딩 오류 방지
    
    params = {
        "serviceKey": decoded_key,
        "item_seq": item_seq,
        "type": "json"
    }
    
    try:
        res = requests.get(api_url, params=params, timeout=10)
        data = res.json()
        if data.get("body") and data["body"].get("items"):
            item = data["body"]["items"][0]
            
            # 허가일 포맷 변경 (예: 20240101 -> 2024-01-01)
            raw_date = item.get("ITEM_PERMIT_DATE", "")
            fmt_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}" if len(raw_date) == 8 else raw_date
                
            return {
                "product_name": item.get("ITEM_NAME", ""),
                "main_ingr": item.get("MAIN_ITEM_INGR", ""), # ✨ 주성분 추출
                "company": item.get("ENTP_NAME", ""),
                "approval_date": fmt_date,
                "category": item.get("ETC_OTC_CODE", "") # ✨ 전문/일반구분 추출
            }
    except Exception as e:
        print(f"⚠️ API 호출 오류 ({item_seq}): {e}")
    return None

def get_detail_page_data(item_seq):
    """상세페이지 버튼을 직접 눌러(접속하여) 위탁제조업체와 허가심사유형을 찾습니다."""
    detail_url = f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
    driver.get(detail_url)
    time.sleep(1.5) # 페이지 로딩 대기
    
    soup = BeautifulSoup(driver.page_source, "html.parser")
    review_type = ""
    contract_mfg = ""
    
    try:
        # 1. 허가심사유형 찾기 (기본정보 테이블)
        th_review = soup.find("th", string=lambda text: text and "허가심사유형" in text)
        if th_review:
            review_type = th_review.find_next_sibling("td").text.strip()
            
        # 2. 위탁제조업체 찾기
        th_mfg = soup.find("th", string=lambda text: text and "위탁제조업체" in text)
        if th_mfg:
            contract_mfg = th_mfg.find_next_sibling("td").text.strip()
    except Exception:
        pass
        
    return contract_mfg, review_type, detail_url

def run_scraper():
    print(f"=== 🚀 식약처 OpenAPI + 셀레니움 하이브리드 수집 시작 ({str_start} ~ {str_end}) ===")
    
    # 1. 셀레니움으로 최근 허가된 '목록(Item_seq)'만 먼저 뚫어냅니다.
    search_url = f"https://nedrug.mfds.go.kr/searchDrug/searchDrugList?page=1&searchYn=true&startDate={str_start}&endDate={str_end}&searchType=ST1&searchKeyword=&pageSize=100"
    
    driver.get(search_url)
    time.sleep(3) # 식약처 방어막 우회를 위한 대기
    
    soup = BeautifulSoup(driver.page_source, "html.parser")
    table = soup.find("table", class_="dr_table")
    
    if not table:
        print("❌ 검색 결과 테이블을 찾을 수 없습니다.")
        driver.quit()
        return
        
    rows = table.find("tbody").find_all("tr")
    if len(rows) == 1 and "데이터가 없습니다" in rows[0].text:
        print(">> 해당 기간에 신규 허가된 의약품이 없습니다.")
        driver.quit()
        return
        
    print(f"🔎 총 {len(rows)}개의 신규 의약품 발견! API 데이터 추출을 시작합니다...")

    # 구글 시트 중복 방지 로직 (기존 품목코드 비교)
    existing_data = worksheet.get_all_records()
    existing_seqs = [str(row.get('품목기준코드', '')) for row in existing_data]

    count = 0
    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 5: continue
            
        try:
            link_tag = cols[1].find("a")
            item_seq = link_tag["href"].split("itemSeq=")[1].split("&")[0]
            
            if item_seq in existing_seqs:
                continue # 이미 시트에 있으면 패스
                
            print(f"⏳ 데이터 융합 중... [{item_seq}]")
            
            # 2. 식약처 OpenAPI 호출 (주성분 등)
            api_data = get_api_data(item_seq)
            
            # API가 순간적으로 응답을 안할 경우, 화면에서 긁어온 데이터로 임시 땜빵하는 안전장치
            if not api_data:
                api_data = {
                    "product_name": link_tag.text.strip(),
                    "main_ingr": "API 확인 필요",
                    "company": cols[2].text.strip(),
                    "approval_date": cols[4].text.strip(),
                    "category": cols[3].text.strip()
                }
                
            # 3. 상세페이지 접속 (위탁제조업체, 허가심사유형)
            contract_mfg, review_type, detail_url = get_detail_page_data(item_seq)
            collected_at = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")

            # 4. 시트에 입력할 새로운 열 순서 세팅
            new_row = [
                item_seq, 
                api_data["product_name"], 
                api_data["main_ingr"], 
                api_data["company"], 
                api_data["approval_date"], 
                api_data["category"], 
                contract_mfg, 
                review_type, 
                detail_url, 
                "", # AI_분류 (비워둠)
                "", # AI_요약 (비워둠)
                collected_at
            ]
            
            worksheet.append_row(new_row)
            existing_seqs.append(item_seq)
            count += 1
            
        except Exception as e:
            print(f"⚠️ 항목 처리 중 에러 발생: {e}")
            continue

    print(f"✅ 수집 완료: 구글 시트에 {count}건의 고급 데이터가 완벽하게 업데이트 되었습니다! 🎉")
    driver.quit()

if __name__ == "__main__":
    run_scraper()
