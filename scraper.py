import os
import requests
import time
import math
import xml.etree.ElementTree as ET
from supabase import create_client, Client

# 1. 설정
API_KEY = "2b03726584036b06c8c1c6b3d385a73be48f35cceac5444bcd6c611db5de7972"
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(URL, KEY)

def get_api_date_and_ingr(item_seq):
    """ 
    [상세 API] 
    불필요한 정보(효능, 제조원)는 버리고,
    가장 중요한 '진짜 허가일자'와 '성분'만 빠르게 가져옵니다.
    """
    url = "http://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService07/getDrugPrdtPrmsnDtlInq06"
    params = {'serviceKey': API_KEY, 'item_seq': item_seq, 'numOfRows': '1', 'type': 'xml'}
    
    try:
        res = requests.get(url, params=params, timeout=10)
        root = ET.fromstring(res.text)
        item = root.find('.//item')
        
        if not item: return None

        return {
            'date': item.findtext('ITEM_PERMIT_DATE') or item.findtext('PERMIT_DATE'),
            'ingr': item.findtext('MAIN_ITEM_INGR') or item.findtext('ITEM_INGR_NAME') or "정보없음"
        }
    except:
        return None

def main():
    print("=== 🌟 션 팀장님 최종 승인: 2026년 2월 신약 17건 확보 (경량화 버전) ===")
    
    list_url = "http://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService07/getDrugPrdtPrmsnInq07"
    
    # [1단계] 전체 페이지 파악
    print(">> [정찰] 데이터 위치 계산 중...")
    try:
        res = requests.get(list_url, params={'serviceKey': API_KEY, 'numOfRows': '1', 'type': 'xml'}, timeout=10)
        total_count = int(ET.fromstring(res.text).findtext('.//totalCount'))
        last_page = math.ceil(total_count / 100)
        print(f">> 총 {total_count}건. 마지막 {last_page}페이지부터 탐색합니다.")
    except Exception as e:
        print(f"❌ 접속 실패: {e}")
        return

    total_saved = 0
    
    # [2단계] 광역 역순 스캔 (뒤에서 200페이지)
    # 17건이 발견된 구간(290~440p)을 충분히 커버하도록 설정
    scan_range = 200
    start_page = last_page
    end_page = max(1, last_page - scan_range)
    
    print(f">> 탐색 범위: {start_page}p ~ {end_page}p (2026년 코드 필터링)")

    for page in range(start_page, end_page, -1):
        # 진행상황 로그 (너무 자주 찍히지 않게 10페이지마다)
        if page % 10 == 0:
            print(f">> [진행] {page}페이지 통과 중... (현재 {total_saved}건 확보)")
            
        params = {
            'serviceKey': API_KEY,
            'pageNo': str(page),
            'numOfRows': '100',
            'type': 'xml'
        }
        
        try:
            res = requests.get(list_url, params=params, timeout=30)
            items = ET.fromstring(res.text).findall('.//item')
            if not items: continue

            # 페이지 내 역순 탐색
            for item in reversed(items):
                # 1. 취소된 약 패스
                if item.findtext('CANCEL_DATE'): continue

                # 2. 2026년 코드 필터 (속도 핵심)
                code = item.findtext('PRDLST_STDR_CODE') or ""
                if not code.startswith("2026"):
                    continue 
                
                # 3. 상세 정보 확인 (날짜 & 성분)
                item_seq = item.findtext('ITEM_SEQ')
                product_name = item.findtext('ITEM_NAME')
                
                detail = get_api_date_and_ingr(item_seq)
                if not detail or not detail['date']: continue
                
                real_date = detail['date'].replace("-", "").replace(".", "")
                
                # 4. [타겟] 2026년 2월 데이터 수집
                if real_date >= "20260201":
                    print(f"   -> [💎저장] {product_name} ({real_date})")
                    
                    data = {
                        "item_seq": item_seq,
                        "product_name": product_name,
                        "company": item.findtext('ENTP_NAME'),
                        "category": item.findtext('SPCLTY_PBLC') or "구분없음",
                        "ingredients": detail['ingr'],
                        "approval_date": real_date,
                        "detail_url": f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
                        # 삭제된 항목: manufacturer, efficacy, approval_type
                    }
                    
                    supabase.table("drug_approvals").upsert(data).execute()
                    total_saved += 1
                    time.sleep(0.02) # 데이터가 가벼워졌으므로 대기시간 단축
                
        except Exception as e:
            print(f"⚠️ 에러: {e}")
            continue

    print(f"\n=== 🏆 최종 완료: 깔끔하게 정리된 2월 신약 {total_saved}건 저장 완료! ===")

if __name__ == "__main__":
    main()
