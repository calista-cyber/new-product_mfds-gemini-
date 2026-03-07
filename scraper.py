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
