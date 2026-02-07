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
    print("=== 🛡️ 션 팀장님 전용: 야간 매복 데이터 인출 작전 시작 ===")
    
    s_start = "2026-02-01"
    s_end = datetime.now().strftime("%Y-%m-%d")
    
    # 봇 감지를 피하기 위한 다양한 이름표(User-Agent) 준비
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
    ]

    session = requests.Session()
    
    try:
        # 무작위 이름표 선택
        session.headers.update({'User-Agent': random.choice(user_agents), 'Referer': 'https://nedrug.mfds.go.kr/pbp/CCBAE01'})
        session.get("https://nedrug.mfds.go.kr/pbp/CCBAE01", timeout=40)
        time.sleep(random.uniform(5, 10)) # 충분한 초기 대기

        total_saved = 0
        pages = [1, 2, 3, 4, 5]
        random.shuffle(pages)

        for page in pages:
            print(f"\n>> [ {page} 페이지 ] 매복 침투 중...")
            payload = {'page': page, 'searchYn': 'true', 'sDateGb': 'date', 'sPermitDateStart': s_start, 'sPermitDateEnd': s_end, 'btnSearch': '검색'}

            # 요청 보낼 때마다 이름표 교체
            session.headers.update({'User-Agent': random.choice(user_agents)})
            res = session.post("https://nedrug.mfds.go.kr/pbp/CCBAE01/getItemPermitIntro", data=payload, timeout=50)
            
            if "board_list" not in res.text or "데이터가" in res.text:
                print(f"⚠️ {page}페이지: 서버가 감시 중입니다. 30초간 매복(대기)...")
                time.sleep(30)
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
                    "item_seq": item_seq, "product_name": product_name, "company": cols[2].get_text(strip=True),
                    "approval_date": cols[3].get_text(strip=True),
                    "detail_url": f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
                }
                
                supabase.table("drug_approvals").upsert(data).execute()
                total_saved += 1
                time.sleep(random.uniform(2, 5)) # 데이터 간 긴 휴식

            time.sleep(random.uniform(10, 20)) # 페이지 간 긴 휴식

        print(f"\n=== 🏆 작전 종료: 총 {total_saved}건 안착! ===")

    except Exception as e:
        print(f"❌ 오류 발생: {e}")

if __name__ == "__main__":
    main()
