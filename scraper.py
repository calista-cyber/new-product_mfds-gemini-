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
    [상세 API] 품목허가 상세 정보 조회 (DtlInq06)
    목록에는 없는 '효능효과', '위탁제조업체' 등을 가져옵니다.
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
            'manu': item.findtext('MANU_METHOD') or "정보없음",
            'ingr': item.findtext('MAIN_ITEM_INGR') or item.findtext('ITEM_INGR_NAME') or "정보없음",
            'effi': BeautifulSoup(item.findtext('EE_DOC_DATA') or "상세참조", "html.parser").get_text()[:500]
        }
    except:
        return None

def main():
    print("=== 🌟 션 팀장님 교정: API(`15095677`)로 PPCAC01 데이터 복제 ===")
    
    # 팀장님이 찾아주신 바로 그 API (목록 조회)
    list_url = "http://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService07/getDrugPrdtPrmsnInq07"
    
    # [1단계] 전체 데이터 수 확인 (Swagger 가이드의 totalCount 활용)
    print(">> [정찰] 전체 데이터 규모 파악 중...")
    try:
        # numOfRows=1로 최소 요청하여 totalCount만 확인
        res = requests.get(list_url, params={'serviceKey': API_KEY, 'numOfRows': '1', 'type': 'xml'}, timeout=10)
        root = ET.fromstring(res.text)
        
        # [cite: 191] 응답 결과 확인
        result_code = root.findtext('.//resultCode')
        if result_code != '00':
             print(f"❌ API 오류 발생: {root.findtext('.//resultMsg')}")
             return

        total_count = int(root.findtext('.//totalCount'))
        
        # 한 페이지에 100개씩 본다고 가정할 때 마지막 페이지 계산
        last_page = math.ceil(total_count / 100)
        print(f">> 총 {total_count}건. PPCAC01의 최신 데이터는 {last_page}페이지에 있습니다.")
    except Exception as e:
        print(f"❌ 접속 실패: {e}")
        return

    total_saved = 0
    
    # [2단계] 마지막 페이지부터 역순으로 3페이지(최근 300건) 스캔
    # PPCAC01 화면 상단에 있는 '최신 허가' 약들입니다.
    for page in range(last_page, last_page - 3, -1):
        if page < 1: break
        
        print(f"\n>> [API] {page}페이지 (최신순) 데이터 분석 중...")
        
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

            # [핵심] 최신순으로 보기 위해 리스트를 뒤집어서(reversed) 처리
            for item in reversed(items):
                item_seq = item.findtext('ITEM_SEQ')
                product_name = item.findtext('ITEM_NAME')
                company = item.findtext('ENTP_NAME')
                
                # 취소 여부 확인 (Swagger 모델 참조)
                cancel_date = item.findtext('CANCEL_DATE')
                cancel_name = item.findtext('CANCEL_NAME')
                
                # [필터] 취소된 약은 건너뛰기 (팀장님 요청사항 반영)
                if cancel_date or cancel_name:
                    print(f"   -> [패스] {product_name} (취소됨)")
                    continue

                # 상세 정보 조회 (날짜 및 제조원 등)
                detail = get_api_detail(item_seq)
                
                # 상세 정보가 없거나 날짜가 없으면 스킵
                if not detail or not detail['date']: continue
                
                real_date = detail['date'].replace("-", "").replace(".", "")
                
                # 최근 데이터인지 확인 (예: 2026년 이후 데이터만)
                # 너무 옛날 데이터가 나오면 루프 종료 가능
                if real_date < "20260101":
                     # 여기서는 일단 계속 수집하지만, 필요시 break 가능
                     pass

                print(f"   -> [수집] {product_name} ({real_date})")
                
                data = {
                    "item_seq": item_seq,
                    "product_name": product_name,
                    "company": company,
                    "manufacturer": detail['manu'],
                    "category": item.findtext('SPCLTY_PBLC') or "구분없음",
                    "approval_type": "정상",
                    "ingredients": detail['ingr'],
                    "efficacy": detail['effi'],
                    "approval_date": real_date,
                    "detail_url": f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
                }
                
                supabase.table("drug_approvals").upsert(data).execute()
                total_saved += 1
                time.sleep(0.05) # API 매너 호출

        except Exception as e:
            print(f"⚠️ 에러: {e}")
            continue

    print(f"\n=== 🏆 수집 완료: PPCAC01 화면의 최신 데이터 {total_saved}건 확보! ===")

if __name__ == "__main__":
    main()
