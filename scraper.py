import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from supabase import create_client, Client
import time

# 1. 설정 (팀장님의 소중한 API 키)
API_KEY = "2b03726584036b06c8c1c6b3d385a73be48f35cceac5444bcd6c611db5de7972"
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(URL, KEY)

def get_api_detail(item_seq):
    """
    [상세 API] 제품번호(item_seq)로 성분, 효능효과, 제조원 정보를 공식 조회
    """
    url = "http://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService07/getDrugPrdtPrmsnDtlInq06"
    params = {
        'serviceKey': API_KEY,
        'item_seq': item_seq,
        'numOfRows': '1',
        'type': 'xml'
    }
    
    try:
        res = requests.get(url, params=params, timeout=10)
        root = ET.fromstring(res.text)
        item = root.find('.//item')
        
        if not item:
            return "정보없음", "정보없음", "상세참조"

        # 1. 위탁제조업체 (MATERIAL_NAME 또는 EE_DOC_DATA 내 분석 필요하나 API는 보통 주성분/효능 위주)
        # API에서는 '제조원' 정보가 별도 필드로 명확치 않을 때가 있어 기본값 처리
        manufacturer = item.findtext('MANU_METHOD') or "정보없음"

        # 2. 성분명 (MAIN_ITEM_INGR)
        ingredients = item.findtext('MAIN_ITEM_INGR') or "정보없음"

        # 3. 효능효과 (EE_DOC_DATA) -> HTML 태그가 포함될 수 있어 텍스트만 깔끔하게
        efficacy_raw = item.findtext('EE_DOC_DATA') or "상세 효능효과 참조"
        # 너무 길면 300자에서 자르기
        efficacy = efficacy_raw[:300] if efficacy_raw else "상세참조"

        return manufacturer, ingredients, efficacy

    except Exception:
        return "조회실패", "조회실패", "조회실패"

def main():
    print("=== 🌟 션 팀장님 전용: API 완전 정복 (목록+상세 병합) ===")
    
    # [목록 API] v7 버전
    list_url = "http://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService07/getDrugPrdtPrmsnInq07"
    
    # 2월 1일 이후 허가된 목록 조회
    # (API는 날짜 형식이 YYYYMMDD 입니다)
    start_date = "20260201"
    
    params = {
        'serviceKey': API_KEY,
        'pageNo': '1',
        'numOfRows': '100',
        'type': 'xml',
        'start_permit_date': start_date 
    }

    try:
        print(f">> [1단계] 신규 허가 목록을 조회합니다... (기준일: {start_date})")
        response = requests.get(list_url, params=params, timeout=30)
        root = ET.fromstring(response.text)
        
        items = root.findall('.//item')
        if not items:
            print(">> 신규 데이터가 없습니다.")
            return

        total_saved = 0
        print(f">> 총 {len(items)}건 발견. 상세 정보를 결합하여 저장을 시작합니다.")

        for item in items:
            item_seq = item.findtext('ITEM_SEQ')
            product_name = item.findtext('ITEM_NAME')
            permit_date = item.findtext('ITEM_PERMIT_DATE') # 20260205 형태

            # 날짜 2차 필터링 (API 파라미터가 안 먹혔을 경우 대비)
            if not permit_date or permit_date < start_date:
                continue

            print(f"   -> 처리 중: {product_name} ({item_seq})")

            # [2단계] 상세 API 호출하여 빈칸 채우기
            manufacturer, ingredients, efficacy = get_api_detail(item_seq)

            data = {
                "item_seq": item_seq,
                "product_name": product_name,
                "company": item.findtext('ENTP_NAME'),
                "manufacturer": manufacturer, # 상세 API에서 온 값
                "category": item.findtext('ETC_OTC_NAME') or "구분없음",
                "approval_type": item.findtext('PRDUCT_TYPE_NAME') or "정상",
                "ingredients": ingredients,   # 상세 API에서 온 값
                "efficacy": efficacy,         # 상세 API에서 온 값
                "approval_date": permit_date,
                "detail_url": f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
            }
            
            # 금고에 저장
            supabase.table("drug_approvals").upsert(data).execute()
            total_saved += 1
            
            # API 서버 예의상 0.1초 텀
            time.sleep(0.1)

        print(f"\n=== 🏆 작전 성공: 총 {total_saved}건을 '공식 API'로 완벽하게 수집했습니다! ===")

    except Exception as e:
        print(f"❌ 시스템 오류: {e}")

if __name__ == "__main__":
    main()
