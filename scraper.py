import time
import os
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from supabase import create_client, Client

# 셀레니움 필수 도구들
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys # 엔터키 입력을 위해 필요

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
    # 봇 탐지 회피용 헤더
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def get_detail_info(item_seq):
    """상세 페이지 정보 (requests 사용)"""
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
    print("=== 크롤링 시작 (인간 행동 모방 모드) ===")
    
    driver = get_driver()
    
    # 1. 사이트 접속 (검색 결과 페이지가 아니라 메인 검색 페이지로 접속)
    base_url = "https://nedrug.mfds.go.kr/pbp/CCBAE01"
    print(f">> 사이트 접속 중: {base_url}")
    driver.get(base_url)
    time.sleep(5) # 로딩 대기
    
    # 2. 날짜 입력 및 검색 버튼 클릭 (이 부분이 핵심!)
    today = datetime.now()
    week_ago = today - timedelta(days=10) # 10일 전부터
    str_start = week_ago.strftime("%Y-%m-%d")
    str_end = today.strftime("%Y-%m-%d")
    
    try:
        # 화면의 날짜 입력칸(startDate, endDate)을 찾아서 강제로 날짜를 넣습니다.
        # (사이트가 캘린더를 띄워도 무시하고 값을 집어넣는 강력한 방식입니다)
        start_input = driver.find_element(By.ID, "startDate")
        end_input = driver.find_element(By.ID, "endDate")
        
        driver.execute_script(f"arguments[0].value = '{str_start}';", start_input)
        driver.execute_script(f"arguments[0].value = '{str_end}';", end_input)
        
        print(f">> 날짜 입력 완료: {str_start} ~ {str_end}")
        
        # 엔터키를 쳐서 검색 실행!
        end_input.send_keys(Keys.RETURN)
        print(">> 검색 실행 (Enter)")
        time.sleep(5) # 결과 뜰 때까지 대기
        
    except Exception as e:
        print(f"⚠️ 검색어 입력 실패 (기본 목록으로 시도합니다): {e}")

    # 3. 데이터 긁어오기 (페이지네이션은 일단 제외하고 1페이지 10건부터 확실하게!)
    # 브라우저가 현재 보고 있는 화면을 가져옴
    page_source = driver.page_source
    soup = BeautifulSoup(page_source, 'html.parser')
    
    rows = soup.select('table.board_list tbody tr')
    
    if not rows:
        print("!! 경고: 테이블을 찾지 못했습니다. (페이지 구조 변경 또는 로딩 실패)")
        # 디버깅을 위해 화면에 보이는 텍스트를 조금 출력해봄
        print("화면 텍스트 일부:", soup.get_text()[:200])
    else:
        print(f"총 {len(rows)}개의 행을 발견했습니다.")

    saved_count = 0
    for row in rows:
        cols = row.find_all('td')
        if len(cols) < 5: continue

        # [인덱스] 0:순번, 1:제품명, 2:업체명, 3:허가일자, 4:취소일자
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
                print(f"SKIP (이미 있음): {product_name}")
                continue

            print(f" + 수집 중: {product_name}")
            
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
            saved_count += 1
            
        except Exception as e:
            print(f"에러: {e}")
            continue
    
    driver.quit()
    print(f"\n=== 최종 완료: {saved_count}건 신규 저장됨 ===")

if __name__ == "__main__":
    main()
