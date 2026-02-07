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
    print("=== 🚨 진짜 최종 데이터 복구 모드 시작 ===")
    driver = get_driver()
    
    # 2월 1일부터 오늘까지
    s_start = "2026-02-01"
    s_end = datetime.now().strftime("%Y-%m-%d")

    try:
        # [단계 1] 정문 접속 (세션 획득)
        driver.get("https://nedrug.mfds.go.kr/pbp/CCBAE01")
        time.sleep(3)

        # [단계 2] 팀장님이 제안하신 정밀 타격 URL로 세션 유지하며 이동
        target_url = (
            f"https://nedrug.mfds.go.kr/pbp/CCBAE01/getItemPermitIntro?"
            f"searchYn=true&sDateGb=date&sPermitDateStart={s_start}&sPermitDateEnd={s_end}&btnSearch="
        )
        driver.get(target_url)
        time.sleep(5)

        total_saved = 0
        
        # [단계 3] 1페이지부터 5페이지까지 훑기
        for page in range(1, 6):
            print(f">> {page}페이지 데이터 수집 중...")
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            rows = soup.select('table.board_list tbody tr')

            if not rows or "데이터가" in rows[0].get_text():
                break

            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 5 or cols[4].get_text(strip=True): continue 

                product_name = cols[1].get_text(strip=True)
                item_seq = cols[1].find('a')['onclick'].split("'")[1]

                print(f"   -> 수집: {product_name}")
                
                data = {
                    "item_seq": item_seq,
                    "product_name": product_name,
                    "company": cols[2].get_text(strip=True),
                    "approval_date": cols[3].get_text(strip=True),
                    "detail_url": f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
                }
                
                # 중복 체크 없이 일단 다 붓기!
                supabase.table("drug_approvals").upsert(data).execute()
                total_saved += 1

            # 다음 페이지로 이동
            try:
                next_page = page + 1
                driver.execute_script(f"page_move('{next_page}')")
                time.sleep(3)
            except:
                break

        print(f"\n=== 최종 성공: 총 {total_saved}건이 DB에 안착했습니다! ===")

    except Exception as e:
        print(f"❌ 에러 발생: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
