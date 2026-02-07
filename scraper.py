import os
import requests
import time
import random
from datetime import datetime
from bs4 import BeautifulSoup
from supabase import create_client, Client

# 1. Supabase 연결
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(URL, KEY)

def main():
    print("=== 🛡️ 션 팀장님 전용: 게릴라 데이터 인출 작전 시작 ===")
    
    s_start = "2026-02-01"
    s_end = datetime.now().strftime("%Y-%m-%d")
    
    session = requests.Session()
    # 사람처럼 보이기 위해 헤더를 더 정교하게 구성
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
        'Referer': 'https://nedrug.mfds.go.kr/pbp/CCBAE01'
    })

    try:
        # 첫 접속 후 랜덤하게 대기 (3~7초)
        session.get("https://nedrug.mfds.go.kr/pbp/CCBAE01", timeout=40)
        time.sleep(random.uniform(3, 7))

        total_saved = 0
        pages = [1, 2, 3, 4, 5]
        random.shuffle(pages) # 페이지 순서를 뒤섞어 봇 감지 회피

        for page in pages:
            print(f"\n>> [ {page} 페이지 ] 기습 침투 중...")
            payload = {
                'page': page,
                'searchYn': 'true',
                'sDateGb': 'date',
                'sPermitDateStart': s_start,
                'sPermitDateEnd': s_end,
                'btnSearch': '검색'
            }

            res = session.post("https://nedrug.mfds.go.kr/pbp/CCBAE01/getItemPermitIntro", 
                               data=payload, timeout=50)
            
            if "데이터가" in res.text or "board_list" not in res.text:
                print(f"⚠️ {page}페이지: 서버가 기만 전술 사용 중. 건너뜁니다.")
                continue

            soup = BeautifulSoup(res.text, 'html.parser')
            rows = soup.select('table.board_list tbody tr')

            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 5: continue

                product_name = cols[1].get_text(strip=True)
                item_seq = cols[1].find('a')['onclick'].split("'")[1]

                print(f"   -> DB 전송: {product_name}")
                data = {
                    "item_seq": item_seq,
                    "product_name": product_name,
                    "company": cols[2].get_text(strip=True),
                    "approval_date": cols[3].get_text(strip=True),
                    "detail_url": f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
                }
                
                supabase.table("drug_approvals").upsert(data).execute()
                total_saved += 1
                time.sleep(random.uniform(1, 3)) # 데이터 간 랜덤 휴식

            time.sleep(random.uniform(5, 10)) # 페이지 간 충분한 휴식

        print(f"\n=== 🏆 작전 종료: 총 {total_saved}건 안착! ===")

    except Exception as e:
        print(f"❌ 오류 발생: {e}")

if __name__ == "__main__":
    main()
