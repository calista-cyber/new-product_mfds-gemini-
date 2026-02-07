import os
import requests
import time
from datetime import datetime
from bs4 import BeautifulSoup
from supabase import create_client, Client

# 1. Supabase 설정
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(URL, KEY)

def main():
    print("=== 🚀 션 팀장님 전용: 식약처 보안 우회 & 강제 인출 작전 ===")
    
    # 2월 1일부터 오늘까지
    s_start = "2026-02-01"
    s_end = datetime.now().strftime("%Y-%m-%d")
    
    session = requests.Session()
    session.get("https://nedrug.mfds.go.kr/pbp/CCBAE01", timeout=20)
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
        'Referer': 'https://nedrug.mfds.go.kr/pbp/CCBAE01',
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    total_saved = 0

    # 41건을 모두 잡기 위해 1~5페이지 순회
    for page in range(1, 6):
        print(f"\n>> [ {page} 페이지 ] 데이터 침투 중...")
        
        # 식약처 서버가 '사람'이라고 믿게 만드는 필수 파라미터 조합
        payload = {
            'page': page,
            'limit': '10',
            'searchYn': 'true',
            'sDateGb': 'date',
            'sPermitDateStart': s_start,
            'sPermitDateEnd': s_end,
            'btnSearch': '검색'
        }

        try:
            res = session.post("https://nedrug.mfds.go.kr/pbp/CCBAE01/getItemPermitIntro", 
                               headers=headers, data=payload, timeout=30)
            
            soup = BeautifulSoup(res.text, 'html.parser')
            rows = soup.select('table.board_list tbody tr')

            if not rows or "데이터가" in rows[0].get_text():
                print("더 이상 데이터가 없습니다.")
                break

            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 5 or cols[4].get_text(strip=True): continue 

                product_name = cols[1].get_text(strip=True)
                item_seq = cols[1].find('a')['onclick'].split("'")[1]

                print(f"   -> 금고로 이송: {product_name}")
                
                # [데이터 구조 일치화] 팀장님이 요청하신 모든 항목을 담습니다.
                data = {
                    "item_seq": item_seq,
                    "product_name": product_name,
                    "company": cols[2].get_text(strip=True),
                    "manufacturer": "정보 수집 중...", # 상세페이지에서 가져오도록 확장 가능
                    "category": "전문의약품" if "전문" in product_name else "일반의약품", 
                    "approval_type": "품목허가",
                    "ingredients": "수집 대기",
                    "efficacy": "수집 대기",
                    "approval_date": cols[3].get_text(strip=True),
                    "detail_url": f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
                }
                
                # Supabase 저장
                supabase.table("drug_approvals").upsert(data).execute()
                total_saved += 1

            time.sleep(1)

        except Exception as e:
            print(f"⚠️ 에러 발생: {e}")
            continue

    print(f"\n=== 🏆 작전 성공: 총 {total_saved}건이 금고에 안착했습니다! ===")

if __name__ == "__main__":
    main()
