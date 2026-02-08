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

def get_api_detail(item_seq):
    """ [상세 API] 무조건 API만 사용하여 날짜와 상세정보를 가져옵니다. """
    url = "http://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService07/getDrugPrdtPrmsnDtlInq06"
    params = {'serviceKey': API_KEY, 'item_seq': item_seq, 'numOfRows': '1', 'type': 'xml'}
    try:
        res = requests.get(url, params=params, timeout=10)
        root = ET.fromstring(res.text)
        item = root.find('.//item')
        if not item: return None
        
        return {
            'date': item.findtext('ITEM_PERMIT_DATE') or item.findtext('PERMIT_DATE'),
            'manu': item.findtext('MANU_METHOD') or "정보없음",
            'ingr': item.findtext('MAIN_ITEM_INGR') or item.findtext('ITEM_INGR_NAME') or "정보없음",
            'effi': BeautifulSoup(item.findtext('EE_DOC_DATA') or "상세참조", "html.parser").get_text()[:500]
        }
    except:
        return None

def main():
    print("=== 🌟 션 팀장님 확인 완료: 100% 공식 API 가동 (2월 1주차 전수 수집) ===")
    
    # 웹사이트 주소가 아닌, '공식 API 주소' 사용
    list_url = "http://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService07/getDrugPrdtPrmsnInq07"
    
    # [1단계] API 전체 데이터 끝 페이지 계산
    print(">> [API 통신] 전체 데이터 규모 확인 중...")
    try:
        res = requests.get(list_url, params={'serviceKey': API_KEY, 'numOfRows': '1', 'type': 'xml'}, timeout=10)
        total_count = int(ET.fromstring(res.text).findtext('.//totalCount'))
        last_page = math.ceil(total_count / 100)
        print(f">> 총 {total_count}건. 마지막 {last_page}페이지부터 탐색합니다.")
    except Exception as e:
        print(f"❌ API 접속 실패: {e}")
        return

    target_saved = 0

    # [2단계] 마지막 페이지부터 역순으로 탐색 (최신 데이터 확보)
    for page in range(last_page, last_page - 10, -1):
        if page < 1: break
        
        print(f"\n>> [API 통신] {page}페이지 스캔 중...")
        
        try:
            params = {'serviceKey': API_KEY, 'pageNo': str(page), 'numOfRows': '100', 'type': 'xml'}
            res = requests.get(list_url, params=params, timeout=30)
            items = ET.fromstring(res.text).findall('.//item')
            
            if not items: continue

            for item in reversed(items):
                # 연도 힌트 적용
                code = item.findtext('PRDLST_STDR_CODE') or ""
                year_prefix = code[:4]
                
                if year_prefix == "2026":
                    item_seq = item.findtext('ITEM_SEQ')
                    product_name = item.findtext('ITEM_NAME')
                    cancel_date = item.findtext('CANCEL_DATE') # API가 제공하는 취소일자
                    
                    detail = get_api_detail(item_seq)
                    if not detail or not detail['date']: continue
                    
                    real_date = detail['date'].replace("-", "").replace(".", "")
                    
                    # 🎯 타겟: 2월 1일 ~ 2월 7일 (1주차 데이터 전수 수집)
                    if "20260201" <= real_date <= "20260207":
                        # 취소된 약이든 아니든 무조건 수집하되, 상태만 기록
                        status = "취소됨" if cancel_date else "정상"
                        print(f"   -> [API 수집] {product_name} ({real_date}) - 상태: {status}")
                        
                        data = {
                            "item_seq": item_seq,
                            "product_name": product_name,
                            "company": item.findtext('ENTP_NAME'),
                            "manufacturer": detail['manu'],
                            "category": item.findtext('SPCLTY_PBLC') or "구분없음",
                            "approval_type": status, # 정상 또는 취소됨
                            "ingredients": detail['ingr'],
                            "efficacy": detail['effi'],
                            "approval_date": real_date,
                            "detail_url": f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
                        }
                        supabase.table("drug_approvals").upsert(data).execute()
                        target_saved += 1
                        time.sleep(0.05)
                        
        except Exception as e:
            print(f"⚠️ 에러 발생: {e}")
            continue

    print(f"\n=== 🏆 API 수집 완료: 2월 1주차 데이터 총 {target_saved}건 저장됨 ===")

if __name__ == "__main__":
    main()
