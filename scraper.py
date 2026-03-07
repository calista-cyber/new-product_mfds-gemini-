import os
import requests
from bs4 import BeautifulSoup
from supabase import create_client, Client
from datetime import datetime, timedelta, timezone

# 1. 설정 (Supabase)
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 2. 날짜 설정 (🕑 한국 표준시 KST 강제 적용)
# GitHub 서버(UTC)와의 9시간 차이를 보정하여 '오늘' 데이터를 정확히 수집합니다.
KST = timezone(timedelta(hours=9))
today = datetime.now(KST)
start_date = today - timedelta(days=7) # 최근 1주일치 데이터 집중 수집

str_start = start_date.strftime("%Y%m%d")
str_end = today.strftime("%Y%m%d")

def run_scraper():
    print(f"=== 🕵️‍♀️ 데이터 수집 시작 (검색범위: {str_start} ~ {str_end}) ===")
    
    # 3. URL 설정 (searchType=ST1: 제품명 검색 조건 추가로 테이블 유실 방지)
    url = f"https://nedrug.mfds.go.kr/searchDrug/searchDrugList?page=1&searchYn=true&startDate={str_start}&endDate={str_end}&searchType=ST1&pageSize=100"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    try:
        res = requests.get(url, headers=headers)
        soup = BeautifulSoup(res.text, "html.parser")
        
        # 4. 데이터 테이블 찾기
        table = soup.find("table", class_="dr_table")
        if not table:
            print("❌ 테이블을 찾을 수 없습니다. 식약처 서버 응답이 올바르지 않습니다.")
            return

        rows = table.find("tbody").find_all("tr")
        
        # 검색 결과 없음 처리
        if len(rows) == 1 and "데이터가 없습니다" in rows[0].text:
            print(">> 해당 기간에 신규 허가된 의약품이 없습니다.")
            return

        print(f"🔎 웹페이지에서 총 {len(rows)}개의 의약품 후보 발견")

        count = 0
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 5: continue
                
            try:
                link_tag = cols[1].find("a")
                item_seq = link_tag["href"].split("itemSeq=")[1].split("&")[0]
                
                data = {
                    "item_seq": item_seq,
                    "product_name": link_tag.text.strip(),
                    "company": cols[2].text.strip(),
                    "category": cols[3].text.strip(),
                    "approval_date": cols[4].text.strip(),
                    "detail_url": "https://nedrug.mfds.go.kr" + link_tag["href"]
                }

                # Supabase Upsert (중복은 무시하고 신규 품목기준코드만 추가)
                supabase.table("drug_approvals").upsert(data, on_conflict="item_seq").execute()
                count += 1
                
            except Exception:
                continue

        print(f"✅ 수집 완료: 총 {count}건의 데이터를 처리했습니다.")

    except Exception as e:
        print(f"🚨 스크래핑 시스템 오류: {e}")

if __name__ == "__main__":
    run_scraper()
