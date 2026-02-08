import os
import requests
import time
import math
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from supabase import create_client, Client

# 1. 설정
API_KEY = "2b03726584036b06c8c1c6b3d385a73be48f35cceac5444bcd6c611db5de7972"
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(URL, KEY)

# 웹 크롤링용 세션
session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Referer': 'https://nedrug.mfds.go.kr/'
})

def clean_text(text):
    if not text: return ""
    return " ".join(text.split())

def get_web_detail_parsing(item_seq):
    url = f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
    try:
        res = session.get(url, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 1. 허가심사유형
        approval_type = "정보없음"
        table_rows = soup.select("table tbody tr")
        for row in table_rows:
            th = row.select_one("th")
            if th and "허가심사유형" in th.text:
                td = row.select_one("td")
                if td: approval_type = clean_text(td.text)
                break
        
        # 2. 효능효과
        efficacy = "상세내용 참조"
        ee_tag = soup.select_one("#ee_doc_data")
        if not ee_tag:
            for row in table_rows:
                th = row.select_one("th")
                if th and "효능" in th.text:
                    ee_tag = row.select_one("td")
                    break
        if ee_tag:
            efficacy = clean_text(ee_tag.get_text(separator=" "))
            if len(efficacy) > 500: efficacy = efficacy[:500] + "..."

        return {'approval_type': approval_type, 'efficacy': efficacy}
    except:
        return None

def main():
    print("=== 🌟 션 팀장님 지시: 앱 호환성을 위해 컬럼명은 영어(efficacy)로 유지! ===")
    
    list_url = "http://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService07/getDrugPrdtPrmsnInq07"
    
    print(">> [정찰] 데이터 확인 중...")
    try:
        res = requests.get(list_url, params={'serviceKey': API_KEY, 'numOfRows': '1', 'type': 'xml'}, timeout=10)
        total_count = int(ET.fromstring(res.text).findtext('.//totalCount'))
        last_page = math.ceil(total_count / 100)
    except:
        return

    total_saved = 0
    scan_range = 200
    start_page = last_page
    end_page = max(1, last_page - scan_range)
    
    for page in range(start_page, end_page, -1):
        if page % 10 == 0:
            print(f">> [진행] {page}페이지... (현재 {total_saved}건)")
            
        try:
            params = {'serviceKey': API_KEY, 'pageNo': str(page), 'numOfRows': '100', 'type': 'xml'}
            res = requests.get(list_url, params=params, timeout=30)
            items = ET.fromstring(res.text).findall('.//item')
            if not items: continue

            for item in reversed(items):
                if item.findtext('CANCEL_DATE'): continue
                code = item.findtext('PRDLST_STDR_CODE') or ""
                if not code.startswith("2026"): continue 
                
                item_seq = item.findtext('ITEM_SEQ')
                real_date = (item.findtext('ITEM_PERMIT_DATE') or "").replace("-", "")

                if real_date >= "20260201":
                    web_detail = get_web_detail_parsing(item_seq) or {'approval_type': '확인불가', 'efficacy': '확인불가'}

                    print(f"   -> [💎저장] {item.findtext('ITEM_NAME')}")
                    
                    data = {
                        "item_seq": item_seq,
                        "product_name": item.findtext('ITEM_NAME'),
                        "company": item.findtext('ENTP_NAME'),
                        "category": item.findtext('SPCLTY_PBLC') or "구분없음",
                        "ingredients": item.findtext('MAIN_ITEM_INGR') or "정보없음",
                        
                        # [핵심 수정] 왼쪽(Key)은 영어, 오른쪽(Value)은 한글 데이터
                        "efficacy": web_detail['efficacy'],         
                        "approval_type": web_detail['approval_type'], 
                        
                        "approval_date": real_date,
                        "detail_url": f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
                    }
                    supabase.table("drug_approvals").upsert(data).execute()
                    total_saved += 1
                    time.sleep(0.5)
        except: continue

    print(f"\n=== 🏆 저장 완료: 앱이 좋아하는 영어 이름표로 잘 붙였습니다! ===")

if __name__ == "__main__":
    main()
