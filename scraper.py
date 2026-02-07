import requests
from bs4 import BeautifulSoup
import os
from supabase import create_client, Client
from datetime import datetime, timedelta

# 1. Supabase 연결 설정 (환경변수에서 가져옴)
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(URL, KEY)

def get_detail_info(item_seq):
    """상세 페이지에서 위탁제조업체, 성분, 효능효과 추출"""
    detail_url = f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
    try:
        res = requests.get(detail_url, headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # (실제 사이트 구조에 따라 선택자는 조정 필요할 수 있음)
        # 예시 로직: 텍스트를 포함하는 요소를 찾아 추출
        
        # 위탁제조업체 (보통 제조/수입사 정보 탭이나 테이블에 위치)
        manufacturer = "정보없음"
        mf_tag = soup.find('th', string=lambda t: t and '제조업체' in t) # 예시
        if mf_tag:
             manufacturer = mf_tag.find_next('td').get_text(strip=True)

        # 성분명 (원료약품 및 분량)
        ingredients = []
        # 간단하게 원료명 텍스트만 추출 (정교한 파싱은 HTML 구조 분석 필요)
        ing_table = soup.select('div#scroll_02 table tbody tr')
        for tr in ing_table:
            tds = tr.find_all('td')
            if len(tds) > 1:
                ingredients.append(tds[1].get_text(strip=True)) # 2번째 칸이 성분명이라 가정
        ingredients_str = ", ".join(ingredients[:5]) # 너무 기니까 5개만

        # 효능효과
        efficacy = ""
        eff_div = soup.select_one('div#scroll_03') # 효능효과 섹션 ID
        if eff_div:
            efficacy = eff_div.get_text(strip=True)[:200] + "..." # 200자 제한

        return manufacturer, ingredients_str, efficacy

    except Exception as e:
        print(f"Error parsing detail {item_seq}: {e}")
        return "", "", ""

def main():
    print("크롤링 시작...")
    
    # 최근 허가 목록 페이지 접근 (최근 1주일 데이터 가정)
    # 실제로는 POST로 날짜 범위를 보내거나, 1페이지를 긁습니다.
    list_url = "https://nedrug.mfds.go.kr/pbp/CCBAE01" 
    
    # 폼 데이터 예시 (필요시 날짜 지정)
    # data = {'startDate': '...', 'endDate': '...'} 
    # res = requests.post(list_url, data=data) 
    
    res = requests.get(list_url) # 단순 1페이지 조회
    soup = BeautifulSoup(res.text, 'html.parser')
    
    rows = soup.select('table.board_list tbody tr')
    
    for row in rows:
        cols = row.find_all('td')
        if not cols or len(cols) < 10: continue

        # [필터링 1] 취소/취하 일자가 비어있지 않으면(값이 있으면) 건너뜀
        cancel_date = cols[5].get_text(strip=True) # *인덱스 확인 필요
        if cancel_date:
            continue

        # 기본 정보 추출
        approval_date = cols[0].get_text(strip=True)
        product_name = cols[1].get_text(strip=True)
        company = cols[2].get_text(strip=True)
        approval_type = cols[4].get_text(strip=True)
        category = cols[6].get_text(strip=True) # 전문/일반 등

        # itemSeq 추출 (상세페이지 링크용)
        # onclick="view('202301234')" 형태에서 숫자 추출
        onclick = cols[1].find('a')['onclick']
        item_seq = onclick.split("'")[1]
        
        detail_url = f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"

        # [필터링 2] 이미 DB에 있는 item_seq면 건너뜀 (중복 방지)
        # (Supabase upsert를 써도 되지만, 상세페이지 크롤링 부하를 줄이기 위해 체크)
        exists = supabase.table("drug_approvals").select("item_seq").eq("item_seq", item_seq).execute()
        if exists.data:
            print(f"이미 존재함: {product_name}")
            continue

        print(f"신규 발견! 상세 정보 수집 중: {product_name}")
        
        # 상세 정보 긁어오기 (함수 호출)
        manufacturer, ingredients, efficacy = get_detail_info(item_seq)

        # 데이터 정리
        data = {
            "item_seq": item_seq,
            "product_name": product_name,
            "company": company,
            "manufacturer": manufacturer,
            "category": category,
            "approval_type": approval_type,
            "ingredients": ingredients,
            "efficacy": efficacy,
            "approval_date": approval_date,
            "detail_url": detail_url
        }

        # Supabase에 저장
        supabase.table("drug_approvals").upsert(data).execute()

    print("크롤링 완료!")

if __name__ == "__main__":
    main()