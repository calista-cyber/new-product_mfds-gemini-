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
    print("=== 🎯 션 팀장님 전용: 식약처 데이터 강제 인출 작전 시작 ===")
    
    # [설정] 2월 1일부터 오늘까지 (팀장님 정밀 타격 기간)
    s_start = "2026-02-01"
    s_end = datetime.now().strftime("%Y-%m-%d")
    
    # 진짜 브라우저처럼 보이기 위한 세션 및 쿠키 설정
    session = requests.Session()
    # 첫 접속을 통해 서버로부터 통행증(Cookie)을 발급받습니다.
    session.get("https://nedrug.mfds.go.kr/pbp/CCBAE01", timeout=20)
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
        'Referer': 'https://nedrug.mfds.go.kr/pbp/CCBAE01',
        'Origin': 'https://nedrug.mfds.go.kr',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8'
    }

    total_saved = 0

    # 41건 정복을 위해 1페이지부터 5페이지까지 순차 타격
    for page in range(1, 6):
        print(f"\n>> [ {page} 페이지 ] 데이터 강제 추출 중...")
        
        # 식약처 서버가 데이터를 내놓게 만드는 '마법의 명령어'들입니다.
        payload = {
            'page': page,
            'limit': '10',
            'sort': '',
            'sortOrder': 'false',
            'searchYn': 'true',
            'garaInputBox': '',
            'sDateGb': 'date', # 일자검색 모드 활성화
            'sPermitDateStart': s_start,
            'sPermitDateEnd': s_end,
            'sItemName': '',
            'sEntpName': '',
            'btnSearch': '검색' # 검색 버튼을 눌렀다는 명시적 신호
        }

        try:
            # POST 방식으로 명령어를 실어 보내 서버의 항복을 받아냅니다.
            res = session.post("https://nedrug.mfds.go.kr/pbp/CCBAE01/getItemPermitIntro", 
                               headers=headers, data=payload, timeout=30)
            
            soup = BeautifulSoup(res.text, 'html.parser')
            rows = soup.select('table.board_list tbody tr')

            # 데이터가 진짜 있는지 최종 확인
            if not rows or "데이터가" in rows[0].get_text():
                print("이 페이지에는 데이터가 없습니다.")
                break

            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 5: continue
                
                # 취소/취하된 데이터는 과감히 버립니다.
                if cols[4].get_text(strip=True): continue 

                product_name = cols[1].get_text(strip=True)
                # 상세 페이지로 가는 고유 키값 추출
                onclick_text = cols[1].find('a')['onclick']
                item_seq = onclick_text.split("'")[1]

                print(f"   -> DB 전송 대기: {product_name}")
                
                data = {
                    "item_seq": item_seq,
                    "product_name": product_name,
                    "company": cols[2].get_text(strip=True),
                    "approval_date": cols[3].get_text(strip=True),
                    "detail_url": f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
                }
                
                # 금고(Supabase)에 강제 저장 (upsert)
                supabase.table("drug_approvals").upsert(data).execute()
                total_saved += 1

            time.sleep(1) # 서버의 의심을 피하기 위한 짧은 휴식

        except Exception as e:
            print(f"⚠️ {page}페이지 요청 중 오류 발생: {e}")
            continue

    print(f"\n=== 🏆 작전 성공: 총 {total_saved}건이 Supabase 금고에 안착했습니다! ===")

if __name__ == "__main__":
    main()
