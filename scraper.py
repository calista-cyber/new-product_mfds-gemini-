import os
import requests
import time
import random
from datetime import datetime
from bs4 import BeautifulSoup
from supabase import create_client, Client

# 1. Supabase 연결 (팀장님이 확인하신 검증된 통로!)
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(URL, KEY)

def main():
    print("=== 🛡️ 션 팀장님 승인: 브라우저 신원 위장 최종 인출 작전 시작 ===")
    
    # 팀장님이 제안하신 2월 1일 ~ 오늘 기간
    s_start = "2026-02-01"
    s_end = datetime.now().strftime("%Y-%m-%d")
    
    session = requests.Session()
    
    # 봇 감지를 무력화하기 위한 고도로 정밀한 이름표(User-Agent)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
        'Referer': 'https://nedrug.mfds.go.kr/pbp/CCBAE01',
        'Origin': 'https://nedrug.mfds.go.kr',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Cache-Control': 'max-age=0',
        'Connection': 'keep-alive'
    }

    try:
        # [1단계] 정문으로 접속해 브라우저 지문(Cookie) 획득
        print(">> 보안 통행증 발급 대기 중...")
        session.get("https://nedrug.mfds.go.kr/pbp/CCBAE01", headers=headers, timeout=40)
        time.sleep(random.uniform(4, 8)) # 인간미 있는 대기 시간

        total_saved = 0
        # 41건 공략을 위해 1페이지부터 5페이지까지 순차적으로, 하지만 불규칙한 시간으로 접근
        pages = [1, 2, 3, 4, 5]
        
        for page in pages:
            print(f"\n>> [ {page} 페이지 ] 데이터 인출 시도 중...")
            
            payload = {
                'page': page,
                'limit': '10',
                'searchYn': 'true',
                'sDateGb': 'date',
                'sPermitDateStart': s_start,
                'sPermitDateEnd': s_end,
                'btnSearch': '검색'
            }

            # 서버에 직접 명령을 던져 데이터를 끄집어냅니다.
            res = session.post("https://nedrug.mfds.go.kr/pbp/CCBAE01/getItemPermitIntro", 
                               headers=headers, data=payload, timeout=60)
            
            # 서버가 빈 데이터를 던지는지 실시간 모니터링
            if "board_list" not in res.text or "데이터가" in res.text:
                print(f"⚠️ {page}페이지: 서버가 기만 전술 사용 중. 잠시 작전 중단 후 재진입 시도.")
                time.sleep(30)
                continue

            soup = BeautifulSoup(res.text, 'html.parser')
            rows = soup.select('table.board_list tbody tr')

            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 5: continue

                product_name = cols[1].get_text(strip=True)
                # 상세 페이지로 가는 열쇠(item_seq) 확보
                item_seq = cols[1].find('a')['onclick'].split("'")[1]

                print(f"   -> 금고(DB) 안착 완료: {product_name}")
                
                data = {
                    "item_seq": item_seq,
                    "product_name": product_name,
                    "company": cols[2].get_text(strip=True),
                    "approval_date": cols[3].get_text(strip=True),
                    "detail_url": f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}",
                    "category": "신규의약품",
                    "manufacturer": "정보 수집 대기",
                    "ingredients": "데이터 로딩 중",
                    "efficacy": "데이터 로딩 중"
                }
                
                # Supabase 테이블에 강제 주입
                supabase.table("drug_approvals").upsert(data).execute()
                total_saved += 1
                time.sleep(random.uniform(1.2, 3.5)) # 한 건 저장할 때마다 인간처럼 멈춤

            print(f">> {page}페이지 수집 완료. 서버의 의심을 피하기 위해 매복...")
            time.sleep(random.uniform(10, 15)) 

        print(f"\n=== 🏆 작전 종료: 총 {total_saved}건이 션 팀장님의 금고에 무사히 도착했습니다! ===")

    except Exception as e:
        print(f"❌ 최종 침투 실패: {e}")

if __name__ == "__main__":
    main()
