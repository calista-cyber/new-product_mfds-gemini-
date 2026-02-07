import time
import os
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from supabase import create_client, Client
import requests

# 1. Supabase 연결 설정
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")

if not URL or not KEY:
    print("Error: Supabase 환경변수가 설정되지 않았습니다.")
    exit(1)

supabase: Client = create_client(URL, KEY)

def get_detail_info(item_seq):
    """상세 페이지에서 위탁제조업체, 성분, 효능효과 추출"""
    detail_url = f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://nedrug.mfds.go.kr/pbp/CCBAE01'
    }
    try:
        res = requests.get(detail_url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        manufacturer = ""
        mf_tag = soup.find('th', string=lambda t: t and ('위탁' in t or '수탁' in t))
        if mf_tag: manufacturer = mf_tag.find_next('td').get_text(strip=True)

        ingredients = []
        ing_table = soup.select('div#scroll_02 table tbody tr')
        for tr in ing_table:
            tds = tr.find_all('td')
            if len(tds) > 1: ingredients.append(tds[1].get_text(strip=True))
        ingredients_str = ", ".join(ingredients[:5])

        efficacy = ""
        eff_div = soup.select_one('div#scroll_03')
        if eff_div: efficacy = eff_div.get_text(strip=True)[:300] 

        return manufacturer, ingredients_str, efficacy
    except:
        return "", "", ""

def main():
    print("=== 크롤링 시작 (션 팀장님 URL 타격 + 보안 통과 모드) ===")
    
    # [설정] 검색 기간: 2월 1일부터 오늘까지 (팀장님 제안 반영)
    s_start = "2026-02-01"
    s_end = datetime.now().strftime("%Y-%m-%d")
    
    current_page = 1
    total_saved = 0

    # 브라우저인 척 위장하는 세션 생성
    session = requests.Session()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://nedrug.mfds.go.kr/pbp/CCBAE01', # 나 여기서 왔어! 라고 말해주는 부분
        'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7'
    }

    while True:
        # 팀장님이 분석하신 URL 구조를 그대로 활용
        target_url = (
            f"https://nedrug.mfds.go.kr/pbp/CCBAE01/getItemPermitIntro?"
            f"page={current_page}&limit=&sort=&sortOrder=true&searchYn=true&"
            f"sDateGb=date&sYear=2026&sMonth=2&sWeek=2&"
            f"sPermitDateStart={s_start}&sPermitDateEnd={s_end}&btnSearch="
        )

        print(f"\n>> [ {current_page} 페이지 ] 접속 중...")
        try:
            res = session.get(target_url, headers=headers, timeout=15)
            soup = BeautifulSoup(res.text, 'html.parser')
            
            rows = soup.select('table.board_list tbody tr')
            
            # 종료 조건 확인
            if not rows or (len(rows) == 1 and "데이터가" in rows[0].get_text()):
                print("더 이상 데이터가 없습니다. (수집 종료)")
                break

            print(f"현재 페이지에서 {len(rows)}건을 확인합니다.")

            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 5: continue

                cancel_date = cols[4].get_text(strip=True)
                product_name = cols[1].get_text(strip=True)

                if cancel_date:
                    print(f"SKIP (취소됨): {product_name}")
                    continue

                try:
                    company = cols[2].get_text(strip=True)
                    approval_date = cols[3].get_text(strip=True)
                    
                    onclick_text = cols[1].find('a')['onclick']
                    item_seq = onclick_text.split("'")[1]
                    
                    # 중복 체크
                    exists = supabase.table("drug_approvals").select("item_seq").eq("item_seq", item_seq).execute()
                    if exists.data:
                        print(f"이미 있음: {product_name}")
                        continue

                    print(f" + 수집 시도: {product_name}")
                    manufacturer, ingredients, efficacy = get_detail_info(item_seq)

                    data = {
                        "item_seq": item_seq,
                        "product_name": product_name,
                        "company": company,
                        "manufacturer": manufacturer,
                        "ingredients": ingredients,
                        "efficacy": efficacy,
                        "approval_date": approval_date,
                        "detail_url": f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
                    }
                    
                    supabase.table("drug_approvals").upsert(data).execute()
                    total_saved += 1
                    time.sleep(0.1)

                except Exception as e:
                    print(f"처리 중 에러: {e}")
                    continue
            
            current_page += 1
            time.sleep(1) # 서버 예의 대기

        except Exception as e:
            print(f"페이지 접속 에러: {e}")
            break

    print(f"\n=== 최종 완료: 총 {total_saved}건 신규 저장됨 ===")

if __name__ == "__main__":
    main()
