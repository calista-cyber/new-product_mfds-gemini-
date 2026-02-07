import time
import os
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from supabase import create_client, Client

# 셀레니움 필수 도구
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# 1. Supabase 연결
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(URL, KEY)

def get_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

def main():
    print("=== 크롤링 시작 (션 팀장님 URL 기반 물리적 타격 모드) ===")
    driver = get_driver()
    wait = WebDriverWait(driver, 20)
    
    # [1] 먼저 대문 페이지 접속 (보안 세션 획득)
    driver.get("https://nedrug.mfds.go.kr/pbp/CCBAE01")
    time.sleep(3)

    # [2] 션 팀장님이 분석하신 검색 조건 강제 주입
    # 2월 1일부터 오늘까지로 설정
    s_start = "2026-02-01"
    s_end = datetime.now().strftime("%Y-%m-%d")
    
    try:
        # '일자검색' 라디오 버튼 클릭
        date_radio = wait.until(EC.element_to_be_clickable((By.XPATH, "//label[contains(text(),'일자검색')]")))
        date_radio.click()
        
        # 날짜 직접 주입
        driver.execute_script(f"document.getElementById('startDate').value = '{s_start}';")
        driver.execute_script(f"document.getElementById('endDate').value = '{s_end}';")
        print(f">> 날짜 설정 완료: {s_start} ~ {s_end}")

        # [3] 검색 버튼 물리적 클릭 (돋보기 모양)
        search_btn = driver.find_element(By.CSS_SELECTOR, "button.btn.btn_search")
        driver.execute_script("arguments[0].click();", search_btn)
        print(">> 검색 실행 완료")
        time.sleep(5)

        # [4] 데이터 수집 및 페이지네이션
        total_saved = 0
        while True:
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            rows = soup.select('table.board_list tbody tr')
            
            if not rows or "데이터가" in rows[0].get_text(): break

            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 5 or cols[4].get_text(strip=True): continue # 취소 건 제외

                product_name = cols[1].get_text(strip=True)
                item_seq = cols[1].find('a')['onclick'].split("'")[1]

                # 중복 체크 후 저장
                exists = supabase.table("drug_approvals").select("item_seq").eq("item_seq", item_seq).execute()
                if not exists.data:
                    print(f" + 수집: {product_name}")
                    data = {
                        "item_seq": item_seq,
                        "product_name": product_name,
                        "company": cols[2].get_text(strip=True),
                        "approval_date": cols[3].get_text(strip=True),
                        "detail_url": f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
                    }
                    supabase.table("drug_approvals").upsert(data).execute()
                    total_saved += 1

            # 다음 페이지 버튼 클릭 (있을 경우)
            try:
                next_btn = driver.find_element(By.XPATH, "//a[contains(@onclick, 'page_move') and text()='>']")
                driver.execute_script("arguments[0].click();", next_btn)
                time.sleep(3)
            except: break

        print(f"\n=== 최종 완료: 총 {total_saved}건 저장됨 ===")
    finally:
        driver.quit()

if __name__ == "__main__": main()
