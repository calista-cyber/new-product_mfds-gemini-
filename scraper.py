import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from supabase import create_client, Client

# 1. 설정
# (팀장님의 이미지 44934a에서 확인된 일반 인증키)
API_KEY = "2b03726584036b06c8c1c6b3d385a73be48f35cceac5444bcd6c611db5de7972"
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(URL, KEY)

def main():
    print("=== 🌟 션 팀장님 전용: 공식 OpenAPI(v7) 데이터 수집 시작 ===")
    
    # [수정] 스크린샷에 명시된 'Service07' 및 'getDrugPrdtPrmsnInq07'로 주소 업데이트
    api_url = "http://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService07/getDrugPrdtPrmsnInq07"
    
    # 요청 파라미터 (공공데이터포털 v7 표준)
    params = {
        'serviceKey': API_KEY,
        'pageNo': '1',
        'numOfRows': '100',
        'type': 'xml', # 응답 형식 명시
        # 날짜 포맷이 YYYYMMDD인 경우가 많으므로 20260201로 설정
        # 만약 데이터가 안 나오면 이 부분을 제거하고 전체를 불러온 뒤 파이썬에서 필터링할 수도 있습니다.
    }

    try:
        print(f">> API 데이터 요청 중... (URL: {api_url})")
        response = requests.get(api_url, params=params, timeout=30)
        
        # [핵심 수정] from_string -> fromstring (언더바 제거)
        root = ET.fromstring(response.text)
        
        # 응답 코드 확인 (에러 메시지가 오는지 체크)
        header_code = root.findtext('.//resultCode')
        if header_code and header_code != '00':
            error_msg = root.findtext('.//resultMsg')
            print(f"⚠️ API 에러 발생: {error_msg} (코드: {header_code})")
            return

        items = root.findall('.//item')
        if not items:
            print(">> 수집된 데이터가 0건입니다. (날짜 조건이나 파라미터를 확인해주세요)")
            # 디버깅을 위해 응답 내용 일부 출력
            print(f"응답 내용: {response.text[:200]}")
            return

        total_saved = 0
        print(f">> 총 {len(items)}개의 데이터를 발견했습니다. 금고 입고를 시작합니다.")

        for item in items:
            # v7 버전에 맞춘 항목 추출 (없을 경우 안전하게 빈 문자열 처리)
            data = {
                "item_seq": item.findtext('ITEM_SEQ'),
                "product_name": item.findtext('ITEM_NAME'),
                "company": item.findtext('ENTP_NAME'),
                "manufacturer": item.findtext('MANU_METHOD') or "정보없음", 
                "category": item.findtext('ETC_OTC_CODE') or "구분없음",
                "approval_type": item.findtext('CANCEL_NAME') or "정상",
                "ingredients": item.findtext('MAIN_ITEM_INGR') or "정보없음",
                "efficacy": (item.findtext('EE_DOC_DATA') or "상세참조")[:200], # 너무 길면 자름
                "approval_date": item.findtext('PERMIT_DATE')
            }
            
            # 날짜 필터링 (2월 1일 이후 데이터만 저장)
            # API 파라미터가 안 먹힐 경우를 대비한 2중 안전장치
            if data['approval_date'] and data['approval_date'] >= "20260201":
                supabase.table("drug_approvals").upsert(data).execute()
                total_saved += 1
                print(f"   -> [저장 완료] {data['product_name']}")

        print(f"\n=== 🏆 작전 성공: 총 {total_saved}건의 데이터가 금고에 안착했습니다! ===")

    except Exception as e:
        print(f"❌ 시스템 오류: {e}")

if __name__ == "__main__":
    main()
