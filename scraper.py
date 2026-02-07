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
    print("=== 크롤링 시작 (물리적 클릭 + 41건 전수 조사) ===")
    driver = get_driver()
    wait = WebDriverWait(driver, 20)
    
    # [1] 사이트 접속
    driver.get("https://nedrug.mfds.go.kr/pbp/CCBAE01")
    time.sleep(3)

    # [2] 션 팀장님 제안 날짜 설정 (2월 1일부터 오늘까지)
    s_start = "2026-02-01"
    s_end = datetime.now().strftime("%Y-%m-%d")
    
    try:
        # '일자검색' 버튼 클릭
        date_radio = wait.until(EC.element_to_be_clickable((By.XPATH, "//label[contains(text(),'일자검색')]")))
        driver.execute_script("arguments[0].click();", date_radio)
        
        # 날짜 직접 입력
        driver.execute_script(f"document.getElementById('startDate').value = '{s_start}';")
        driver.execute_script(f"document.getElementById('endDate').value = '{s_end}';")
        print(f">> 날짜 설정 완료: {s_start} ~ {s_end}")

        # 검색 버튼(돋보기) 클릭
        search_btn = driver.find_element(By.CSS_SELECTOR, "button.btn.btn_search")
        driver.execute_script("arguments[0].click();", search_btn)
        print(">> 검색 실행 완료")
        time.sleep(5)

        # [3] 페이지 순회 및 데이터 수집
        total_saved = 0
        current_page = 1
        
        while True:
            print(f"\n>> [ {current_page} 페이지 ] 처리 중...")
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            rows = soup.select('table.board_list tbody tr')
            
            if not rows or "데이터가" in rows[0].get_text():
                print("수집할 데이터가 없습니다.")
                break

            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 5 or cols[4].get_text(strip=True): 
                    continue # 취소 건 제외

                product_name = cols[1].get_text(strip=True)
                item_seq = cols[1].find('a')['onclick'].split("'")[1]

                # 중복 체크 후 저장
                exists = supabase.table("drug_approvals").select("item_seq").eq("item_seq", item_seq).execute()
                if not exists.data:
                    print(f" + 신규 수집: {product_name}")
                    data = {
                        "item_seq": item_seq,
                        "product_name": product_name,
                        "company": cols[2].get_text(strip=True),
                        "approval_date": cols[3].get_text(strip=True),
                        "detail_url": f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
                    }
                    supabase.table("drug_approvals").upsert(data).execute()
                    total_saved += 1

            # [4] 다음 페이지 버튼 클릭 (번호 기반)
            current_page += 1
            try:
                # 다음 페이지 번호(예: 2, 3, 4, 5) 링크를 찾아 클릭
                next_page_link = driver.find_element(By.XPATH, f"//div[@class='paging']//a[text()='{current_page}']")
                driver.execute_script("arguments[0].click();", next_page_link)
                time.sleep(3)
            except:
                print("더 이상 넘길 페이지가 없습니다.")
                break

        print(f"\n=== 최종 완료: 총 {total_saved}건 저장됨 ===")
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
