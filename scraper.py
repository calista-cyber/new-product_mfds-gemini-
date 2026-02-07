import time
import os
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from supabase import create_client, Client

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
    # 화면을 크게 설정 (버튼 가림 방지)
    chrome_options.add_argument("--window-size=1920,1080")
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
    print("=== 크롤링 시작 (일자검색 강제 전환 모드) ===")
    
    driver = get_driver()
    wait = WebDriverWait(driver, 20)
    
    # 1. 사이트 접속
    base_url = "https://nedrug.mfds.go.kr/pbp/CCBAE01"
    print(f">> 사이트 접속 중: {base_url}")
    driver.get(base_url)
    time.sleep(3) # 접속 대기
    
    # 날짜 계산 (오늘 기준 14일 전까지)
    today = datetime.now()
    two_weeks_ago = today - timedelta(days=14)
    str_start = two_weeks_ago.strftime("%Y-%m-%d")
    str_end = today.strftime("%Y-%m-%d")

    try:
        print(">> '일자검색' 모드로 전환 시도...")
        
        # [핵심 변경] 모든 라벨(label) 태그를 가져와서 '일자' 글씨가 있는 걸 찾아 클릭합니다.
        # XPath보다 훨씬 유연하고 확실한 방법입니다.
        labels = driver.find_elements(By.TAG_NAME, "label")
        clicked = False
        for label in labels:
            if "일자" in label.text:
                driver.execute_script("arguments[0].click();", label)
                print(">> '일자검색' 버튼 클릭 성공!")
                clicked = True
                break
        
        if not clicked:
            print("⚠️ '일자검색' 버튼을 못 찾았습니다. (기본 모드로 진행)")

        # 클릭 후 입력칸이 생길 때까지 2초 대기
        time.sleep(2)

        # [단계 2] 이제 입력칸이 생겼으므로 날짜 주입 (더 이상 null 에러 안 남!)
        driver.execute_script(f"document.getElementById('startDate').value = '{str_start}';")
        driver.execute_script(f"document.getElementById('endDate').value = '{str_end}';")
        print(f">> 날짜 입력 완료: {str_start} ~ {str_end}")
        
        # [단계 3] '종료일' 입력칸에서 엔터키(RETURN) 입력
        end_date_input = driver.find_element(By.ID, "endDate")
        end_date_input.send_keys(Keys.RETURN)
        print(">> 엔터키 입력 완료 (검색 실행)")
        
        # 결과 로딩 대기
        time.sleep(5)
        
    except Exception as e:
        print(f"⚠️ 검색 설정 중 오류 발생: {e}")
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
            # 취소일자 확인 (5번째 칸)
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
