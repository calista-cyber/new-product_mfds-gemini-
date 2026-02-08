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
    """ [상세 API] 추가 정보 조회 """
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
    print("=== 🌟 션 팀장님 지시: '광역 그물망'으로 숨은 2026년 데이터 전수 조사 ===")
    
    list_url = "http://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService07/getDrugPrdtPrmsnInq07"
    
    # [1단계] 전체 페이지 파악
    print(">> [정찰] 전체 데이터 규모 확인 중...")
    try:
        res = requests.get(list_url, params={'serviceKey': API_KEY, 'numOfRows': '1', 'type': 'xml'}, timeout=10)
        total_count = int(ET.fromstring(res.text).findtext('.//totalCount'))
        last_page = math.ceil(total_count / 100)
        print(f">> 총 {total_count}건. 마지막 {last_page}페이지부터 대규모 수색을 시작합니다.")
    except Exception as e:
        print(f"❌ API 접속 실패: {e}")
        return

    total_saved = 0
    
    # [2단계] 대규모 역순 스캔 (뒤에서 150페이지)
    # 데이터가 섞여 있어도 150페이지(15,000건) 안에는 무조건 2026년 데이터가 다 들어옵니다.
    scan_range = 150
    start_page = last_page
    end_page = max(1, last_page - scan_range)
    
    print(f">> 탐색 범위: {start_page}페이지 ~ {end_page}페이지 (약 {scan_range*100}건 검사)")

    for page in range(start_page, end_page, -1):
        print(f"\n>> [API] {page}페이지 분석 중... (현재 확보: {total_saved}건)")
        
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

                # 2. [핵심] 2026년 코드 필터링
                code = item.findtext('PRDLST_STDR_CODE') or ""
                if not code.startswith("2026"):
                    continue # 2026년 코드가 아니면 과감히 패스 (속도 향상)
                
                # 3. 상세 정보 확인 (진짜 날짜 확인)
                item_seq = item.findtext('ITEM_SEQ')
                product_name = item.findtext('ITEM_NAME')
                
                detail = get_api_detail(item_seq)
                if not detail or not detail['date']: continue
                
                real_date = detail['date'].replace("-", "").replace(".", "")
                
                # 4. [타겟] 2026년 2월 데이터인지 확인 (범위를 2월 전체로 잡음)
                # (1월 데이터도 일단 수집해두면 나쁠 건 없습니다)
                if real_date >= "20260201":
                    print(f"   -> [🎯심봤다!] {product_name} (코드:{code}, 일자:{real_date})")
                    
                    data = {
                        "item_seq": item_seq,
                        "product_name": product_name,
                        "company": item.findtext('ENTP_NAME'),
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
                    time.sleep(0.05) # API 부하 조절
                
                elif real_date >= "20260101":
                    # 1월 데이터는 로그만 찍고 넘어감 (필요하면 저장 로직 추가 가능)
                    # print(f"   -> [1월데이터] {product_name} ({real_date}) - 패스")
                    pass

        except Exception as e:
            print(f"⚠️ 에러: {e}")
            continue

    print(f"\n=== 🏆 작전 종료: 광역 수색 결과 총 {total_saved}건의 2월 데이터를 확보했습니다! ===")

if __name__ == "__main__":
    main()
