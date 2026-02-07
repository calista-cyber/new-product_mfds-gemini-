import os
import requests
import time
from datetime import datetime
from bs4 import BeautifulSoup
from supabase import create_client, Client

# 1. Supabase 설정 (Secrets에 입력한 값 자동 로드)
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(URL, KEY)

def main():
    print("=== 🚀 션 팀장님 제안: '새로운 방식(직접 타격)' 작전 시작 ===")
    
    # [설정] 팀장님이 제안하신 2월 1일부터 오늘까지의 기간
    s_start = "2026-02-01"
    s_end = datetime.now().strftime("%Y-%m-%d")
    
    # 1. 통행증(세션/쿠키) 발급
    session = requests.Session()
    session.get("https://nedrug.mfds.go.kr/pbp/CCBAE01", timeout=20)
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
        'Referer': 'https://nedrug.mfds.go.kr/pbp/CCBAE01',
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    total_saved = 0

    # 2. 41건을 모두 가져오기 위해 1~5페이지 순차 공략
    for page in range(1, 6):
        print(f"\n>> [ {page} 페이지 ] 데이터 직접 요청 중...")
        
        # 서버가 데이터를 내놓을 수밖에 없는 '마법의 파라미터' 조합
        payload = {
            'page': page,
            'limit': '10',
            'searchYn': 'true',
            'sDateGb': 'date', # 일자검색 강제 활성화
            'sPermitDateStart': s_start,
            'sPermitDateEnd': s_end,
            'btnSearch': '검색' # 서버에 "나 진짜 검색 버튼 눌렀어"라고 외침
        }

        try:
            # 뒷문으로 직접 데이터를 요구합니다.
            res = session.post("https://nedrug.mfds.go.kr/pbp/CCBAE01/getItemPermitIntro", 
                               headers=headers, data=payload, timeout=30)
            
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

                print(f"   -> DB 전송 대기: {product_name}")
                
                # 팀장님이 요청하신 7개 항목 구조로 데이터 패키징
                data = {
                    "item_seq": item_seq,
                    "product_name": product_name,
                    "company": cols[2].get_text(strip=True),
                    "manufacturer": "상세 수집 대기", 
                    "category": "전문의약품" if "전문" in product_name else "일반의약품", 
                    "approval_type": "품목허가",
                    "ingredients": "성분 로딩 중",
                    "efficacy": "효능 로딩 중",
                    "approval_date": cols[3].get_text(strip=True),
                    "detail_url": f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
                }
                
                # Supabase 금고에 안착 (Upsert)
                supabase.table("drug_approvals").upsert(data).execute()
                total_saved += 1

            time.sleep(1) # 서버의 의심을 피하기 위한 짧은 휴식

        except Exception as e:
            print(f"⚠️ 에러 발생: {e}")
            continue

    print(f"\n=== 🏆 성공: 총 {total_saved}건이 Supabase 금고에 안착했습니다! ===")

if __name__ == "__main__":
    main()
