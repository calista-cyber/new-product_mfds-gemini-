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

def clean_data(td):
    """중복 텍스트 방지: span 태그를 제거하고 순수 데이터만 추출"""
    soup = BeautifulSoup(str(td), "html.parser")
    for span in soup.find_all("span"): span.decompose()
    return soup.get_text(strip=True)

def get_api_data(item_seq):
    """API를 통해 주성분과 허가일자 확보"""
    api_url = "http://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService07/getDrugPrdtPrmsnDtlInq06"
    params = {"serviceKey": urllib.parse.unquote(mfds_api_key), "item_seq": item_seq, "type": "json"}
    try:
        res = requests.get(api_url, params=params, timeout=10).json()
        item = res["body"]["items"][0]
        return {"ingr": item.get("MAIN_ITEM_INGR", "")}
    except: return None

def get_detail_info(item_seq):
    """상세 페이지에서 위탁제조업체, 허가심사유형, 주성분(보조) 수집"""
    url = f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
    driver.get(url)
    time.sleep(2) # 상세 페이지 로딩 대기
    soup = BeautifulSoup(driver.page_source, "html.parser")
    
    mfg, rv_type, ingr = "", "", ""
    try:
        # 위탁제조업체 찾기
        th_mfg = soup.find("th", string=lambda t: t and "위탁제조업체" in t)
        if th_mfg: mfg = th_mfg.find_next_sibling("td").text.strip()
        
        # 허가심사유형 찾기
        th_rv = soup.find("th", string=lambda t: t and "허가심사유형" in t)
        if th_rv: rv_type = th_rv.find_next_sibling("td").text.strip()
        
        # 주성분(API 실패 대비)
        th_ingr = soup.find("th", string=lambda t: t and "주성분" in t)
        if th_ingr: ingr = th_ingr.find_next_sibling("td").text.strip()
    except: pass
    return mfg, rv_type, ingr

def run_scraper():
    print(f"=== 🚀 보완 완료 버전 수집 시작 ({start_date.strftime('%Y-%m-%d')} ~) ===")
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
        
        if re.search(r'\d', clean_data(cols[4])): continue # 취하 제품 패스

        try:
            item_seq = re.search(r"(\d{9})", str(cols[1].find("a"))).group(1)
            if item_seq in existing_seqs: continue
            
            # 상세 정보 수집 (API + 페이지 크롤링)
            api = get_api_data(item_seq)
            mfg, rv_type, detail_ingr = get_detail_info(item_seq)
            
            # 주성분 결정 (API 우선, 안되면 상세페이지 데이터)
            final_ingr = api["ingr"] if (api and api["ingr"]) else detail_ingr
            
            new_row = [
                item_seq, clean_data(cols[1]), final_ingr, clean_data(cols[2]), 
                clean_data(cols[3]), clean_data(cols[5]), mfg, rv_type, 
                f'=HYPERLINK("https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}", "클릭")',
                "", "", today.strftime("%Y-%m-%d %H:%M:%S")
            ]
            
            worksheet.append_row(new_row, value_input_option='USER_ENTERED')
            existing_seqs.append(item_seq)
            count += 1
            print(f"   ✅ 보완 수집 완료: {clean_data(cols[1])}")
        except: continue

    print(f"🏁 신규 {count}건 업데이트 완료!")
    driver.quit()

if __name__ == "__main__":
    run_scraper()
