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
import re

# 1. API 및 구글 시트 연동 설정
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
gcp_secret = os.environ.get("GCP_SERVICE_ACCOUNT")
sheet_id = os.environ.get("GOOGLE_SHEET_ID")
mfds_api_key = os.environ.get("MFDS_API_KEY") 

if not gcp_secret or not sheet_id or not mfds_api_key:
    print("🚨 환경변수(구글 키, 시트 ID, 또는 식약처 API 키)가 설정되지 않았습니다.")
    exit()

# 구글 시트 인증
credentials = Credentials.from_service_account_info(json.loads(gcp_secret), scopes=scope)
gc = gspread.authorize(credentials)
worksheet = gc.open_by_key(sheet_id).sheet1

# 2. 날짜 설정 (최근 1주일)
KST = timezone(timedelta(hours=9))
today = datetime.now(KST)
start_date = today - timedelta(days=7) 

str_start = start_date.strftime("%Y-%m-%d")
str_end = today.strftime("%Y-%m-%d")
s_year = today.strftime("%Y")
s_month = str(today.month)

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
    api_url = "http://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService07/getDrugPrdtPrmsnDtlInq06"
    decoded_key = urllib.parse.unquote(mfds_api_key) 
    
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
            raw_date = item.get("ITEM_PERMIT_DATE", "")
            fmt_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}" if len(raw_date) == 8 else raw_date
                
            return {
                "product_name": item.get("ITEM_NAME", ""),
                "main_ingr": item.get("MAIN_ITEM_INGR", ""), 
                "company": item.get("ENTP_NAME", ""),
                "approval_date": fmt_date,
                "category": item.get("ETC_OTC_CODE", "") 
            }
    except Exception as e:
        print(f"⚠️ API 호출 오류 ({item_seq}): {e}")
    return None

def get_detail_page_data(item_seq):
    """상세페이지 버튼을 직접 눌러 위탁제조업체와 허가심사유형을 찾습니다."""
    detail_url = f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
    driver.get(detail_url)
    time.sleep(1.5) 
    
    soup = BeautifulSoup(driver.page_source, "html.parser")
    review_type = ""
    contract_mfg = ""
    
    try:
        th_review = soup.find("th", string=lambda text: text and "허가심사유형" in text)
        if th_review:
            review_type = th_review.find_next_sibling("td").text.strip()
            
        th_mfg = soup.find("th", string=lambda text: text and "위탁제조업체" in text)
        if th_mfg:
            contract_mfg = th_mfg.find_next_sibling("td").text.strip()
    except Exception:
        pass
        
    return contract_mfg, review_type, detail_url

def run_scraper():
    print(f"=== 🚀 다이렉트 URL 타겟팅 수집 시작 ({str_start} ~ {str_end}) ===")
    
    # 🌟 팀장님이 설계하신 완벽한 URL에 날짜만 동적으로 주입 (100개씩 보기 적용)
    search_url = (
        f"https://nedrug.mfds.go.kr/pbp/CCBAE01/getItemPermitIntro?"
        f"page=1&limit=100&sort=&sortOrder=true&searchYn=true&garaInputBox=&sDateGb=date&"
        f"sYear={s_year}&sMonth={s_month}&sWeek=1&"
        f"sPermitDateStart={str_start}&sPermitDateEnd={str_end}&sItemName=&sEntpName=&btnSearch="
    )
    
    driver.get(search_url)
    time.sleep(5) # 다이렉트 접속 후 표가 렌더링될 때까지 넉넉히 대기
    
    soup = BeautifulSoup(driver.page_source, "html.parser")
    table = soup.find("table") 
    
    if not table:
        print("❌ 검색 결과 테이블을 찾을 수 없습니다. (식약처 서버 응답 지연)")
        driver.quit()
        return
        
    rows = table.find("tbody").find_all("tr")
    if len(rows) == 1 and ("데이터가 없습니다" in rows[0].text or "조회된 내용이 없습니다" in rows[0].text):
        print(">> 해당 기간에 신규 허가된 의약품이 없습니다.")
        driver.quit()
        return
        
    print(f"🔎 총 {len(rows)}개의 신규 의약품 발견! 데이터 추출을 시작합니다...")

    existing_data = worksheet.get_all_records()
    existing_seqs = [str(row.get('품목기준코드', '')) for row in existing_data]

    count = 0
    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 5: continue
            
        try:
            link_tag = cols[1].find("a")
            if not link_tag: continue
            
            # 정규식을 이용해 어떤 형태의 링크/스크립트든 9자리 품목코드만 정확히 낚아채기
            match = re.search(r"(\d{9})", str(link_tag))
            if match:
                item_seq = match.group(1)
            else:
                continue
            
            if item_seq in existing_seqs:
                continue 
                
            print(f"⏳ 데이터 융합 중... [{item_seq}]")
            
            api_data = get_api_data(item_seq)
            
            if not api_data:
                # API 실패 시 표에서 직접 긁어오는 백업 플랜 (변경된 표 양식에 맞춤)
                api_data = {
                    "product_name": link_tag.text.strip(),
                    "main_ingr": "API 확인 필요",
                    "company": cols[2].text.strip(),
                    "approval_date": cols[3].text.strip(),
                    "category": cols[5].text.strip() if len(cols) > 5 else ""
                }
                
            contract_mfg, review_type, detail_url = get_detail_page_data(item_seq)
            collected_at = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")

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

    print(f"✅ 수집 완료: 구글 시트에 {count}건이 완벽하게 업데이트 되었습니다! 🎉")
    driver.quit()

if __name__ == "__main__":
    run_scraper()
