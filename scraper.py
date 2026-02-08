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
    [상세 수집] 제품명을 클릭했을 때 나오는 화면(CCBBB01)의 데이터를 긁어옵니다.
    """
    url = f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
    try:
        res = session.get(url, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 1. 위탁제조업체 (테이블 뒤지기)
        manufacturer = "자사제조" 
        tables = soup.select("table.view_table")
        for table in tables:
            if "제조소" in table.text:
                rows = table.select("tr")
                for row in rows:
                    if "위탁" in row.text or "수탁" in row.text:
                        # 위탁업체명이 있는 td를 찾아서 추출
                        manufacturer = row.select_one("td").text.strip()
                        break
        
        # 2. 성분명 (기본 개요 탭 등에서 추출 시도)
        ingredients = "상세성분 참조"
        # 성분은 보통 별도 탭이나 복잡한 구조라, 간단히 스킵하거나 메타데이터 활용
        
        # 3. 효능효과 (ID로 추출)
        efficacy = "상세 효능효과 참조"
        ee_data = soup.select_one("#ee_doc_data")
        if ee_data:
            efficacy = ee_data.text.strip()[:500] # 500자 요약

        return manufacturer, ingredients, efficacy

    except Exception:
        return "수집실패", "수집실패", "수집실패"

def main():
    print("=== 🌟 션 팀장님 전략: '유효 허가(취소X)' 의약품만 정밀 타격 ===")
    
    session = requests.Session()
    # 봇 차단 회피용 헤더
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Referer': 'https://nedrug.mfds.go.kr/pbp/CCBAE01'
    }
    
    # [1단계] 팀장님이 주신 '주간 검색' URL (2월 2주차)
    target_url = "https://nedrug.mfds.go.kr/pbp/CCBAE01/getItemPermitIntro"
    
    # 페이지 순회 (데이터가 많을 수 있으니 1~5페이지)
    for page in range(1, 6):
        print(f"\n>> [Web] {page}페이지 목록 검사 중...")
        
        # 파라미터 세팅 (팀장님 URL 기준)
        params = {
            'page': page,
            'limit': '10',
            'sort': 'itemPermitDate', # 허가일자순 정렬
            'sortOrder': 'true',      # 내림차순(최신순) 추정
            'searchYn': 'true',
            'sDateGb': 'week',        # 주간 검색
            'sYear': '2026',
            'sMonth': '2',
            'sWeek': '2',
            'sPermitDateStart': '2026-02-08',
            'sPermitDateEnd': '2026-02-14',
            'btnSearch': '검색'
        }

        try:
            # 목록 페이지 접속
            res = session.get(target_url, params=params, headers=headers, timeout=30)
            soup = BeautifulSoup(res.text, 'html.parser')
            rows = soup.select('table.board_list tbody tr')

            if not rows or "데이터가" in rows[0].text:
                print(">> 더 이상 데이터가 없습니다. (완료)")
                break

            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 8: continue # 컬럼 수 확인

                # 컬럼 매핑 (사이트 구조에 따라 인덱스 조정 필요)
                # 순번(0) / 제품명(1) / 업체명(2) / 허가일자(3) / 취소취하일자(4) ...
                product_name = cols[1].text.strip()
                company = cols[2].text.strip()
                approval_date = cols[3].text.strip()
                cancel_date = cols[4].text.strip() # 여기가 핵심!

                # [2단계] 필터링: '취소/취하일자'가 비어있어야 수집
                if cancel_date != "":
                    print(f"   -> [패스] {product_name} (취소됨: {cancel_date})")
                    continue
                
                # 유효한 약품만 진행
                try:
                    # onclick="goDetail('202612345');" 형태에서 ID 추출
                    item_seq = cols[1].find('a')['onclick'].split("'")[1]
                except:
                    continue

                print(f"   -> [수집] {product_name} ({approval_date}) - 상세 정보 긁는 중...")
                
                # [3단계] 상세 페이지 침투 (클릭 행동 모방)
                manufacturer, ingredients, efficacy = get_web_detail(session, item_seq)

                # [4단계] 리스트(표)에 반영
                data = {
                    "item_seq": item_seq,
                    "product_name": product_name,
                    "company": company,
                    "manufacturer": manufacturer, 
                    "category": "전문의약품" if "전문" in cols[5].text else "일반의약품", # 5,6번 컬럼 쯤에 구분 존재
                    "approval_type": "정상",
                    "ingredients": ingredients,
                    "efficacy": efficacy,
                    "approval_date": approval_date,
                    "detail_url": f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
                }
                
                supabase.table("drug_approvals").upsert(data).execute()
                time.sleep(random.uniform(0.5, 1.0)) # 봇 탐지 방지 텀

        except Exception as e:
            print(f"⚠️ 에러 발생: {e}")
            continue

    print(f"\n=== 🏆 작전 완료: 취소된 약은 버리고 알짜배기만 수집했습니다! ===")

if __name__ == "__main__":
    main()
