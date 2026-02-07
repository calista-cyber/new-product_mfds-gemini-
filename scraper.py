import time
import os
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from supabase import create_client, Client

# 셀레니움(가짜 브라우저) 관련 라이브러리
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By

# 1. Supabase 연결
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")

if not URL or not KEY:
    print("Error: Supabase 환경변수 없음")
    exit(1)

supabase: Client = create_client(URL, KEY)

def get_driver():
    """헤드리스 크롬 브라우저 설정 및 실행"""
    chrome_options = Options()
    chrome_options.add_argument("--headless") # 화면 없이 실행
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    # 봇 탐지 방지용 헤더
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def get_detail_info(item_seq):
    """상세 페이지 정보 추출 (requests 사용 - 속도 위해)"""
    # 상세 페이지는 보안이 약할 수 있으므로 requests로 시도 (실패 시 빈값)
    detail_url = f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
    try:
        import requests
        res = requests.get(detail_url, headers={'User-Agent': 'Mozilla/5.0'})
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
    print("=== 크롤링 시작 (Selenium 헤드리스 브라우저) ===")
    
    # 브라우저 시동
    driver = get_driver()
    
    today = datetime.now()
    week_ago = today - timedelta(days=10) # 10일치
    str_start = week_ago.strftime("%Y-%m-%d")
    str_end = today.strftime("%Y-%m-%d")
    
    current_page = 1
    total_saved = 0
    
    while True:
        # URL에 검색 조건과 페이지 번호를 넣어 접속
        target_url = f"https://nedrug.mfds.go.kr/pbp/CCBAE01?searchYn=true&page={current_page}&searchType=screen&startDate={str_start}&endDate={str_end}"
        print(f"\n>> [ {current_page} 페이지 ] 브라우저 접속 중... ({str_start}~{str_end})")
        
        try:
            driver.get(target_url)
            # [중요] 자바스크립트가 표를 그릴 때까지 3초 대기
            time.sleep(3)
            
            # 브라우저가 현재 보고 있는 HTML 소스 가져오기
            page_source = driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')
            
        except Exception as e:
            print(f"브라우저 에러: {e}")
            break

        rows = soup.select('table.board_list tbody tr')
        
        # 종료 조건
        if not rows or (len(rows) == 1 and "데이터가" in rows[0].get_text()):
            print("더 이상 데이터가 없습니다.")
            break

        page_saved_count = 0
        for row in rows:
            cols = row.find_all('td')
            if len(cols) < 5: continue

            # [인덱스 확인] 0:순번, 1:제품명, 2:업체명, 3:허가일자, 4:취소일자, 5:전문/일반
            cancel_date = cols[4].get_text(strip=True)
            product_name = cols[1].get_text(strip=True)

            if cancel_date:
                print(f"SKIP (취소됨): {product_name}")
                continue

            try:
                company = cols[2].get_text(strip=True)
                approval_date = cols[3].get_text(strip=True)
                
                # onclick="return view('20231234',...)" 파싱
                onclick_text = cols[1].find('a')['onclick']
                item_seq = onclick_text.split("'")[1]
                
                # 중복 체크
                exists = supabase.table("drug_approvals").select("item_seq").eq("item_seq", item_seq).execute()
                if exists.data:
                    print(f"SKIP (이미 있음): {product_name}")
                    continue

                print(f" + 수집 중: {product_name}")
                
                # 상세 정보
                manufacturer, ingredients, efficacy = get_detail_info(item_seq)

                data = {
                    "item_seq": item_seq,
                    "product_name": product_name,
                    "company": company,
                    "manufacturer": manufacturer,
                    "approval_type": "",
                    "ingredients": ingredients,
                    "efficacy": efficacy,
                    "approval_date": approval_date,
                    "detail_url": f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
                }
                
                supabase.table("drug_approvals").upsert(data).execute()
                page_saved_count += 1
                total_saved += 1
                
            except Exception as e:
                print(f"에러: {e}")
                continue
        
        print(f"   -> {current_page}페이지 완료 ({page_saved_count}건 저장)")
        current_page += 1
        
        # 페이지 넘길 때도 브라우저 휴식
        time.sleep(1)

    driver.quit() # 브라우저 종료
    print(f"\n=== 최종 완료: 총 {total_saved}건 저장됨 ===")

if __name__ == "__main__":
    main()
