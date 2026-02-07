import time
import os
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from supabase import create_client, Client
import requests

# 1. Supabase 연결 (환경변수 확인 필수!)
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(URL, KEY)

def get_detail_info(item_seq):
    """상세 데이터 추출"""
    detail_url = f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(detail_url, headers=headers, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        manufacturer = ""
        mf_tag = soup.find('th', string=lambda t: t and ('위탁' in t or '수탁' in t))
        if mf_tag: manufacturer = mf_tag.find_next('td').get_text(strip=True)

        ingredients = []
        ing_table = soup.select('div#scroll_02 table tbody tr')
        for tr in ing_table:
            tds = tr.find_all('td')
            if len(tds) > 1: ingredients.append(tds[1].get_text(strip=True))
        
        efficacy = ""
        eff_div = soup.select_one('div#scroll_03')
        if eff_div: efficacy = eff_div.get_text(strip=True)[:300] 

        return manufacturer, ", ".join(ingredients[:5]), efficacy
    except:
        return "", "", ""

def main():
    print("=== 🚨 긴급 데이터 복구 모드 시작 ===")
    
    # 2월 1일부터 오늘까지 정밀 타격
    s_start = "2026-02-01"
    s_end = datetime.now().strftime("%Y-%m-%d")
    
    current_page = 1
    total_saved = 0
    headers = {
        'User-Agent': 'Mozilla/5.0',
        'Referer': 'https://nedrug.mfds.go.kr/pbp/CCBAE01'
    }

    while current_page <= 5: # 41건을 잡기 위해 5페이지까지 강제 순회
        target_url = (
            f"https://nedrug.mfds.go.kr/pbp/CCBAE01/getItemPermitIntro?"
            f"page={current_page}&limit=&sort=&sortOrder=true&searchYn=true&"
            f"sDateGb=date&sYear=2026&sMonth=2&"
            f"sPermitDateStart={s_start}&sPermitDateEnd={s_end}&btnSearch="
        )

        print(f"\n>> [ {current_page} 페이지 ] 데이터 강제 인계 중...")
        try:
            res = requests.get(target_url, headers=headers, timeout=20)
            soup = BeautifulSoup(res.text, 'html.parser')
            rows = soup.select('table.board_list tbody tr')

            if not rows or "데이터가" in rows[0].get_text():
                break

            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 5 or cols[4].get_text(strip=True): continue 

                product_name = cols[1].get_text(strip=True)
                item_seq = cols[1].find('a')['onclick'].split("'")[1]

                print(f" -> DB 전송: {product_name}")
                manufacturer, ingredients, efficacy = get_detail_info(item_seq)

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
                
                # 강제 저장 (upsert)
                supabase.table("drug_approvals").upsert(data).execute()
                total_saved += 1
                time.sleep(0.2)

            current_page += 1
            time.sleep(1)

        except Exception as e:
            print(f"오류: {e}")
            break

    print(f"\n=== 복구 완료: 총 {total_saved}건이 DB에 안착했습니다! ===")

if __name__ == "__main__":
    main()
