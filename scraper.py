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

def get_full_detail_and_date(item_seq):
    """
    [상세 API] 날짜, 성분, 효능 등 모든 핵심 정보를 가져옵니다.
    목록 API가 날짜를 안 줘도, 여기서 확실하게 알아낼 수 있습니다.
    """
    url = "http://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService07/getDrugPrdtPrmsnDtlInq06"
    params = {'serviceKey': API_KEY, 'item_seq': item_seq, 'numOfRows': '1', 'type': 'xml'}
    
    try:
        res = requests.get(url, params=params, timeout=10)
        root = ET.fromstring(res.text)
        item = root.find('.//item')
        
        if not item: return None

        # [핵심] 상세 API에서 진짜 허가일자 추출
        permit_date = item.findtext('ITEM_PERMIT_DATE') or item.findtext('PERMIT_DATE')
        
        manufacturer = item.findtext('MANU_METHOD') or "정보없음"
        ingredients = item.findtext('MAIN_ITEM_INGR') or item.findtext('ITEM_INGR_NAME') or "정보없음"
        efficacy_raw = item.findtext('EE_DOC_DATA') or "상세참조"
        efficacy = BeautifulSoup(efficacy_raw, "html.parser").get_text()[:500]
        
        return {
            'date': permit_date, 
            'manu': manufacturer,
            'ingr': ingredients,
            'effi': efficacy
        }
    except:
        return None

def main():
    print("=== 🌟 션 팀장님 지시: 목록 날짜 무시 -> 상세 강제 검증 모드 가동 ===")
    
    list_url = "http://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService07/getDrugPrdtPrmsnInq07"
    
    # [1단계] 전체 데이터 개수 파악
    print(">> [정찰] 전체 데이터 개수 확인 중...")
    try:
        res = requests.get(list_url, params={'serviceKey': API_KEY, 'numOfRows': '1', 'type': 'xml'}, timeout=10)
        root = ET.fromstring(res.text)
        total_count = int(root.findtext('.//totalCount'))
        last_page = math.ceil(total_count / 100)
        print(f">> 총 {total_count}건. 최신 데이터는 {last_page}페이지에 위치합니다.")
    except Exception as e:
        print(f"❌ 초기화 실패: {e}")
        return

    # [2단계] 마지막 페이지부터 역순으로 5페이지 스캔
    target_saved = 0
    
    for page in range(last_page, last_page - 5, -1):
        if page < 1: break
        
        print(f"\n>> [API] {page}페이지 데이터를 전수 검사합니다...")
        
        try:
            params = {'serviceKey': API_KEY, 'pageNo': str(page), 'numOfRows': '100', 'type': 'xml'}
            res = requests.get(list_url, params=params, timeout=30)
            items = ET.fromstring(res.text).findall('.//item')
            
            if not items: continue

            # 역순 순회
            for item in reversed(items):
                item_seq = item.findtext('ITEM_SEQ')
                product_name = item.findtext('ITEM_NAME')
                
                # [중요] 목록에 있는 날짜는 무시하고, 상세 API를 찔러서 진짜 날짜를 확인
                detail = get_full_detail_and_date(item_seq)
                
                # 상세 정보가 없거나 날짜가 없으면 패스
                if not detail or not detail['date']:
                    continue
                
                # 날짜 포맷 통일 (2026-02-01 -> 20260201)
                real_date = detail['date'].replace("-", "").replace(".", "")
                
                # 🎯 타겟: 2026년 2월 1일 이후
                if real_date >= "20260201":
                    print(f"   -> [포착] {product_name} (허가일: {real_date})")
                    
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
                    target_saved += 1
                    time.sleep(0.05) # API 호출 간격
                
                # 2025년 데이터가 나오면 너무 멀리 온 것이므로 종료 (최적화)
                elif real_date < "20260101":
                    print(">> 2025년 데이터 발견. 더 이상의 과거 데이터 수집을 중단합니다.")
                    print(f"\n=== 🏆 최종 결과: 총 {target_saved}건(목표 43건) 저장 완료! ===")
                    return

        except Exception as e:
            print(f"⚠️ 페이지 처리 오류: {e}")
            continue

    print(f"\n=== 🏆 작전 종료: 총 {target_saved}건 저장 완료! ===")

if __name__ == "__main__":
    main()
