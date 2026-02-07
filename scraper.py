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
    print("=== 🚨 션 팀장님 제안: '보안 우회 & 강제 인출' 작전 시작 ===")
    
    # 2월 1일부터 오늘까지
    s_start = "2026-02-01"
    s_end = datetime.now().strftime("%Y-%m-%d")
    
    session = requests.Session()
    # 통행증(Cookie) 발급을 위해 정문으로 입장
    session.get("https://nedrug.mfds.go.kr/pbp/CCBAE01", timeout=30)
    
    # 서버를 완벽히 속이기 위한 정밀 헤더
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
        'Referer': 'https://nedrug.mfds.go.kr/pbp/CCBAE01',
        'Origin': 'https://nedrug.mfds.go.kr',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8'
    }

    total_saved = 0

    # 41건을 모두 잡기 위해 1~5페이지 강제 순회
    for page in range(1, 6):
        print(f"\n>> [ {page} 페이지 ] 보안 장벽 우회 중...")
        
        # 서버가 "이건 진짜 사람이다"라고 믿게 만드는 파라미터 조합
        payload = {
            'page': page,
            'limit': '10',
            'searchYn': 'true',
            'sDateGb': 'date', # 일자검색 강제 활성화
            'sPermitDateStart': s_start,
            'sPermitDateEnd': s_end,
            'btnSearch': '검색'
        }

        try:
            # POST 방식으로 명령어를 실어 보내 서버의 항복을 받아냅니다.
            res = session.post("https://nedrug.mfds.go.kr/pbp/CCBAE01/getItemPermitIntro", 
                               headers=headers, data=payload, timeout=40)
            
            soup = BeautifulSoup(res.text, 'html.parser')
            rows = soup.select('table.board_list tbody tr')

            if not rows or "데이터가" in rows[0].get_text():
                print("⚠️ 주의: 서버가 빈 데이터를 보냈습니다. 재시도 필요.")
                break

            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 5 or cols[4].get_text(strip=True): continue 

                product_name = cols[1].get_text(strip=True)
                item_seq = cols[1].find('a')['onclick'].split("'")[1]

                print(f"   -> 금고 안착 완료: {product_name}")
                
                # 팀장님이 요청하신 7가지 항목 구조로 데이터 생성
                data = {
                    "item_seq": item_seq,
                    "product_name": product_name,
                    "company": cols[2].get_text(strip=True),
                    "manufacturer": "상세 수집 중", 
                    "category": "전문의약품" if "전문" in product_name else "일반의약품", 
                    "approval_type": "품목허가",
                    "ingredients": "성분 로딩 중",
                    "efficacy": "효능 로딩 중",
                    "approval_date": cols[3].get_text(strip=True),
                    "detail_url": f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
                }
                
                # Supabase 저장
                supabase.table("drug_approvals").upsert(data).execute()
                total_saved += 1

            time.sleep(2) # 서버의 의심을 피하기 위한 휴식

        except Exception as e:
            print(f"⚠️ 에러 발생: {e}")
            continue

    print(f"\n=== 🏆 성공: 총 {total_saved}건이 Supabase 금고에 안착했습니다! ===")

if __name__ == "__main__":
    main()
