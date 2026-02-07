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
    """상세 페이지에서 위탁제조업체, 성분, 효능효과 추출"""
    detail_url = f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
    try:
        res = requests.get(detail_url, headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 위탁제조업체
        manufacturer = ""
        mf_tag = soup.find('th', string=lambda t: t and ('위탁' in t or '수탁' in t))
        if mf_tag:
             manufacturer = mf_tag.find_next('td').get_text(strip=True)

        # 성분명
        ingredients = []
        ing_table = soup.select('div#scroll_02 table tbody tr')
        for tr in ing_table:
            tds = tr.find_all('td')
            if len(tds) > 1:
                ingredients.append(tds[1].get_text(strip=True))
        ingredients_str = ", ".join(ingredients[:5])

        # 효능효과
        efficacy = ""
        eff_div = soup.select_one('div#scroll_03')
        if eff_div:
            efficacy = eff_div.get_text(strip=True)[:300] 

        return manufacturer, ingredients_str, efficacy

    except Exception as e:
        print(f"상세 정보 파싱 중 에러 ({item_seq}): {e}")
        return "", "", ""

def main():
    print("=== 크롤링 시작 (페이지 순회 모드) ===")
    
    url = "https://nedrug.mfds.go.kr/pbp/CCBAE01"
    
    # 오늘 날짜와 7일 전 날짜 계산
    today = datetime.now()
    week_ago = today - timedelta(days=7) # 일주일치 데이터 검색
    
    current_page = 1
    total_saved = 0
    
    while True:
        print(f"\n>> [ {current_page} 페이지 ] 읽는 중...")
        
        # 페이지 번호(page)를 포함하여 요청
        payload = {
            "searchYn": "true",
            "page": current_page, 
            "startDate": week_ago.strftime("%Y-%m-%d"),
            "endDate": today.strftime("%Y-%m-%d"),
        }
        
        try:
            res = requests.post(url, data=payload, headers={'User-Agent': 'Mozilla/5.0'})
            soup = BeautifulSoup(res.text, 'html.parser')
        except Exception as e:
            print(f"페이지 접속 실패: {e}")
            break

        # 테이블 행 가져오기
        rows = soup.select('table.board_list tbody tr')
        
        # [종료 조건] 데이터가 없거나, "데이터가 없습니다" 텍스트가 나오면 종료
        if not rows or (len(rows) == 1 and "데이터가" in rows[0].get_text()):
            print("더 이상 데이터가 없습니다. 크롤링을 종료합니다.")
            break

        page_saved_count = 0

        for row in rows:
            cols = row.find_all('td')
            if not cols or len(cols) < 5:
                continue

            # 취소/취하 일자 확인 (인덱스 6)
            cancel_date = cols[6].get_text(strip=True) if len(cols) > 6 else ""
            product_name = cols[1].get_text(strip=True)

            if cancel_date:
                print(f"SKIP (취소됨): {product_name}")
                continue

            try:
                # 데이터 추출
                company = cols[2].get_text(strip=True)
                approval_date = cols[3].get_text(strip=True)
                
                onclick = cols[1].find('a')['onclick'] 
                item_seq = onclick.split("'")[1]
                detail_url = f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"

                # 중복 체크
                exists = supabase.table("drug_approvals").select("item_seq").eq("item_seq", item_seq).execute()
                if exists.data:
                    print(f"SKIP (이미 있음): {product_name}")
                    continue

                print(f" + 수집: {product_name}")
                
                manufacturer, ingredients, efficacy = get_detail_info(item_seq)

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

                supabase.table("drug_approvals").upsert(data).execute()
                page_saved_count += 1
                total_saved += 1
                
                # 서버 부하 방지를 위해 아주 살짝 대기
                time.sleep(0.1)

            except Exception as e:
                print(f"에러 발생 ({product_name}): {e}")
                continue
        
        # 이번 페이지에서 저장한 게 없고 모두 중복/취소라면? (그래도 다음 페이지 확인 필요)
        print(f"   -> {current_page}페이지 완료 ({page_saved_count}건 저장)")
        
        # 다음 페이지로 이동
        current_page += 1
        time.sleep(0.5) # 페이지 넘길 때 대기

    print(f"\n=== 최종 완료: 총 {total_saved}건 신규 저장됨 ===")

if __name__ == "__main__":
    main()
