import requests
from bs4 import BeautifulSoup
import os
from supabase import create_client, Client
from datetime import datetime, timedelta
import time

# 1. Supabase 연결 설정
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")

if not URL or not KEY:
    print("Error: Supabase 환경변수가 설정되지 않았습니다.")
    exit(1)

supabase: Client = create_client(URL, KEY)

def get_detail_info(item_seq):
    """
    상세 페이지(링크)에 들어가서
    위탁제조업체, 성분명, 효능효과를 가져오는 함수
    """
    detail_url = f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
    try:
        # 사람인 척 하기 위한 헤더 설정
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        res = requests.get(detail_url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 1. 위탁제조업체 찾기
        manufacturer = ""
        mf_tag = soup.find('th', string=lambda t: t and ('위탁' in t or '수탁' in t))
        if mf_tag:
             manufacturer = mf_tag.find_next('td').get_text(strip=True)

        # 2. 성분명 찾기 (최대 5개까지만)
        ingredients = []
        ing_table = soup.select('div#scroll_02 table tbody tr')
        for tr in ing_table:
            tds = tr.find_all('td')
            if len(tds) > 1:
                ingredients.append(tds[1].get_text(strip=True))
        ingredients_str = ", ".join(ingredients[:5])

        # 3. 효능효과 찾기 (너무 길면 300자로 자름)
        efficacy = ""
        eff_div = soup.select_one('div#scroll_03')
        if eff_div:
            efficacy = eff_div.get_text(strip=True)[:300] 

        return manufacturer, ingredients_str, efficacy

    except Exception as e:
        print(f"상세 정보 파싱 중 에러 ({item_seq}): {e}")
        return "", "", ""

def main():
    print("=== 크롤링 시작 (주소창 입력 방식) ===")
    
    # 오늘 날짜와 10일 전 날짜 계산 (넉넉하게 검색)
    today = datetime.now()
    week_ago = today - timedelta(days=10)
    
    # 식약처 URL 형식에 맞게 날짜 변환 (YYYY-MM-DD)
    str_start = week_ago.strftime("%Y-%m-%d")
    str_end = today.strftime("%Y-%m-%d")
    
    current_page = 1
    total_saved = 0
    
    while True:
        # [핵심] 검색 버튼을 누르는 대신, 주소창에 조건을 직접 넣어서 접속합니다 (GET 방식)
        # 이렇게 하면 보안 봇 탐지를 우회할 확률이 높습니다.
        target_url = f"https://nedrug.mfds.go.kr/pbp/CCBAE01?searchYn=true&page={current_page}&searchType=screen&startDate={str_start}&endDate={str_end}"
        
        print(f"\n>> [ {current_page} 페이지 ] 읽는 중... ({str_start} ~ {str_end})")
        
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
            res = requests.get(target_url, headers=headers, timeout=15)
            soup = BeautifulSoup(res.text, 'html.parser')
        except Exception as e:
            print(f"페이지 접속 실패: {e}")
            break

        # 테이블 행 가져오기
        rows = soup.select('table.board_list tbody tr')
        
        # [종료 조건] 목록이 없거나 "데이터가 없습니다" 문구가 나오면 끝
        if not rows or (len(rows) == 1 and "데이터가" in rows[0].get_text()):
            print("더 이상 데이터가 없습니다. 크롤링을 종료합니다.")
            break

        page_saved_count = 0

        for row in rows:
            cols = row.find_all('td')
            # 칸 개수가 부족하면 제목줄이나 빈 줄이므로 패스
            if not cols or len(cols) < 5:
                continue

            # [중요 수정] 스크린샷 기준 '취소/취하일자'는 5번째 칸 (인덱스 4)
            # 순서: 0:순번, 1:제품명, 2:업체명, 3:허가일자, 4:취소일자, 5:전문/일반
            cancel_date = cols[4].get_text(strip=True) 
            product_name = cols[1].get_text(strip=True)

            # 취소 날짜가 적혀있으면(공백이 아니면) 건너뛰기
            if cancel_date:
                print(f"SKIP (취소됨/취하됨): {product_name}")
                continue

            try:
                company = cols[2].get_text(strip=True)
                approval_date = cols[3].get_text(strip=True)
                
                # 제품명 클릭 시 이동하는 링크(onclick)에서 고유코드(itemSeq) 추출
                # 예: view('20231234', '...') -> 20231234 추출
                onclick_text = cols[1].find('a')['onclick'] 
                item_seq = onclick_text.split("'")[1]
                
                detail_url = f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"

                # [중복 체크] 이미 저장된 약인지 확인
                exists = supabase.table("drug_approvals").select("item_seq").eq("item_seq", item_seq).execute()
                if exists.data:
                    print(f"SKIP (이미 저장됨): {product_name}")
                    continue

                print(f" + 수집 중: {product_name}")
                
                # 상세 페이지 들어가서 나머지 정보 가져오기
                manufacturer, ingredients, efficacy = get_detail_info(item_seq)

                # 저장할 데이터 뭉치 만들기
                data = {
                    "item_seq": item_seq,
                    "product_name": product_name,
                    "company": company,
                    "manufacturer": manufacturer,
                    "category": "", 
                    "approval_type": "",
                    "ingredients": ingredients,
                    "efficacy": efficacy,
                    "approval_date": approval_date,
                    "detail_url": detail_url
                }

                # Supabase에 저장 (upsert: 없으면 넣고, 있으면 업데이트)
                supabase.table("drug_approvals").upsert(data).execute()
                page_saved_count += 1
                total_saved += 1
                
                # 너무 빨리 긁으면 차단당할 수 있으니 0.1초 쉼
                time.sleep(0.1)

            except Exception as e:
                print(f"에러 발생 ({product_name}): {e}")
                continue
        
        print(f"   -> {current_page}페이지 완료 ({page_saved_count}건 저장)")
        
        # 다음 페이지로 이동
        current_page += 1
        time.sleep(0.5)

    print(f"\n=== 최종 완료: 총 {total_saved}건 신규 저장됨 ===")

if __name__ == "__main__":
    main()
