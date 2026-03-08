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

def safe_clean(td):
    text = td.get_text(separator=" ", strip=True)
    # 🌟 "제품명"을 지우개 목록에 추가했습니다!
    labels = ["제품명", "업체명", "허가일자", "전문/일반", "취소/취하일자", "분류"]
    for label in labels:
        text = text.replace(label, "").strip()
    return text

def get_api_data(item_seq):
    api_url = "http://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService07/getDrugPrdtPrmsnDtlInq06"
    params = {"serviceKey": urllib.parse.unquote(mfds_api_key), "item_seq": item_seq, "type": "json"}
    try:
        res = requests.get(api_url, params=params, timeout=10).json()
        return {"ingr": res["body"]["items"][0].get("MAIN_ITEM_INGR", "")}
    except: return None

def get_detail_info(item_seq):
    url = f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
    driver.get(url)
    time.sleep(1.5)
    soup = BeautifulSoup(driver.page_source, "html.parser")
    mfg, rv_type, detail_ingr = "", "", ""
    try:
        th_mfg = soup.find("th", string=lambda t: t and "위탁제조업체" in t)
        if th_mfg: mfg = th_mfg.find_next_sibling("td").text.strip()
        
        th_rv = soup.find("th", string=lambda t: t and "허가심사유형" in t)
        if th_rv: rv_type = th_rv.find_next_sibling("td").text.strip()
        
        th_ingr = soup.find("th", string=lambda t: t and "주성분" in t)
        if th_ingr: detail_ingr = th_ingr.find_next_sibling("td").get_text(separator=", ", strip=True)
    except: pass
    return mfg, rv_type, detail_ingr

def run_scraper():
    print(f"=== 🚀 직관적 필터링 수집 시작 ({start_date.strftime('%Y-%m-%d')} ~) ===")
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
        
        cancel_date = safe_clean(cols[4])
        if cancel_date and re.search(r'\d', cancel_date): 
            continue

        try:
            item_seq = re.search(r"(\d{9})", str(cols[1].find("a"))).group(1)
            if item_seq in existing_seqs: continue
            
            product_name = safe_clean(cols[1])
            api = get_api_data(item_seq)
            mfg, rv_type, detail_ingr = get_detail_info(item_seq)
            
            raw_ingr = api["ingr"] if (api and api["ingr"]) else detail_ingr
            
            clean_ingr = re.sub(r'\[M\d+\]', '', raw_ingr)
            clean_ingr = clean_ingr.replace('|', ', ').strip()
            clean_ingr = re.sub(r',\s*,', ',', clean_ingr)
            
            # 🌟 요약 열이 삭제되어 데이터 칸 수를 11칸으로 맞췄습니다.
            new_row = [
                item_seq, product_name, clean_ingr, safe_clean(cols[2]), 
                safe_clean(cols[3]), safe_clean(cols[5]), mfg, rv_type, 
                f'=HYPERLINK("https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}", "클릭")',
                "", # J열: AI_분류 (빈칸 대기)
                today.strftime("%Y-%m-%d %H:%M:%S") # K열: 수집일시
            ]
            
            worksheet.append_row(new_row, value_input_option='USER_ENTERED')
            existing_seqs.append(item_seq)
            count += 1
            print(f"   ✅ 수집됨: {product_name}")
        except: continue

    print(f"🏁 신규 {count}건 업데이트 완료!")
    driver.quit()

if __name__ == "__main__":
    run_scraper()
