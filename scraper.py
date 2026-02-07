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
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

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
    print("=== 크롤링 시작 (클릭 강화 + 숫자 8자리 입력) ===")
    
    driver = get_driver()
    wait = WebDriverWait(driver, 20)
    
    # 1. 사이트 접속
    base_url = "https://nedrug.mfds.go.kr/pbp/CCBAE01"
    print(f">> 사이트 접속 중: {base_url}")
    driver.get(base_url)
    
    # 숫자 8자리 포맷 (YYYYMMDD)
    today = datetime.now()
    two_weeks_ago = today - timedelta(days=14)
    str_start = two_weeks_ago.strftime("%Y%m%d")
    str_end = today.strftime("%Y%m%d")

    try:
        print(">> '일자검색' 모드 전환 시도...")
        
        # [1] '일자검색' 라벨을 XPath로 정확하게 찾아서 클릭 (가장 확실한 방법)
        try:
            # 텍스트가 '일자검색'인 라벨 찾기
            date_label = wait.until(EC.element_to_be_clickable((By.XPATH, "//label[contains(text(), '일자검색')]")))
            date_label.click()
            print(">> '일자검색' 라벨 클릭 완료 (방법 1)")
        except:
            # 실패 시 라디오 버튼(input)을 직접 찾아서 클릭 시도
            print(">> 라벨 클릭 실패, 라디오 버튼 직접 클릭 시도...")
            radio_btn = driver.find_element(By.CSS_SELECTOR, "input[value='date']") # value가 date인 경우가 많음
            driver.execute_script("arguments[0].click();", radio_btn)
            print(">> '일자검색' 라디오 버튼 강제 클릭 완료 (방법 2)")
        
        # [2] 입력칸이 나타날 때까지 확실히 대기
        print(">> 입력칸 활성화 대기 중...")
        start_input = wait.until(EC.visibility_of_element_located((By.ID, "startDate")))
        end_input = wait.until(EC.visibility_of_element_located((By.ID, "endDate")))
        
        # [3] 기존 값 지우고 숫자만 입력
        start_input.click() # 포커스 주기
        start_input.clear()
        start_input.send_keys(str_start) # 예: 20260201
        
        end_input.click()
        end_input.clear()
        end_input.send_keys(str_end) # 예: 20260215
        
        print(f">> 날짜 입력 완료: {str_start} ~ {str_end}")
        
        # [4] 검색 실행 (엔터키)
        end_input.send_keys(Keys.RETURN)
        print(">> 검색 실행 (Enter)")
        
        time.sleep(5) # 결과 로딩 대기
        
    except Exception as e:
        print(f"⚠️ 검색 설정 중 오류 (진행 불가 시 현재 화면 캡쳐 추천): {e}")

    # 2. 데이터 수집
    page_source = driver.page_source
    soup = BeautifulSoup(page_source, 'html.parser')
    
    rows = soup.select('table.board_list tbody tr')
    
    if not rows:
        print("!! 경고: 테이블을 찾을 수 없습니다.")
    elif len(rows) == 1 and "데이터가" in rows[0].get_text():
        print("검색 결과가 없습니다 (0건).")
    else:
        print(f"총 {len(rows)}개의 행을 발견했습니다.")

    saved_count = 0
    for row in rows:
        cols = row.find_all('td')
        if len(cols) < 5: continue

        try:
            cancel_date = cols[4].get_text(strip=True)
            product_name = cols[1].get_text(strip=True)
        except:
            continue

        if cancel_date:
            print(f"SKIP (취소됨): {product_name}")
            continue

        try:
            company = cols[2].get_text(strip=True)
            approval_date = cols[3].get_text(strip=True)
            
            onclick_text = cols[1].find('a')['onclick']
            item_seq = onclick_text.split("'")[1]
            
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
                "detail_url": f"https://
