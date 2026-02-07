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

def get_detail_info(session, item_seq):
    """상세 페이지 정보 추출 (세션 사용)"""
    detail_url = f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
    try:
        res = session.get(detail_url, headers={'User-Agent': 'Mozilla/5.0'})
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
    print("=== 크롤링 시작 (세션 모드) ===")
    
    base_url = "https://nedrug.mfds.go.kr/pbp/CCBAE01"
    
    # [핵심] 세션 객체 생성 (방문증 보관함)
    s = requests.Session()
    
    # 진짜 사람처럼 보이기 위한 헤더
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://nedrug.mfds.go.kr/pbp/CCBAE01',
        'Origin': 'https://nedrug.mfds.go.kr',
        'Host': 'nedrug.mfds.go.kr'
    }

    # 1. 먼저 사이트에 한번 접속해서 쿠키(방문증) 획득
    try:
        print(">> 사이트 접속 시도 (쿠키 획득)...")
        s.get(base_url, headers=headers, timeout=10)
    except Exception as e:
        print(f"초기 접속 실패: {e}")
        return

    # 날짜 계산 (오늘 ~ 10일 전까지 넉넉하게)
    today = datetime.now()
    week_ago = today - timedelta(days=10)
    
    current_page = 1
    total_saved = 0
    
    while True:
        print(f"\n>> [ {current_page} 페이지 ] 읽는 중... ({week_ago.strftime('%Y-%m-%d')} ~ {today.strftime('%Y-%m-%d')})")
        
        # 검색 조건 (Payload)
        payload = {
            "searchYn": "true",
            "page": current_page,
            "searchType": "", # 전체 검색
            "startDate": week_ago.strftime("%Y-%m-%d"),
            "endDate": today.strftime("%Y-%m-%d"),
            "order": "date" # 최신순 정렬
        }
        
        try:
            # [핵심] 그냥 requests.post가 아니라 s.post 사용 (쿠키 포함됨)
            res = s.post(base_url, data=payload, headers=headers, timeout=10)
            soup = BeautifulSoup(res.text, 'html.parser')
        except Exception as e:
            print(f"페이지 로딩 실패: {e}")
            break

        rows = soup.select('table.board_list tbody tr')
        
        # 결과가 없으면 종료
        if not rows or (len(rows) == 1 and "데이터가" in rows[0].get_text()):
            print("더 이상 데이터가 없습니다. (또는 검색 결과 없음)")
            # [디버깅] 만약 1페이지부터 데이터가 없으면 사이트 응답 내용을 일부 출력해봄
            if current_page == 1:
                print(">>> 사이트 응답 내용 일부(디버깅):")
                print(soup.get_text(strip=True)[:200])
            break

        page_saved_count = 0

        for row in rows:
            cols = row.find_all('td')
            if not cols or len(cols) < 5:
                continue

            # [수정 완료] 취소/취하일자는 5번째 칸 (인덱스 4)
            # 0:순번, 1:제품명, 2:업체명, 3:허가일자, 4:취소일자, 5:전문/일반
            cancel_date = cols[4].get_text(strip=True) 
            product_name = cols[1].get_text(strip=True)

            # 취소 날짜가 있으면 건너뛰기
            if cancel_date:
                print(f"SKIP (취소됨): {product_name}")
                continue

            try:
                company = cols[2].get_text(strip=True)
                approval_date = cols[3].get_text(strip=True)
                
                # 상세 링크 추출
                onclick = cols[1].find('a')['onclick'] 
                # view('20230001', '...') 형태 파싱
                item_seq = onclick.split("'")[1]
                detail_url = f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"

                # 중복 체크
                exists = supabase.table("drug_approvals").select("item_seq").eq("item_seq", item_seq).execute()
                if exists.data:
                    print(f"SKIP (이미 있음): {product_name}")
                    continue

                print(f" + 수집: {product_name}")
                
                # 상세 정보도 세션(s)을 이용해서 가져옴
                manufacturer, ingredients, efficacy = get_detail_info(s, item_seq)

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
                
                time.sleep(0.1)

            except Exception as e:
                print(f"에러 발생 ({product_name}): {e}")
                continue
        
        print(f"   -> {current_page}페이지 완료 ({page_saved_count}건 저장)")
        
        current_page += 1
        time.sleep(0.5)

    print(f"\n=== 최종 완료: 총 {total_saved}건 신규 저장됨 ===")

if __name__ == "__main__":
    main()
