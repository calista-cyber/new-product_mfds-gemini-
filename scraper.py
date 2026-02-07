import time
import os
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from supabase import create_client, Client
import requests

# 1. Supabase 연결 설정 (절대 건드리지 마세요!)
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(URL, KEY)

def get_detail_info(item_seq, session):
    """상세 페이지 데이터(성분, 효능 등) 강제 추출"""
    detail_url = f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
    try:
        # 타임아웃을 넉넉히 주어 끊김 방지
        res = session.get(detail_url, timeout=30)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 위탁제조업체 추출
        manufacturer = ""
        mf_tag = soup.find('th', string=lambda t: t and ('위탁' in t or '수탁' in t))
        if mf_tag: manufacturer = mf_tag.find_next('td').get_text(strip=True)

        # 성분명 추출
        ingredients = []
        ing_table = soup.select('div#scroll_02 table tbody tr')
        for tr in ing_table:
            tds = tr.find_all('td')
            if len(tds) > 1: ingredients.append(tds[1].get_text(strip=True))

        # 효능효과 추출
        efficacy = ""
        eff_div = soup.select_one('div#scroll_03')
        if eff_div: efficacy = eff_div.get_text(strip=True)[:300] 

        return manufacturer, ", ".join(ingredients[:5]), efficacy
    except:
        return "", "", ""

def main():
    print("=== 🚨 션 팀장님 제안: URL 정밀 타격 & 세션 위장 모드 ===")
    
    # 끈질긴 재시도를 위한 세션 설정
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://nedrug.mfds.go.kr/pbp/CCBAE01',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Connection': 'keep-alive'
    })

    # [단계 1] 세션 활성화를 위해 메인 페이지 한 번 들르기
    session.get("https://nedrug.mfds.go.kr/pbp/CCBAE01", timeout=15)
    time.sleep(2)

    # [설정] 2월 1일 ~ 오늘 (팀장님의 정밀 타격 기간)
    s_start = "2026-02-01"
    s_end = datetime.now().strftime("%Y-%m-%d")
    
    total_saved = 0

    # [단계 2] 1페이지부터 5페이지까지 끈질기게 수집
    for current_page in range(1, 6):
        target_url = (
            f"https://nedrug.mfds.go.kr/pbp/CCBAE01/getItemPermitIntro?"
            f"page={current_page}&limit=&sort=&sortOrder=true&searchYn=true&"
            f"sDateGb=date&sYear=2026&sMonth=2&"
            f"sPermitDateStart={s_start}&sPermitDateEnd={s_end}&btnSearch="
        )

        print(f"\n>> [ {current_page} 페이지 ] 데이터 침투 중...")
        try:
            res = session.get(target_url, timeout=30)
            soup = BeautifulSoup(res.text, 'html.parser')
            rows = soup.select('table.board_list tbody tr')

            if not rows or (len(rows) == 1 and "데이터가" in rows[0].get_text()):
                print("더 이상 데이터가 없습니다.")
                break

            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 5 or cols[4].get_text(strip=True): continue # 취소 건 제외

                product_name = cols[1].get_text(strip=True)
                item_seq = cols[1].find('a')['onclick'].split("'")[1]

                print(f"   -> DB 전송 대기: {product_name}")
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
                
                # 강제 저장 (upsert 사용)
                supabase.table("drug_approvals").upsert(data).execute()
                total_saved += 1
                time.sleep(0.5) # 서버 예의

        except Exception as e:
            print(f"⚠️ 연결 오류 발생: {e}")
            continue

    print(f"\n=== 🏆 임무 완수: 총 {total_saved}건이 Supabase 금고에 안착했습니다! ===")

if __name__ == "__main__":
    main()
