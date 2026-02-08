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
    """
    [상세 API] 품목허가일자, 업체명, 성분, 효능효과 조회
    """
    url = "http://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService07/getDrugPrdtPrmsnDtlInq06"
    params = {'serviceKey': API_KEY, 'item_seq': item_seq, 'numOfRows': '1', 'type': 'xml'}
    
    try:
        res = requests.get(url, params=params, timeout=10)
        root = ET.fromstring(res.text)
        item = root.find('.//item')
        
        if not item: return None

        # 날짜가 상세 API에만 있는 경우가 많음
        permit_date = item.findtext('ITEM_PERMIT_DATE') or item.findtext('PERMIT_DATE')
        
        return {
            'date': permit_date,
            'manu': item.findtext('MANU_METHOD') or "정보없음",
            'ingr': item.findtext('MAIN_ITEM_INGR') or item.findtext('ITEM_INGR_NAME') or "정보없음",
            'effi': BeautifulSoup(item.findtext('EE_DOC_DATA') or "상세참조", "html.parser").get_text()[:500]
        }
    except:
        return None

def main():
    print("=== 🌟 션 팀장님 지시: 'API 방식'으로 2월 1주차(43건) 확보 작전 ===")
    
    list_url = "http://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService07/getDrugPrdtPrmsnInq07"
    
    # [1단계] 전체 데이터 수 확인 및 마지막 페이지 계산
    print(">> [정찰] API 전체 데이터 규모 파악 중...")
    try:
        res = requests.get(list_url, params={'serviceKey': API_KEY, 'numOfRows': '1', 'type': 'xml'}, timeout=10)
        root = ET.fromstring(res.text)
        total_count = int(root.findtext('.//totalCount'))
        last_page = math.ceil(total_count / 100)
        print(f">> 총 {total_count}건. 최신 데이터는 {last_page}페이지부터 있습니다.")
    except Exception as e:
        print(f"❌ API 접속 실패: {e}")
        return

    total_saved = 0
    
    # [2단계] 마지막 페이지부터 역순으로 5페이지만 뒤짐 (1주차 데이터는 무조건 여기 있음)
    for page in range(last_page, last_page - 5, -1):
        if page < 1: break
        
        print(f"\n>> [API] {page}페이지 분석 중...")
        
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

            # 최신순(역순)으로 순회
            for item in reversed(items):
                item_seq = item.findtext('ITEM_SEQ')
                product_name = item.findtext('ITEM_NAME')
                
                # [중요] 목록에 날짜가 없어도 상세 API를 찔러서 확인
                detail = get_api_detail(item_seq)
                
                # 상세 정보가 없거나 날짜가 없으면 스킵
                if not detail or not detail['date']: continue
                
                # 날짜 포맷 통일 (YYYY-MM-DD -> YYYYMMDD)
                real_date = detail['date'].replace("-", "").replace(".", "")
                
                # 🎯 타겟 기간: 2026년 2월 1일 ~ 2월 7일 (1주차)
                if "20260201" <= real_date <= "20260207":
                    print(f"   -> [포착] {product_name} ({real_date})")
                    
                    data = {
                        "item_seq": item_seq,
                        "product_name": product_name,
                        "company": item.findtext('ENTP_NAME'),
                        "manufacturer": detail['manu'],
                        "category": item.findtext('SPCLTY_PBLC') or "구분없음",
                        "approval_type": item.findtext('PRDUCT_TYPE_NAME') or "정상",
                        "ingredients": detail['ingr'],
                        "efficacy": detail['effi'],
                        "approval_date": real_date,
                        "detail_url": f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
                    }
                    
                    supabase.table("drug_approvals").upsert(data).execute()
                    total_saved += 1
                    time.sleep(0.05) # API 부하 방지
                
                # 2026년 1월 데이터가 나오면, 2월 1주차는 다 캔 것임. 종료.
                elif real_date < "20260201":
                    # 페이지 내 정렬이 완벽하지 않을 수 있으니 로그만 찍고 계속 진행 (안전빵)
                    pass

        except Exception as e:
            print(f"⚠️ 에러: {e}")
            continue

    print(f"\n=== 🏆 API 수집 완료: 총 {total_saved}건 저장됨 ===")

if __name__ == "__main__":
    main()
