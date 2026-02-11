import os
import requests
from bs4 import BeautifulSoup
from supabase import create_client, Client
from datetime import datetime, timedelta, timezone

# 1. 설정
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("🚨 Supabase 환경변수가 없습니다.")
    exit()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 2. 날짜 설정 (🕑 여기가 핵심! 한국 시간 KST 적용)
# GitHub 서버(UTC)가 아니라 '한국 시간' 기준으로 날짜를 잡아야 '오늘' 데이터를 가져옵니다.
KST = timezone(timedelta(hours=9))
end_date = datetime.now(KST)
start_date = end_date - timedelta(days=14) # 넉넉하게 2주치 조회 (누락 방지)

str_start = start_date.strftime("%Y%m%d")
str_end = end_date.strftime("%Y%m%d")

print(f"=== 🕵️‍♀️ 데이터 수집 시작 (한국시간: {str_start} ~ {str_end}) ===")

def run_scraper():
    # 3. URL 수정 (searchType 제거 -> 조건 없이 날짜로만 검색)
    # pageSize=100 : 한 번에 100개씩 긁어오기
    url = f"https://nedrug.mfds.go.kr/searchDrug/searchDrugList?page=1&searchYn=true&startDate={str_start}&endDate={str_end}&pageSize=100"
    
    # 4. 헤더 추가 (봇 차단 방지용 '주민등록증')
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    try:
        res = requests.get(url, headers=headers)
        soup = BeautifulSoup(res.text, "html.parser")
        
        # 테이블 찾기
        table = soup.find("div", class_="r_sec").find("table", class_="dr_table")
        if not table:
            print("❌ 식약처 사이트에서 테이블을 못 찾았습니다. (구조 변경 또는 접속 차단)")
            return

        rows = table.find("tbody").find_all("tr")
        print(f"🔎 검색된 의약품 수: {len(rows)}개")

        # '검색 결과가 없습니다' 처리
        if len(rows) == 1 and "검색된 데이터가 없습니다" in rows[0].text:
            print(">> 해당 기간에 신규 허가된 의약품이 없습니다.")
            return

        count = 0
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 2:
                continue
                
            try:
                # 데이터 추출
                link_tag = cols[1].find("a")
                detail_href = link_tag["href"]
                
                if "itemSeq=" in detail_href:
                    item_seq = detail_href.split("itemSeq=")[1].split("&")[0]
                else:
                    continue

                item_name = link_tag.text.strip()
                company = cols[2].text.strip()
                category = cols[3].text.strip()
                approval_date = cols[4].text.strip()
                
                data = {
                    "item_seq": item_seq,
                    "product_name": item_name,
                    "company": company,
                    "category": category,
                    "approval_date": approval_date,
                    "detail_url": "https://nedrug.mfds.go.kr" + detail_href,
                    # created_at 생략 (DB 자동 생성)
                }

                # Supabase Upsert (중복이면 무시/업데이트, 없으면 추가)
                result = supabase.table("drug_approvals").upsert(data, on_conflict="item_seq").execute()
                count += 1
                
            except Exception as e:
                print(f"⚠️ 에러 발생 ({item_name}): {e}")
                continue

        print(f"✅ 수집 완료: 총 {count}건 처리됨")

    except Exception as e:
        print(f"🚨 스크래핑 치명적 오류: {e}")

if __name__ == "__main__":
    run_scraper()
