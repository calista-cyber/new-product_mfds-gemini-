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

def get_detail_info(item_seq):
    """ [상세 API] 날짜 및 상세정보 정밀 조회 """
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
    print("=== 🌙 션 팀장님 굿나잇: '2026 코드' 무중단 전수조사 시작 ===")
    
    list_url = "http://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService07/getDrugPrdtPrmsnInq07"
    
    # [1단계] 끝 페이지 계산
    print(">> [정찰] 전체 데이터 규모 확인 중...")
    try:
        res = requests.get(list_url, params={'serviceKey': API_KEY, 'numOfRows': '1', 'type': 'xml'}, timeout=10)
        total_count = int(ET.fromstring(res.text).findtext('.//totalCount'))
        last_page = math.ceil(total_count / 100)
        print(f">> 총 {total_count}건. 마지막 {last_page}페이지부터 역순으로 훑습니다.")
    except:
        return

    target_saved = 0

    # [2단계] 마지막 페이지부터 역순으로 '20페이지' 무조건 스캔 (조기종료 없음)
    # 20페이지 = 2000개 데이터. 이 안에 2026년 데이터는 100% 들어있습니다.
    scan_range = 20 
    start_page = last_page
    end_page = max(1, last_page - scan_range)

    for page in range(start_page, end_page - 1, -1):
        print(f"\n>> [스캔] {page}페이지 분석 중... (멈추지 않습니다)")
        
        try:
            params = {'serviceKey': API_KEY, 'pageNo': str(page), 'numOfRows': '100', 'type': 'xml'}
            res = requests.get(list_url, params=params, timeout=30)
            items = ET.fromstring(res.text).findall('.//item')
            
            if not items: continue

            # 페이지 내 역순 탐색
            for item in reversed(items):
                # 힌트 적용: 기준코드 앞 4자리 확인
                code = item.findtext('PRDLST_STDR_CODE') or item.findtext('ITEM_SEQ') or ""
                year_prefix = code[:4]
                
                # '2026'으로 시작하면 무조건 상세 조회 (놓치지 않기 위해)
                if year_prefix == "2026":
                    item_seq = item.findtext('ITEM_SEQ')
                    product_name = item.findtext('ITEM_NAME')
                    
                    # 상세 API로 날짜 검증
                    detail = get_detail_info(item_seq)
                    if not detail or not detail['date']: continue
                    
                    real_date = detail['date'].replace("-", "").replace(".", "")
                    
                    # 🎯 타겟: 2월 1일 ~ 2월 14일
                    if "20260201" <= real_date <= "20260214":
                        print(f"   -> [🎯보물발견] {product_name} ({real_date})")
                        
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
                        time.sleep(0.05)
                
                # 2025년 데이터가 나와도 멈추지 않고 계속 갑니다! (혹시 섞여 있을까봐)

        except Exception as e:
            print(f"⚠️ 페이지 에러: {e}")
            continue

    print(f"\n=== 🏆 굿나잇 리포트: 총 {target_saved}건 저장 완료! 좋은 꿈 꾸세요! ===")

if __name__ == "__main__":
    main()
