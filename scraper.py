import os
import requests
import time
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from supabase import create_client, Client

# 1. Supabase 설정
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(URL, KEY)

def get_detail_info(item_seq, session):
    """상세 페이지 데이터 정밀 수집"""
    detail_url = f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
    try:
        # 타임아웃을 넉넉히 주어 연결 안정성 확보
        res = session.get(detail_url, timeout=30)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 위탁제조업체
        manufacturer = ""
        mf_tag = soup.find('th', string=lambda t: t and ('위탁' in t or '수탁' in t))
        if mf_tag: manufacturer = mf_tag.find_next('td').get_text(strip=True)

        # 성분명
        ingredients = []
        ing_table = soup.select('div#scroll_02 table tbody tr')
        for tr in ing_table:
            tds = tr.find_all('td')
            if len(tds) > 1: ingredients.append(tds[1].get_text(strip=True))

        # 효능효과
        efficacy = ""
        eff_div = soup.select_one('div#scroll_03')
        if eff_div: efficacy = eff_div.get_text(strip=True)[:300] 

        return manufacturer, ", ".join(ingredients[:5]), efficacy
    except:
        return "", "", ""

def main():
    print("=== 🚀 션 팀장님 제안: URL 직접 타격 최종 작전 시작 ===")
    
    # 세션 생성 (사람처럼 보이기 위한 헤더 설정)
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
        'Referer': 'https://nedrug.mfds.go.kr/pbp/CCBAE01',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8'
    })

    # 팀장님의 정밀 타격 기간: 2월 1일 ~ 오늘
    s_start = "2026-02-01"
    s_end = datetime.now().strftime("%Y-%m-%d")
    
    total_saved = 0

    # 41건을 모두 잡기 위해 1~5페이지 순회
    for page in range(1, 6):
        target_url = (
            f"https://nedrug.mfds.go.kr/pbp/CCBAE01/getItemPermitIntro?"
            f"page={page}&limit=&sort=&sortOrder=true&searchYn=true&"
            f"sDateGb=date&sYear=2026&sMonth=2&"
            f"sPermitDateStart={s_start}&sPermitDateEnd={s_end}&btnSearch="
        )

        print(f"\n>> [ {page} 페이지 ] 침투 중...")
        try:
            res = session.get(target_url, timeout=30)
            soup = BeautifulSoup(res.text, 'html.parser')
            rows = soup.select('table.board_list tbody tr')

            if not rows or (len(rows) == 1 and "데이터가" in rows[0].get_text()):
                print("더 이상 데이터가 없습니다.")
                break

            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 5 or cols[4].get_text(strip=True): continue 

                product_name = cols[1].get_text(strip=True)
                item_seq = cols[1].find('a')['onclick'].split("'")[1]

                print(f"   -> 발견: {product_name} (금고 이송 준비)")
                
                # 상세 정보 가져오기
                manufacturer, ingredients, efficacy = get_detail_info(item_seq, session)

                data = {
                    "item_seq": item_seq,
                    "product_name": product_name,
                    "company": cols[2].get_text(strip=True),
                    "manufacturer": manufacturer,
                    "ingredients": ingredients,
                    "efficacy": efficacy,
                    "approval_date": cols[3].get_text(strip=True),
                    "detail_url": f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
                }
                
                # [중요] 중복 체크 없이 Upsert로 강제 저장
                supabase.table("drug_approvals").upsert(data).execute()
                total_saved += 1
                time.sleep(0.3)

        except Exception as e:
            print(f"⚠️ {page}페이지 요청 중 실패: {e}")
            continue

    print(f"\n=== 🏆 작전 종료: 총 {total_saved}건이 Supabase 금고에 안착했습니다! ===")

if __name__ == "__main__":
    main()
