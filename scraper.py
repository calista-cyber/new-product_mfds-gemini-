import os, time, json, requests, urllib.parse, re
from datetime import datetime, timedelta, timezone
import gspread
from google.oauth2.service_account import Credentials

# 1. 설정
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
gcp_secret = os.environ.get("GCP_SERVICE_ACCOUNT")
sheet_id = os.environ.get("GOOGLE_SHEET_ID")
mfds_api_key = os.environ.get("MFDS_API_KEY") 

credentials = Credentials.from_service_account_info(json.loads(gcp_secret), scopes=scope)
gc = gspread.authorize(credentials)
worksheet = gc.open_by_key(sheet_id).sheet1

# 2. 날짜 설정 (최근 7일 - 주간 자동화 기준)
KST = timezone(timedelta(hours=9))
today = datetime.now(KST)
start_date = today - timedelta(days=7)
start_date_str = start_date.strftime('%Y%m%d') # API 날짜 비교용 (YYYYMMDD)

def run_api_scraper():
    print(f"=== 🚀 100% API 기반 수집 시작 ({start_date.strftime('%Y-%m-%d')} ~) ===")
    
    try:
        existing_seqs = [str(r.get('품목기준코드', '')) for r in worksheet.get_all_records()]
    except Exception:
        print("⚠️ 구글 시트 로드 실패")
        existing_seqs = []

    count = 0
    api_url = "http://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService07/getDrugPrdtPrmsnDtlInq06"
    
    # 3. API 호출 (최신 허가 품목 확보를 위해 상위 페이지 탐색)
    for page in range(1, 6):
        params = {
            "serviceKey": urllib.parse.unquote(mfds_api_key),
            "pageNo": page,
            "numOfRows": 100,
            "type": "json"
        }
        
        try:
            res = requests.get(api_url, params=params, timeout=15).json()
            items = res.get("body", {}).get("items", [])
            
            if not items:
                break
                
            for item in items:
                permit_date = str(item.get("ITEM_PERMIT_DATE", ""))
                cancel_date = str(item.get("CANCEL_DATE", ""))
                
                # 취소/취하 품목 제외
                if cancel_date:
                    continue
                    
                # 날짜 필터링 (최근 7일 이내 데이터만 추출)
                if permit_date < start_date_str:
                    continue 
                    
                item_seq = str(item.get("ITEM_SEQ", ""))
                if not item_seq or item_seq in existing_seqs:
                    continue
                    
                product_name = item.get("ITEM_NAME", "")
                entp_name = item.get("ENTP_NAME", "")
                etc_otc = item.get("ETC_OTC_CODE", "")
                
                # 주성분 전처리
                raw_ingr = item.get("MAIN_ITEM_INGR", "-")
                clean_ingr = re.sub(r'\[M\d+\]', '', raw_ingr)
                clean_ingr = clean_ingr.replace('|', ', ').strip()
                clean_ingr = re.sub(r',\s*,', ',', clean_ingr)
                
                # API 구조상 직접 표기되지 않는 상세 웹 전용 필드는 "-" 또는 기본값 처리
                mfg = item.get("MAKE_MATERIAL_FLAG", "-") 
                rv_type = "-" 
                
                # 날짜 포맷 변경 (YYYYMMDD -> YYYY-MM-DD)
                if len(permit_date) == 8:
                    formatted_date = f"{permit_date[:4]}-{permit_date[4:6]}-{permit_date[6:]}"
                else:
                    formatted_date = permit_date
                
                new_row = [
                    item_seq, product_name, clean_ingr, entp_name, 
                    formatted_date, etc_otc, mfg, rv_type, 
                    f'=HYPERLINK("https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}", "클릭")',
                    "", # J열: AI_분류 (빈칸 대기)
                    today.strftime("%Y-%m-%d %H:%M:%S") # K열
                ]
                
                worksheet.append_row(new_row, value_input_option='USER_ENTERED')
                existing_seqs.append(item_seq)
                count += 1
                print(f"   ✅ 수집됨: {product_name}")
                
            time.sleep(0.5) # API 호출 제한 방어
        except Exception as e:
            print(f"❌ API 호출 에러: {e}")
            break

    print(f"🏁 신규 {count}건 업데이트 완료!")

if __name__ == "__main__":
    run_api_scraper()
