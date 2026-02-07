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
    # 화면을 넉넉하게 설정 (요소 가림 방지)
    chrome_options.add_argument("--window-size=1920,1080")
    # 봇 탐지 회피용 헤더
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def get_detail_info(item_seq):
    """상세 페이지 정보 (requests 사용 - 속도 향상)"""
    detail_url = f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
    try:
        # 상세 페이지는 보안이 덜 까다로운 편이라 requests로 빠르게 시도
        res = requests.get(detail_url, headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 1. 위탁제조업체
        manufacturer = ""
        mf_tag = soup.find('th', string=lambda t: t and ('위탁' in t or '수탁' in t))
        if mf_tag: manufacturer = mf_tag.find_next('td').get_text(strip=True)

        # 2. 성분명 (최대 5개)
        ingredients = []
        ing_table = soup.select('div#scroll_02 table tbody tr')
        for tr in ing_table:
            tds = tr.find_all('td')
            if len(tds) > 1: ingredients.append(tds[1].get_text(strip=True))
        ingredients_str = ", ".join(ingredients[:5])

        # 3. 효능효과
        efficacy = ""
        eff_div = soup.select_one('div#scroll_03')
        if eff_div: efficacy = eff_div.get_text(strip=True)[:300] 

        return manufacturer, ingredients_str, efficacy
    except:
        return "", "", ""

def main():
    print("=== 크롤링 시작 (숫자 8자리 입력 모드) ===")
    
    driver = get_driver()
    wait = WebDriverWait(driver, 20)
    
    # 1. 사이트 접속
    base_url = "https://nedrug.mfds.go.kr/pbp/CCBAE01"
    print(f">> 사이트 접속 중: {base_url}")
    driver.get(base_url)
    
    # [핵심] 하이픈(-)을 뺀 순수 숫자 8자리 포맷 (YYYYMMDD)
    # 사이트가 자동으로 변환해주므로 숫자가 깔끔합니다.
    today = datetime.now()
    two_weeks_ago = today - timedelta(days=14)
    str_start = two_weeks_ago.strftime("%Y%m%d") # 예: 20260201
    str_end = today.strftime("%Y%m%d")           # 예: 20260215

    try:
        print(">> '일자검색' 모드 전환 시도...")
        
        # [1] '일자검색' 라벨을 찾아서 클릭
        # 화면상의 모든 라벨 중 '일자'라는 단어가 포함된 것을 찾습니다.
        labels = driver.find_elements(By.TAG_NAME, "label")
        clicked = False
        for label in labels:
            if "일자" in label.text:
                driver.execute_script("arguments[0].click();", label)
                clicked = True
                print(">> '일자검색' 버튼 클릭 성공")
                break
        
        if not clicked:
            print("⚠️ '일자검색' 버튼을 찾지 못했습니다. (기본 설정으로 진행)")

        # [2] 입력칸이 눈에 보일 때까지 대기 (Null 에러 방지)
        print(">> 입력칸 생성 대기 중...")
        start_input = wait.until(EC.visibility_of_element_located((By.ID, "startDate")))
        end_input = wait.until(EC.visibility_of_element_located((By.ID, "endDate")))
        
        # [3] 숫자만 입력 (send_keys)
        start_input.clear()
        start_input.send_keys(str_start)
        
        end_input.clear()
        end_input.send_keys(str_end)
        
        print(f">> 날짜 입력 완료 (숫자만): {str_start} ~ {str_end}")
        
        # [4] 엔터키로 검색 실행
        end_input.send_keys(Keys.RETURN)
        print(">> 검색 실행 (Enter)")
        
        # 결과 로딩 대기 (넉넉하게 5초)
        time.sleep(5)
        
    except Exception as e:
        print(f"⚠️ 검색 설정 과정 중 오류: {e}")
        # 오류가 나도 죽지 않고 진행 (혹시 데이터가 이미 나와있을 수도 있으니)

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
            # 취소일자 확인 (5번째 칸, 인덱스 4)
            cancel_date = cols[4].get_text(strip=True)
            product_name = cols[1].get_text(strip=True)
        except:
            continue

        # 취소된 약은 수집 제외
        if cancel_date:
            print(f"SKIP (취소됨): {product_name}")
            continue

        try:
            company = cols[2].get_text(strip=True)
            approval_date = cols[3].get_text(strip=True)
            
            # 상세 링크에서 고유번호(itemSeq) 추출
            onclick_text = cols[1].find('a')['onclick']
            # view('2023001', '...') 형태
            item_seq = onclick_text.split("'")[1]
            
            # 중복 체크 (DB에 이미 있으면 패스)
            exists = supabase.table("drug_approvals").select("item_seq").eq("item_seq", item_seq).execute()
            if exists.data:
                print(f"SKIP (이미 있음): {product_name}")
                continue

            print(f" + 수집 중: {product_name}")
            
            # 상세 정보 가져오기
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
