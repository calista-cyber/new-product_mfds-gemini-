import os
import requests
import time
from datetime import datetime
from bs4 import BeautifulSoup
from supabase import create_client, Client

# 1. Supabase 연결 (절대 건드리지 마세요!)
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(URL, KEY)

def main():
    print("=== 🚀 션 팀장님 전용: 데이터 강제 수집 작전 시작 ===")
    
    # 2월 1일부터 오늘까지 (팀장님 제안 날짜)
    s_start = "2026-02-01"
    s_end = datetime.now().strftime("%Y-%m-%d")
    
    # 세션 유지 (진짜 사람처럼 보이게 함)
    session = requests.Session()
    session.get("https://nedrug.mfds.go.kr/pbp/CCBAE01", timeout=20)
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://nedrug.mfds.go.kr/pbp/CCBAE01',
        'Origin': 'https://nedrug.mfds.go.kr',
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    total_saved = 0

    # 41건을 모두 잡기 위해 1~5페이지 순차 공략
    for page in range(1, 6):
        print(f"\n>> [ {page} 페이지 ] 데이터 인계 중...")
        
        # [핵심] 식약처 서버가 요구하는 검색 신호를 몸통(Data)에 실어 보냅니다.
        payload = {
            'page': page,
            'searchYn': 'true',
            'sDateGb': 'date',
            'sPermitDateStart': s_start,
            'sPermitDateEnd': s_end,
            'btnSearch': ''
        }

        try:
            # POST 방식으로 요청하여 서버가 "검색 버튼을 눌렀다"고 믿게 만듭니다.
            res = session.post("https://nedrug.mfds.go.kr/pbp/CCBAE01/getItemPermitIntro", 
                               headers=headers, data=payload, timeout=30)
            
            soup = BeautifulSoup(res.text, 'html.parser')
            rows = soup.select('table.board_list tbody tr')

            if not rows or "데이터가" in rows[0].get_text():
                print("더 이상 수집할 데이터가 없습니다.")
                break

            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 5 or cols[4].get_text(strip=True): continue 

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
                
                # Supabase에 데이터 꽂기 (Upsert)
                supabase.table("drug_approvals").upsert(data).execute()
                total_saved += 1

            time.sleep(1) # 서버 예의 대기

        except Exception as e:
            print(f"⚠️ {page}페이지 요청 실패: {e}")
            continue

    print(f"\n=== 🏆 작전 종료: 총 {total_saved}건이 Supabase 금고에 안착했습니다! ===")

if __name__ == "__main__":
    main()
