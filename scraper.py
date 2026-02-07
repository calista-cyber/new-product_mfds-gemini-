import time
import os
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from supabase import create_client, Client
import requests

# 셀레니움 도구들
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# 1. Supabase 연결
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")

if not URL or not KEY:
    print("Error: Supabase 환경변수 없음")
    exit(1)

supabase: Client = create_client(URL, KEY)

def get_driver():
    """헤드리스 크롬 브라우저 설정"""
    chrome_options = Options()
    chrome_options.add_argument("--headless") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def get_detail_info(item_seq):
    """상세 페이지 정보 (requests 사용)"""
    detail_url = f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
    try:
        res = requests.get(detail_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
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
    print("=== 크롤링 시작 (션 팀장님 제안: URL 직접 타격 모드) ===")
    
    driver = get_driver()
    
    # 날짜 자동 계산 (오늘 기준 14일 전까지)
    today = datetime.now()
    start_dt = today - timedelta(days=14)
    
    s_year = start_dt.strftime("%Y")
    s_month = start_dt.strftime("%m").lstrip('0') # 02 -> 2
    s_start = start_dt.strftime("%Y-%m-%d")
    s_end = today.strftime("%Y-%m-%d")

    # [핵심] 제안해주신 URL 구조에 날짜 변수 대입
    # page=1 부터 시작하여 41건을 모두 보기 위해 순회 가능하도록 설정
    current_page = 1
    total_saved = 0

    while True:
        target_url = (
            f"https://nedrug.mfds.go.kr/pbp/CCBAE01/getItemPermitIntro?"
            f"page={current_page}&limit=&sort=&sortOrder=true&searchYn=true&garaInputBox=&"
            f"sDateGb=date&sYear={s_year}&sMonth={s_month}&sWeek=&"
            f"sPermitDateStart={s_start}&sPermitDateEnd={s_end}&"
            f"sItemName=&sEntpName=&btnSearch="
        )

        print(f"\n>> [ {current_page} 페이지 ] 접속 중...")
        driver.get(target_url)
        time.sleep(5) # 로딩 대기

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        rows = soup.select('table.board_list tbody tr')

        if not rows or (len(rows) == 1 and "데이터가" in rows[0].get_text()):
            print("더 이상 데이터가 없습니다.")
            break

        print(f"현재 페이지에서 {len(rows)}건 발견")

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
                
                # 제품 일련번호 추출
                onclick_text = cols[1].find('a')['onclick']
                item_seq = onclick_text.split("'")[1]
                
                # 중복 체크
                exists = supabase.table("drug_approvals").select("item_seq").eq("item_seq", item_seq).execute()
                if exists.data:
                    print(f"SKIP (이미 있음): {product_name}")
                    continue

                print(f" + 수집 중: {product_name}")
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
        
        # 다음 페이지로 (총 41건이므로 5페이지까지 자동으로 넘어감)
        current_page += 1
        if current_page > 10: # 안전장치: 너무 많이 넘어가는 것 방지
            break

    driver.quit()
    print(f"\n=== 최종 완료: 총 {total_saved}건 신규 저장됨 ===")

if __name__ == "__main__":
    main()
