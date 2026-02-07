import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from supabase import create_client, Client

# 1. 설정
API_KEY = "2b03726584036b06c8c1c6b3d385a73be48f35cceac5444bcd6c611db5de7972"
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(URL, KEY)

def main():
    print("=== 🌟 션 팀장님 전용: 데이터 '무조건 저장' 작전 시작 ===")
    
    # 공공데이터포털 v7 서비스 URL
    api_url = "http://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService07/getDrugPrdtPrmsnInq07"
    
    # 요청 파라미터
    params = {
        'serviceKey': API_KEY,
        'pageNo': '1',
        'numOfRows': '100',
        'type': 'xml',
        # 혹시 모르니 API 쪽 필터도 일단 넣어둠 (작동 안 해도 무관)
        'start_permit_date': '20260201' 
    }

    try:
        print(f">> API 데이터 요청 중...")
        response = requests.get(api_url, params=params, timeout=30)
        
        root = ET.fromstring(response.text)
        
        header_code = root.findtext('.//resultCode')
        if header_code and header_code != '00':
            print(f"⚠️ API 에러 코드 반환: {root.findtext('.//resultMsg')}")
            return

        items = root.findall('.//item')
        if not items:
            print(">> 데이터가 없습니다.")
            return

        total_saved = 0
        print(f">> 발견된 {len(items)}개의 데이터를 묻지도 따지지도 않고 저장합니다.")

        for item in items:
            data = {
                "item_seq": item.findtext('ITEM_SEQ'),
                "product_name": item.findtext('ITEM_NAME'),
                "company": item.findtext('ENTP_NAME'),
                "manufacturer": item.findtext('MANU_METHOD') or "정보없음", 
                "category": item.findtext('ETC_OTC_CODE') or "구분없음",
                "approval_type": item.findtext('CANCEL_NAME') or "정상",
                "ingredients": item.findtext('MAIN_ITEM_INGR') or "정보없음",
                "efficacy": (item.findtext('EE_DOC_DATA') or "상세참조")[:200],
                "approval_date": item.findtext('PERMIT_DATE')
            }
            
            # [수정] 날짜 필터링(if문) 삭제 -> 무조건 저장!
            # 디버깅을 위해 날짜를 로그에 찍어봅니다.
            print(f"   -> [저장 중] {data['product_name']} (허가일: {data['approval_date']})")
            
            supabase.table("drug_approvals").upsert(data).execute()
            total_saved += 1

        print(f"\n=== 🏆 작전 대성공: 총 {total_saved}건이 금고에 강제 입고되었습니다! ===")

    except Exception as e:
        print(f"❌ 시스템 오류: {e}")

if __name__ == "__main__":
    main()
