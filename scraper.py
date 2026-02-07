import time
import os
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from supabase import create_client, Client
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# 1. Supabase 연결 설정
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(URL, KEY)

def get_driver():
    """진짜 브라우저처럼 위장한 셀레니움 설정"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    # 봇 감지 회피용 헤더
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

def main():
    print("=== 🚨 션 팀장님 전용: 물리적 검색 버튼 타격 모드 시작 ===")
    driver = get_driver()
    wait = WebDriverWait(driver, 20)
    
    # [1] 정문으로 당당하게 입장 (보안 세션 획득)
    driver.get("https://nedrug.mfds.go.kr/pbp/CCBAE01")
    time.sleep(3)

    # [2] 날짜 설정 (2월 1일부터 오늘까지)
    s_start = "2026-02-01"
    s_end = datetime.now().strftime("%Y-%m-%d")

    try:
        # 일자검색 버튼 클릭
        date_radio = wait.until(EC.element_to_be_clickable((By.XPATH, "//label[contains(text(),'일자검색')]")))
        driver.execute_script("arguments[0].click();", date_radio)
        
        # 날짜 강제 주입
        driver.execute_script(f"document.getElementById('startDate').value = '{s_start}';")
        driver.execute_script(f"document.getElementById('endDate').value = '{s_end}';")
        print(f">> 날짜 설정 완료: {s_start} ~ {s_end}")

        # 검색 버튼 물리적 클릭
        search_btn = driver.find_element(By.CSS_SELECTOR, "button.btn.btn_search")
        driver.execute_script("arguments[0].click();", search_btn)
        print(">> 검색 실행 완료. 결과 로딩 중...")
        time.sleep(5)

        total_saved = 0
        
        # [3] 페이지 순회하며 강제 수집
        while True:
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            rows = soup.select('table.board_list tbody tr')

            if not rows or (len(rows) == 1 and "데이터가" in rows[0].get_text()):
                break

            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 5 or cols[4].get_text(strip=True): continue 

                product_name = cols[1].get_text(strip=True)
                item_seq = cols[1].find('a')['onclick'].split("'")[1]

                print(f"   -> DB 전송: {product_name}")
                data = {
                    "item_seq": item_seq,
                    "product_name": product_name,
                    "company": cols[2].get_text(strip=True),
                    "approval_date": cols[3].get_text(strip=True),
                    "detail_url": f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
                }
                
                # 중복 무시하고 일단 다 집어넣기
                supabase.table("drug_approvals").upsert(data).execute()
                total_saved += 1

            # 다음 페이지 버튼 클릭 시도
            try:
                next_btn = driver.find_element(By.XPATH, "//a[contains(@onclick, 'page_move') and text()='>']")
                driver.execute_script("arguments[0].click();", next_btn)
                time.sleep(3)
            except:
                break

        print(f"\n=== 🏆 복구 완료: 총 {total_saved}건이 Supabase 금고에 안착했습니다! ===")

    except Exception as e:
        print(f"❌ 에러 발생: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
