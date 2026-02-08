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
    """ [상세 API] 정밀 정보 조회 """
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
    print("=== 🌟 션 팀장님 지시: 식약처 DB '전수조사(Full Scan)' 가동 ===")
    
    list_url = "http://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService07/getDrugPrdtPrmsnInq07"
    
    # [1단계] 전체 페이지 계산
    print(">> [정찰] 전체 페이지 수 확인 중...")
    try:
        res = requests.get(list_url, params={'serviceKey': API_KEY, 'numOfRows': '1', 'type': 'xml'}, timeout=10)
        total_count = int(ET.fromstring(res.text).findtext('.//totalCount'))
        last_page = math.ceil(total_count / 100)
        print(f">> 총 {total_count}건. 1페이지부터 {last_page}페이지까지 전부 뒤집니다.")
    except Exception as e:
        print(f"❌ 접속 실패: {e}")
        return

    total_saved = 0
    
    # [2단계] 무제한 역순 스캔 (Last Page -> 1 Page)
    # 중간에 멈추는 조건(break) 없이 끝까지 갑니다.
    print(f">> 전수조사 시작! (예상 소요시간: 조금 걸리지만 확실합니다)")

    for page in range(last_page, 0, -1):
        # 진행상황 표시 (10페이지마다 로그)
        if page % 10 == 0:
            print(f">> [진행중] {page}페이지 통과 중... (현재 {total_saved}건 발견)")
        
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

            # 페이지 내 아이템 전수 검사
            for item in reversed(items):
                # 1. 1차 필터: '취소일자' 있으면 탈락
                if item.findtext('CANCEL_DATE'): continue

                # 2. 2차 필터: '2026' 코드가 아니면 탈락 (광속 패스)
                code = item.findtext('PRDLST_STDR_CODE') or ""
                if not code.startswith("2026"):
                    continue 
                
                # --- 여기 도달하면 '2026년생 유효 약품' ---
                product_name = item.findtext('ITEM_NAME')
                item_seq = item.findtext('ITEM_SEQ')
                
                # 3. 상세 검증: 진짜 허가일자 확인
                detail = get_api_detail(item_seq)
                if not detail or not detail['date']: continue
                
                real_date = detail['date'].replace("-", "").replace(".", "")
                
                # 4. 최종 타겟: 2월 1일 이후 데이터
                if real_date >= "20260201":
                    print(f"   -> [💎검거완료] {product_name} (날짜:{real_date}, 페이지:{page})")
                    
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
                    time.sleep(0.05) # API 매너 호출
                
                elif real_date >= "20260101":
                    # 1월 데이터는 로그 없이 패스 (전수조사 속도를 위해)
                    pass

        except Exception as e:
            print(f"⚠️ {page}페이지 에러: {e}")
            continue

    print(f"\n=== 🏆 전수조사 종료: DB를 탈탈 털어 총 {total_saved}건을 확보했습니다! ===")

if __name__ == "__main__":
    main()
