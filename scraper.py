import requests
from bs4 import BeautifulSoup
import os
from supabase import create_client, Client
from datetime import datetime, timedelta

# 1. Supabase 연결
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")

if not URL or not KEY:
    print("Error: Supabase 환경변수가 설정되지 않았습니다.")
    exit(1)

supabase: Client = create_client(URL, KEY)

def get_detail_info(item_seq):
    """상세 페이지에서 위탁제조업체, 성분, 효능효과 추출"""
    detail_url = f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
    try:
        res = requests.get(detail_url, headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 위탁제조업체 (제조/수입사 정보 찾기)
        manufacturer = ""
        # '위탁제조업체' 또는 '수탁자'라는 텍스트가 포함된 th 찾기
        mf_tag = soup.find('th', string=lambda t: t and ('위탁' in t or '수탁' in t))
        if mf_tag:
             manufacturer = mf_tag.find_next('td').get_text(strip=True)

        # 성분명
        ingredients = []
        ing_table = soup.select('div#scroll_02 table tbody tr')
        for tr in ing_table:
            tds = tr.find_all('td')
            if len(tds) > 1:
                ingredients.append(tds[1].get_text(strip=True))
        ingredients_str = ", ".join(ingredients[:5])

        # 효능효과
        efficacy = ""
        eff_div = soup.select_one('div#scroll_03')
        if eff_div:
            efficacy = eff_div.get_text(strip=True)[:300] # 300자 제한

        return manufacturer, ingredients_str, efficacy

    except Exception as e:
        print(f"상세 정보 파싱 중 에러 ({item_seq}): {e}")
        return "", "", ""

def main():
    print("=== 크롤링 시작 ===")
    
    # 최근 목록 조회
    list_url = "https://nedrug.mfds.go.kr/pbp/CCBAE01" 
    try:
        res = requests.get(list_url, headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(res.text, 'html.parser')
    except Exception as e:
        print(f"목록 페이지 접속 실패: {e}")
        return

    rows = soup.select('table.board_list tbody tr')
    print(f"총 {len(rows)}개의 행을 발견했습니다.")
    
    saved_count = 0

    for i, row in enumerate(rows):
        cols = row.find_all('td')
        if not cols or len(cols) < 5:
            continue

        # [디버깅] 첫 번째 줄의 데이터를 출력해봅니다 (컬럼 위치 확인용)
        if i == 0:
            print(f"첫 번째 행 데이터 샘플: {[c.get_text(strip=True) for c in cols]}")

        # [수정 포인트] 취소/취하 일자는 보통 7번째 칸 (인덱스 6)에 있습니다.
        # 인덱스 5는 '품목기준코드'라서 항상 값이 있습니다.
        cancel_date = ""
        if len(cols) > 6:
            cancel_date = cols[6].get_text(strip=True)
        
        product_name = cols[1].get_text(strip=True)

        if cancel_date:
            print(f"SKIP (취소됨): {product_name}")
            continue

        # 데이터 추출
        try:
            # 보통 Nedrug 목록: 0:순번, 1:품목명, 2:업체명, 3:허가유형, 4:허가일자, 5:코드, 6:취소일자
            
            # 정확한 매핑 (표 구조 기반)
            product_name = cols[1].get_text(strip=True)
            company = cols[2].get_text(strip=True)
            approval_type = cols[3].get_text(strip=True)
            approval_date = cols[4].get_text(strip=True)
            
            # itemSeq 추출
            onclick = cols[1].find('a')['onclick'] # view('2023...')
            item_seq = onclick.split("'")[1]
            
            detail_url = f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"

            # 중복 체크
            exists = supabase.table("drug_approvals").select("item_seq").eq("item_seq", item_seq).execute()
            if exists.data:
                print(f"SKIP (이미 있음): {product_name}")
                continue

            print(f">> 신규 데이터 수집 중: {product_name}...")
            
            manufacturer, ingredients, efficacy = get_detail_info(item_seq)

            data = {
                "item_seq": item_seq,
                "product_name": product_name,
                "company": company,
                "manufacturer": manufacturer,
                "category": "", # 목록에 없으면 빈값
                "approval_type": approval_type,
                "ingredients": ingredients,
                "efficacy": efficacy,
                "approval_date": approval_date,
                "detail_url": detail_url
            }

            supabase.table("drug_approvals").upsert(data).execute()
            saved_count += 1

        except Exception as e:
            print(f"데이터 처리 중 에러 ({product_name}): {e}")
            continue

    print(f"=== 크롤링 완료: 총 {saved_count}건 저장됨 ===")

if __name__ == "__main__":
    main()
