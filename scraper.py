import os
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
import gspread
from google.oauth2.service_account import Credentials

# 1. 구글 시트 연동 설정
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
gcp_secret = os.environ.get("GCP_SERVICE_ACCOUNT")
sheet_id = os.environ.get("GOOGLE_SHEET_ID")

if not gcp_secret or not sheet_id:
    print("🚨 구글 클라우드 인증키 또는 시트 ID가 설정되지 않았습니다.")
    exit()

# JSON 텍스트를 파이썬 딕셔너리로 변환하여 인증
credentials = Credentials.from_service_account_info(json.loads(gcp_secret), scopes=scope)
gc = gspread.authorize(credentials)
doc = gc.open_by_key(sheet_id)
worksheet = doc.sheet1 # 첫 번째 탭(시트) 사용

# 2. 날짜 설정 (한국 표준시 KST)
KST = timezone(timedelta(hours=9))
today = datetime.now(KST)
start_date = today - timedelta(days=7) # 최근 1주일치 검색

str_start = start_date.strftime("%Y-%m-%d")
str_end = today.strftime("%Y-%m-%d")

def run_scraper():
    print(f"=== 🕵️‍♀️ 구글 시트 수집 모드 가동 ({str_start} ~ {str_end}) ===")
    
    url = f"https://nedrug.mfds.go.kr/searchDrug/searchDrugList?page=1&searchYn=true&startDate={str_start}&endDate={str_end}&searchType=ST1&searchKeyword=&pageSize=100"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    }

    try:
        res = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")
        
        table = soup.find("table", class_="dr_table")
        if not table:
            print("❌ 테이블을 찾을 수 없습니다. (식약처 서버 응답 확인 필요)")
            return

        rows = table.find("tbody").find_all("tr")
        if len(rows) == 1 and "데이터가 없습니다" in rows[0].text:
            print(">> 해당 기간에 신규 허가된 의약품이 없습니다.")
            return

        print(f"🔎 웹페이지에서 총 {len(rows)}개의 의약품 후보 발견")

        # 🌟 핵심: 기존 구글 시트에 있는 품목기준코드 목록을 가져와서 중복 방지
        existing_data = worksheet.get_all_records()
        existing_seqs = [str(row.get('품목기준코드', '')) for row in existing_data]

        count = 0
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 5: continue
                
            try:
                link_tag = cols[1].find("a")
                item_seq = link_tag["href"].split("itemSeq=")[1].split("&")[0]
                
                # 시트에 이미 있는 코드면 패스 (중복 추가 방지)
                if item_seq in existing_seqs:
                    continue
                    
                product_name = link_tag.text.strip()
                company = cols[2].text.strip()
                category = cols[3].text.strip()
                approval_date = cols[4].text.strip()
                detail_url = "https://nedrug.mfds.go.kr" + link_tag["href"]
                collected_at = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")

                # 시트에 추가할 데이터 한 줄 (A~I열 순서에 맞게 배열)
                new_row = [item_seq, product_name, company, category, approval_date, detail_url, "", "", collected_at]
                
                # 구글 시트의 가장 아래 빈칸에 데이터 추가
                worksheet.append_row(new_row)
                existing_seqs.append(item_seq) # 방금 넣은 데이터도 중복 목록에 임시 추가
                count += 1
                
            except Exception as e:
                print(f"⚠️ 개별 데이터 처리 중 에러: {e}")
                continue

        print(f"✅ 수집 완료: 구글 스프레드시트에 총 {count}건이 성공적으로 추가되었습니다! 🎉")

    except Exception as e:
        print(f"🚨 스크래핑 시스템 오류: {e}")

if __name__ == "__main__":
    run_scraper()
