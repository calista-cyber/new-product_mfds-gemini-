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
from selenium.webdriver.common.action_chains import ActionChains  # [추가] 마우스 동작 모방
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
    chrome_options.add_argument("--window-size=1920,1080") # 화면 크게
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
    print("=== 크롤링 시작 (마우스 액션 모방 모드) ===")
    
    driver = get_driver()
    wait = WebDriverWait(driver, 20)
    actions = ActionChains(driver) # 마우스 동작 제어기
    
    # 1. 사이트 접속
    base_url = "https://nedrug.mfds.go.kr/pbp/CCBAE01"
    print(f">> 사이트 접속 중: {base_url}")
    driver.get(base_url)
    
    # 숫자 8자리 포맷 (YYYYMMDD) - 사이트 자동 변환용
    today = datetime.now()
    two_weeks_ago = today - timedelta(days=14)
    str_start = two_weeks_ago.strftime("%Y%m%d")
    str_end = today.strftime("%Y%m%d")

    try:
        print(">> '일자검색' 모드 전환 시도 (마우스 액션)...")
        
        # [1] '일자검색' 라벨 찾기 (가장 정확한 XPath)
        # 텍스트에 '일자검색' 또는 '일자'가 포함된 라벨을 찾습니다.
        target_label = wait.until(EC.element_to_be_clickable((By.XPATH, "//label[contains(text(), '일자')]")))
        
        # [2] 마우스 이동 후 진짜 클릭 (ActionChains 사용)
        actions.move_to_element(target_label).click().perform()
        print(">> 마우스로 '일자검색' 클릭 완료")
        
        # 혹시 클릭이 씹혔을 경우를 대비해 1초 후 확인 사살 (라디오버튼 직접 클릭)
        time.sleep(1)
        try:
            radio = driver.find_element(By.CSS_SELECTOR, "input[type='radio'][value='date']") # value가 date인지 확인 필요하나 보통 그렇습니다
            if not radio.is_selected():
                driver.execute_script("arguments[0].click();", radio)
                print(">> (보정) 라디오 버튼 강제 선택 완료")
        except:
            pass # 라벨 클릭이 성공했으면 이 부분은 에러나도 상관없음

        # [3] 입력칸이 나타날 때까지 확실히 대기
        print(">> 입력칸 활성화 대기 중...")
        start_input = wait.until(EC.visibility_of_element_located((By.ID, "startDate")))
        end_input = wait.until(EC.visibility_of_element_located((By.ID, "endDate")))
        
        # [4] 값 입력 (숫자 8자리)
        start_input.click() 
        start_input.clear()
        start_input.send_keys(str_start) # 20260201
        
        end_input.click()
        end_input.clear()
        end_input.send_keys(str_end) # 20260215
        
        print(f">> 날짜 입력 완료: {str_start} ~ {str_end}")
        
        # [5] 엔터키로 검색 실행
        end_input.send_keys(Keys.RETURN)
        print(">> 검색 실행 (Enter)")
        
        time.sleep(5) # 결과 로딩 대기
        
    except Exception as e:
        print(f"⚠️ 검색 설정 중 오류: {e}")
        # 오류가 나도 죽지 않고 현재 화면이라도 긁어오도록 진행

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
