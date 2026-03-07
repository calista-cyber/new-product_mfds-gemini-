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

credentials = Credentials.from_service_account_info(json.loads(gcp_secret), scopes=scope)
gc = gspread.authorize(credentials)
worksheet = gc.open_by_key(sheet_id).sheet1

# 2. 날짜 설정
KST = timezone(timedelta(hours=9))
today = datetime.now(KST)
start_date = today - timedelta(days=7) 
str_start = start_date.strftime("%Y-%m-%d")
str_end = today.strftime("%Y-%m-%d")

# 3. 셀레니움 설정
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)

def get_api_data(item_seq):
    api_url = "http://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService07/getDrugPrdtPrmsnDtlInq06"
    decoded_key = urllib.parse.unquote(mfds_api_key) 
    params = {"serviceKey": decoded_key, "item_seq": item_seq, "type": "json"}
    try:
        res = requests.get(api_url, params=params, timeout=10)
        data = res.json()
        if data.get("body") and data["body"].get("items"):
            item = data["body"]["items"][0]
            raw_date = item.get("ITEM_PERMIT_DATE", "")
            return {
                "product_name": item.get("ITEM_NAME", ""),
                "main_ingr": item.get("MAIN_ITEM_INGR", ""), 
                "company": item.get("ENTP_NAME", ""),
                "approval_date": f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}" if len(raw_date)==8 else raw_date,
                "category": item.get("ETC_OTC_CODE", "") 
            }
    except: pass
    return None

def get_detail_page_data(item_seq):
    detail_url = f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
    driver.get(detail_url)
    time.sleep(1.5) 
    soup = BeautifulSoup(driver.page_source, "html.parser")
    review_type, contract_mfg = "", ""
    try:
        th_review = soup.find("th", string=lambda text: text and "허가심사유형" in text)
        if th_review: review_type = th_review.find_next_sibling("td").text.strip()
        th_mfg = soup.find("th", string=lambda text: text and "위탁제조업체" in text)
        if th_mfg: contract_mfg = th_mfg.find_next_sibling("td").text.strip()
    except: pass
    return contract_mfg, review_type, detail_url

def run_scraper():
    print(f"=== 🚀 수집 시작 ({str_start} ~ {str_end}) ===")
    search_url = (
        f"https://nedrug.mfds.go.kr/pbp/CCBAE01/getItemPermitIntro?"
        f"page=1&limit=100&searchYn=true&sDateGb=date&sYear={today.year}&sMonth={today.month}&"
        f"sPermitDateStart={str_start}&sPermitDateEnd={str_end}&btnSearch="
    )
    driver.get(search_url)
    time.sleep(5) 
    soup = BeautifulSoup(driver.page_source, "html.parser")
    table = soup.find("table") 
    if not table: return
        
    rows = table.find("tbody").find_all("tr")
    existing_data = worksheet.get_all_records()
    existing_seqs = [str(row.get('품목기준코드', '')) for row in existing_data]

    count = 0
    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 6: continue
            
        # ✨ [수정 1] 숫자가 포함된 진짜 날짜가 있을 때만 '취하'로 간주!
        cancel_text = cols[4].text.strip()
        if any(char.isdigit() for char in cancel_text):
            print(f"⏩ 취하 품목 패스: {cancel_text}")
            continue

        try:
            link_tag = cols[1].find("a")
            item_seq = re.search(r"(\d{9})", str(link_tag)).group(1)
            if item_seq in existing_seqs: continue
                
            api_data = get_api_data(item_seq) or {
                "product_name": link_tag.text.strip(), "main_ingr": "API 확인 필요",
                "company": cols[2].text.strip(), "approval_date": cols[3].text.strip(),
                "category": cols[5].text.strip()
            }
                
            mfg, review, url = get_detail_page_data(item_seq)
            
            # ✨ [수정 3] 상세링크를 '클릭' 하이퍼링크로 변환
            hyperlink = f'=HYPERLINK("{url}", "클릭")'

            new_row = [
                item_seq, api_data["product_name"], api_data["main_ingr"], 
                api_data["company"], api_data["approval_date"], api_data["category"], 
                mfg, review, hyperlink, "", "", datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
            ]
            
            worksheet.append_row(new_row, value_input_option='USER_ENTERED')
            existing_seqs.append(item_seq)
            count += 1
        except: continue

    print(f"✅ 수집 완료: {count}건 업데이트! 🎉")
    driver.quit()

if __name__ == "__main__":
    run_scraper()
