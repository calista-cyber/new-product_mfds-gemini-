import os
import requests
import time
from datetime import datetime
from bs4 import BeautifulSoup
from supabase import create_client, Client

# 1. Supabase 설정 (절대 수정 금지)
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(URL, KEY)

def main():
    print("=== 🚨 션 팀장님 전용: 식약처 보안 완전 정복 작전 시작 ===")
    
    # [설정] 2월 1일부터 오늘까지 (41건 정밀 타격 기간)
    s_start = "2026-02-01"
    s_end = datetime.now().strftime("%Y-%m-%d")
    
    session = requests.Session()
    # 통행증(Cookie) 발급을 위한 첫 방문
    session.get("https://nedrug.mfds.go.kr/pbp/CCBAE01", timeout=20)
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
        'Referer': 'https://nedrug.mfds.go.kr/pbp/CCBAE01',
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    total_saved = 0

    # 41건 수집을 위해 1~5페이지 순차 공략
    for page in range(1, 6):
        print(f"\n>> [ {page} 페이지 ] 데이터 강제 인출 중...")
        
        # 서버가 "사람이 검색했다"고 믿게 만드는 필수 파라미터 조합
        payload = {
            'page': page,
            'limit': '10',
            'searchYn': 'true',
            'sDateGb': 'date', # 일자검색 모드 활성화
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
                print("수집 가능한 데이터가 없습니다.")
                break

            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 5 or cols[4].get_text(strip=True): continue 

                product_name = cols[1].get_text(strip=True)
                item_seq = cols[1].find('a')['onclick'].split("'")[1]

                print(f"   -> 금고 안착: {product_name}")
                
                # 팀장님이 요청하신 7가지 항목 구조로 데이터 생성
                data = {
                    "item_seq": item_seq,
                    "product_name": product_name,
                    "company": cols[2].get_text(strip=True),
                    "manufacturer": "상세정보 수집 중", # 상세페이지 추가 수집용
                    "category": "전문의약품" if "전문" in product_name else "일반의약품", 
                    "approval_type": "품목허가",
                    "ingredients": "데이터 로딩 중",
                    "efficacy": "데이터 로딩 중",
                    "approval_date": cols[3].get_text(strip=True),
                    "detail_url": f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
                }
                
                # Supabase 저장 (Upsert)
                supabase.table("drug_approvals").upsert(data).execute()
                total_saved += 1

            time.sleep(1)

        except Exception as e:
            print(f"⚠️ 에러 발생: {e}")
            continue

    print(f"\n=== 🏆 성공: 총 {total_saved}건이 금고에 안착했습니다! ===")

if __name__ == "__main__":
    main()
