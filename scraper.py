import os
import requests
import time
from datetime import datetime
from bs4 import BeautifulSoup
from supabase import create_client, Client
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 1. Supabase 설정
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(URL, KEY)

def main():
    print("=== 🚀 션 팀장님 제안: '새로운 방식(인내심 강화)' 작전 시작 ===")
    
    s_start = "2026-02-01"
    s_end = datetime.now().strftime("%Y-%m-%d")
    
    # 2. 끈질긴 재시도 설정
    session = requests.Session()
    retry = Retry(
        total=5, # 최대 5번 재시도
        backoff_factor=2, # 재시도 간격 점진적 증가 (2, 4, 8, 16초...)
        status_forcelist=[500, 502, 503, 504], # 해당 에러 발생 시 재시도
        raise_on_status=False
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
        'Referer': 'https://nedrug.mfds.go.kr/pbp/CCBAE01'
    })

    try:
        # 첫 접속 타임아웃을 60초로 연장
        print(">> 식약처 서버 접속 시도 중 (최대 60초 대기)...")
        session.get("https://nedrug.mfds.go.kr/pbp/CCBAE01", timeout=60)
        time.sleep(3) # 접속 후 잠시 휴식

        total_saved = 0

        for page in range(1, 6):
            print(f"\n>> [ {page} 페이지 ] 데이터 요청 중...")
            
            payload = {
                'page': page,
                'limit': '10',
                'searchYn': 'true',
                'sDateGb': 'date',
                'sPermitDateStart': s_start,
                'sPermitDateEnd': s_end,
                'btnSearch': '검색'
            }

            # 데이터 요청 타임아웃도 60초로 설정
            res = session.post("https://nedrug.mfds.go.kr/pbp/CCBAE01/getItemPermitIntro", 
                               headers=session.headers, data=payload, timeout=60)
            
            soup = BeautifulSoup(res.text, 'html.parser')
            rows = soup.select('table.board_list tbody tr')

            if not rows or "데이터가" in rows[0].get_text():
                print("수집할 데이터가 더 이상 없습니다.")
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
                
                supabase.table("drug_approvals").upsert(data).execute()
                total_saved += 1
                time.sleep(0.5) # 개별 데이터 저장 후 짧은 휴식

            time.sleep(3) # 페이지 전환 전 충분한 휴식

        print(f"\n=== 🏆 성공: 총 {total_saved}건이 Supabase 금고에 안착했습니다! ===")

    except Exception as e:
        print(f"❌ 최종 실패: {e}")

if __name__ == "__main__":
    main()
