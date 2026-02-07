import time
import os
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from supabase import create_client, Client
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 1. Supabase 연결 설정
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")

if not URL or not KEY:
    print("Error: Supabase 환경변수가 없습니다.")
    exit(1)

supabase: Client = create_client(URL, KEY)

def get_detail_info(item_seq, session):
    """상세 페이지 데이터 추출 (재시도 로직 포함)"""
    detail_url = f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
    try:
        # 타임아웃을 30초로 늘려 안정성 확보
        res = session.get(detail_url, timeout=30)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 위탁제조업체 추출
        manufacturer = ""
        mf_tag = soup.find('th', string=lambda t: t and ('위탁' in t or '수탁' in t))
        if mf_tag: manufacturer = mf_tag.find_next('td').get_text(strip=True)

        # 성분명 추출
        ingredients = []
        ing_table = soup.select('div#scroll_02 table tbody tr')
        for tr in ing_table:
            tds = tr.find_all('td')
            if len(tds) > 1: ingredients.append(tds[1].get_text(strip=True))
        ingredients_str = ", ".join(ingredients[:5])

        # 효능효과 추출
        efficacy = ""
        eff_div = soup.select_one('div#scroll_03')
        if eff_div: efficacy = eff_div.get_text(strip=True)[:300] 

        return manufacturer, ingredients_str, efficacy
    except:
        return "", "", ""

def main():
    print("=== 크롤링 시작 (강철 멘탈 & 정밀 타격 모드) ===")
    
    # 끈질긴 재시도를 위한 세션 설정
    session = requests.Session()
    retry = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://nedrug.mfds.go.kr/pbp/CCBAE01'
    })

    # [설정] 팀장님 제안 기간: 2월 1일 ~ 오늘
    s_start = "2026-02-01"
    s_end = datetime.now().strftime("%Y-%m-%d")
    
    current_page = 1
    total_saved = 0

    while True:
        target_url = (
            f"https://nedrug.mfds.go.kr/pbp/CCBAE01/getItemPermitIntro?"
            f"page={current_page}&limit=&sort=&sortOrder=true&searchYn=true&"
            f"sDateGb=date&sYear=2026&sMonth=2&"
            f"sPermitDateStart={s_start}&sPermitDateEnd={s_end}&btnSearch="
        )

        print(f"\n>> [ {current_page} 페이지 ] 데이터 요청 중 (최대 30초 대기)...")
        try:
            # 타임아웃을 30초로 대폭 늘림
            res = session.get(target_url, timeout=30)
            soup = BeautifulSoup(res.text, 'html.parser')
            rows = soup.select('table.board_list tbody tr')

            if not rows or (len(rows) == 1 and "데이터가" in rows[0].get_text()):
                print("수집할 데이터가 더 이상 없습니다.")
                break

            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 5 or cols[4].get_text(strip=True): continue # 취소 건 제외

                product_name = cols[1].get_text(strip=True)
                item_seq = cols[1].find('a')['onclick'].split("'")[1]

                # 중복 체크
                exists = supabase.table("drug_approvals").select("item_seq").eq("item_seq", item_seq).execute()
                if exists.data:
                    print(f"이미 있음: {product_name}")
                    continue

                print(f" + 수집 시도: {product_name}")
                manufacturer, ingredients, efficacy = get_detail_info(item_seq, session)

                data = {
                    "item_seq": item_seq,
                    "product_name": product_name,
                    "company": cols[2].get_text(strip=True),
                    "manufacturer": manufacturer,
                    "ingredients": ingredients,
                    "efficacy": efficacy,
                    "approval_date": cols[3].get_text(strip=True),
                    "detail_url": f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
                }
                
                supabase.table("drug_approvals").upsert(data).execute()
                total_saved += 1
                time.sleep(0.5) # 서버 예의 대기

            current_page += 1
            time.sleep(2) # 페이지 간 충분한 휴식

        except Exception as e:
            print(f"⚠️ 연결 오류 발생 (무시하고 재시도): {e}")
            time.sleep(5)
            continue

    print(f"\n=== 최종 완료: 총 {total_saved}건 신규 저장됨 ===")

if __name__ == "__main__":
    main()
