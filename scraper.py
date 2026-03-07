import os, time, json, requests, urllib.parse, re
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
import gspread
from google.oauth2.service_account import Credentials
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# 1. 설정 및 인증
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
str_start, str_end = start_date.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")

# 3. 셀레니움 설정
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)

def clean_td(td):
    """중복 텍스트 원인인 span 태그(모바일 라벨)를 제거하고 순수 데이터만 추출"""
    temp_soup = BeautifulSoup(str(td), "html.parser")
    for span in temp_soup.find_all("span"):
        span.decompose()
    return temp_soup.get_text(strip=True)

def get_api_data(item_seq):
    """식약처 API를 통해 상세 정보 수집"""
    api_url = "http://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService07/getDrugPrdtPrmsnDtlInq06"
    params = {"serviceKey": urllib.parse.unquote(mfds_api_key), "item_seq": item_seq, "type": "json"}
    try:
        res = requests.get(api_url, params=params, timeout=10).json()
        item = res["body"]["items"][0]
        d = item.get("ITEM_PERMIT_DATE", "")
        return {
            "name": item.get("ITEM_NAME", ""), "ingr": item.get("MAIN_ITEM_INGR", ""), 
            "com": item.get("ENTP_NAME", ""), "date": f"{d[:4]}-{d[4:6]}-{d[6:]}" if len(d)==8 else d,
            "cat": item.get("ETC_OTC_CODE", "") 
        }
    except: return None

def get_detail(item_seq):
    """상세 페이지에서 위탁제조업체 및 허가유형 추출"""
    url = f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
    driver.get(url)
    time.sleep(1.5)
    soup = BeautifulSoup(driver.page_source, "html.parser")
    rv, mfg = "", ""
    try:
        th_rv = soup.find("th", string=lambda t: t and "허가심사유형" in t)
        if th_rv: rv = th_rv.find_next_sibling("td").text.strip()
        th_mfg = soup.find("th", string=lambda t: t and "위탁제조업체" in t)
        if th_mfg: mfg = th_mfg.find_next_sibling("td").text.strip()
    except: pass
    return mfg, rv, url

def run_scraper():
    print(f"=== 🚀 클린 데이터 수집 시작 ({str_start} ~ {str_end}) ===")
    search_url = (f"https://nedrug.mfds.go.kr/pbp/CCBAE01/getItemPermitIntro?page=1&limit=100&searchYn=true&sDateGb=date&"
                  f"sYear={today.year}&sMonth={today.month}&sPermitDateStart={str_start}&sPermitDateEnd={str_end}&btnSearch=")
    driver.get(search_url)
    time.sleep(5)
    
    rows = BeautifulSoup(driver.page_source, "html.parser").find("tbody").find_all("tr")
    existing_seqs = [str(r.get('품목기준코드', '')) for r in worksheet.get_all_records()]

    count = 0
    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 6: continue
        
        # 1. 취하 품목 필터링 (취소/취하일자 칸에 숫자가 있으면 제외)
        if re.search(r'\d', clean_td(cols[4])): continue

        try:
            item_seq = re.search(r"(\d{9})", str(cols[1].find("a"))).group(1)
            if item_seq in existing_seqs: continue
            
            # API 데이터 우선, 실패 시 표에서 추출 (노란 하이라이트 방지 적용)
            api = get_api_data(item_seq) or {
                "name": clean_td(cols[1]), "ingr": "API 확인 필요",
                "com": clean_td(cols[2]), "date": clean_td(cols[3]), "cat": clean_td(cols[5])
            }
            mfg, rv, url = get_detail(item_seq)
            
            # 3. 상세링크 '클릭' 하이퍼링크 적용
            hyperlink = f'=HYPERLINK("{url}", "클릭")'

            new_row = [item_seq, api["name"], api["ingr"], api["com"], api["date"], api["cat"], 
                       mfg, rv, hyperlink, "", "", datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")]
            
            worksheet.append_row(new_row, value_input_option='USER_ENTERED')
            existing_seqs.append(item_seq)
            count += 1
        except: continue

    print(f"✅ 수집 완료: {count}건 업데이트!")
    driver.quit()

if __name__ == "__main__":
    run_scraper()
