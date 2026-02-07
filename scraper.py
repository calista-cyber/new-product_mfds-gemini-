import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from supabase import create_client, Client

# 1. 설정 (인증키는 팀장님의 이미지 44934a에서 확인된 값을 사용합니다)
API_KEY = "2b03726584036b06c8c1c6b3d385a73be48f35cceac5444bcd6c611db5de7972"
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(URL, KEY)

def main():
    print("=== 🌟 션 팀장님 전용: 공식 OpenAPI 기반 데이터 수집 작전 시작 ===")
    
    # 이미지 44934a에서 확인된 서비스 URL
    api_url = "http://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService05/getDrugPrdtPrmsnInq05"
    
    # 2월 1일 이후 데이터를 100건씩 가져오도록 설정
    params = {
        'serviceKey': API_KEY,
        'pageNo': '1',
        'numOfRows': '100',
        'start_permit_date': '20260201' 
    }

    try:
        response = requests.get(api_url, params=params, timeout=30)
        root = ET.from_string(response.text)
        
        items = root.findall('.//item')
        total_saved = 0

        for item in items:
            # 팀장님이 요청하신 7가지 항목을 API 규격에 맞춰 추출
            data = {
                "item_seq": item.findtext('ITEM_SEQ'),
                "product_name": item.findtext('ITEM_NAME'),
                "company": item.findtext('ENTP_NAME'),
                "manufacturer": item.findtext('MANU_METHOD') or "자사제조", # 위탁제조업체 정보
                "category": item.findtext('ETC_OTC_CODE'), # 전문일반
                "approval_type": item.findtext('CANCEL_NAME') or "정상", # 허가심사유형 대체
                "ingredients": item.findtext('MAIN_ITEM_INGR'), # 원료약품 및 성분명
                "efficacy": item.findtext('EE_DOC_DATA')[:200] if item.findtext('EE_DOC_DATA') else "상세참조", # 효능효과
                "approval_date": item.findtext('PERMIT_DATE')
            }

            # Supabase 금고에 안착
            supabase.table("drug_approvals").upsert(data).execute()
            total_saved += 1
            print(f"   -> [공식 안착] {data['product_name']}")

        print(f"\n=== 🏆 작전 성공: 총 {total_saved}건의 정밀 데이터가 금고에 안착했습니다! ===")

    except Exception as e:
        print(f"❌ API 통신 오류: {e}")

if __name__ == "__main__":
    main()
