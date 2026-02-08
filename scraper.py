import os
import requests
import time
import random
from bs4 import BeautifulSoup
from supabase import create_client, Client

# 1. 설정
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(URL, KEY)

def get_web_detail(session, item_seq):
    """
    [상세 수집] 제품명 클릭 시 이동하는 상세 페이지(CCBBB01) 데이터 수집
    """
    url = f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
    try:
        res = session.get(url, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 1. 위탁제조업체 (테이블 스캔)
        manufacturer = "자사제조" 
        tables = soup.select("table.view_table")
        for table in tables:
            if "제조소" in table.text:
                rows = table.select("tr")
                for row in rows:
                    if "위탁" in row.text or "수탁" in row.text:
                        manufacturer = row.select_one("td").text.strip()
                        break
        
        # 2. 성분명
        ingredients = "상세성분 참조"
        
        # 3. 효능효과 (ID로 추출)
        efficacy = "상세 효능효과 참조"
        ee_data = soup.select_one("#ee_doc_data")
        if ee_data:
            efficacy = ee_data.text.strip()[:500]

        return manufacturer, ingredients, efficacy

    except Exception:
        return "수집실패", "수집실패", "수집실패"

def main():
    print("=== 🧪 션 팀장님 테스트: '2월 1주차(데이터 유)' 검증 시작 ===")
    
    session = requests.Session()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Referer': 'https://nedrug.mfds.go.kr/pbp/CCBAE01'
    }
    
    target_url = "https://nedrug.mfds.go.kr/pbp/CCBAE01/getItemPermitIntro"
    
    # 1주차는 데이터가 43건이므로 1~5페이지면 충분
    total_saved = 0
    
    for page in range(1, 6):
        print(f"\n>> [Web] {page}페이지 스캔 중 (기간: 2/1 ~ 2/7)...")
        
        # [핵심] 2월 1주차로 타겟 변경
        params = {
            'page': page,
            'limit': '10',
            'sort': 'itemPermitDate',
            'sortOrder': 'true',
            'searchYn': 'true',
            'sDateGb': 'date', # 정확한 날짜 지정을 위해 date 모드 사용
            'sYear': '2026',
            'sMonth': '2',
            'sWeek': '1',
            'sPermitDateStart': '2026-02-01', # 시작일 (1주차)
            'sPermitDateEnd': '2026-02-07',   # 종료일 (1주차)
            'btnSearch': '검색'
        }

        try:
            res = session.get(target_url, params=params, headers=headers, timeout=30)
            soup = BeautifulSoup(res.text, 'html.parser')
            rows = soup.select('table.board_list tbody tr')

            if not rows or "데이터가" in rows[0].text:
                print(">> 더 이상 데이터가 없습니다.")
                break

            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 8: continue

                # 웹사이트 컬럼 인덱스 (변동 가능성 있으나 보통 이 순서)
                # 0:번호, 1:제품명, 2:업체명, 3:허가일, 4:취소일, 5:상태, 6:구분...
                product_name = cols[1].text.strip()
                company = cols[2].text.strip()
                approval_date = cols[3].text.strip()
                cancel_date = cols[4].text.strip() 

                # [필터링] 취소일자가 있으면(값이 비어있지 않으면) 패스
                if cancel_date:
                    print(f"   -> [거름] {product_name} (취소됨: {cancel_date})")
                    continue
                
                try:
                    item_seq = cols[1].find('a')['onclick'].split("'")[1]
                except:
                    continue

                print(f"   -> [수집] {product_name} ({approval_date})")
                
                # 상세 정보 긁어오기
                manufacturer, ingredients, efficacy = get_web_detail(session, item_seq)

                data = {
                    "item_seq": item_seq,
                    "product_name": product_name,
                    "company": company,
                    "manufacturer": manufacturer, 
                    "category": "전문의약품" if "전문" in row.text else "일반의약품",
                    "approval_type": "정상",
                    "ingredients": ingredients,
                    "efficacy": efficacy,
                    "approval_date": approval_date,
                    "detail_url": f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
                }
                
                supabase.table("drug_approvals").upsert(data).execute()
                total_saved += 1
                time.sleep(random.uniform(0.5, 1.0))

        except Exception as e:
            print(f"⚠️ 에러: {e}")
            continue

    print(f"\n=== 🏆 검증 완료: 1주차 데이터 총 {total_saved}건 수집됨 ===")

if __name__ == "__main__":
    main()
