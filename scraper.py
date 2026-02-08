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
    """ [상세 API] 제조원, 성분, 효능 등 추가 정보 조회 """
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
    print("=== 🌟 션 팀장님 최종 지시: '2026년 코드' 필터링으로 정확도 100% 확보 ===")
    
    list_url = "http://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService07/getDrugPrdtPrmsnInq07"
    
    # [1단계] 전체 페이지 파악
    print(">> [정찰] 데이터 규모 확인 중...")
    try:
        res = requests.get(list_url, params={'serviceKey': API_KEY, 'numOfRows': '1', 'type': 'xml'}, timeout=10)
        total_count = int(ET.fromstring(res.text).findtext('.//totalCount'))
        last_page = math.ceil(total_count / 100)
        print(f">> 총 {total_count}건. 최신 데이터(변경분 포함)는 {last_page}페이지에 있습니다.")
    except Exception as e:
        print(f"❌ API 접속 실패: {e}")
        return

    total_saved = 0
    
    # [2단계] 역순 스캔 (마지막 페이지부터 뒤로 20페이지)
    # 최근에 '취소'된 옛날 약들이 뒤쪽에 몰려있을 수 있으므로, 넉넉하게 20페이지를 훑어서 '2026년생'을 찾습니다.
    scan_depth = 20
    
    for page in range(last_page, last_page - scan_depth, -1):
        if page < 1: break
        
        print(f"\n>> [API] {page}페이지 정밀 선별 중...")
        
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

            # 최신순(역순) 순회
            for item in reversed(items):
                product_name = item.findtext('ITEM_NAME')
                
                # 1. 취소 여부 확인 (취소된 약은 버림)
                cancel_date = item.findtext('CANCEL_DATE')
                if cancel_date:
                    # 로그를 너무 많이 찍지 않기 위해 취소된 건은 조용히 패스하거나 필요시 주석 해제
                    # print(f"   -> [거름] {product_name} (취소됨)") 
                    continue

                # 2. [핵심] 품목기준코드(PRDLST_STDR_CODE) 확인
                code = item.findtext('PRDLST_STDR_CODE') or ""
                
                # 코드가 "2026"으로 시작하지 않으면? -> 옛날 약임 -> 패스!
                if not code.startswith("2026"):
                    continue
                
                # 여기까지 왔으면 "2026년에 태어난 살아있는 약"입니다.
                item_seq = item.findtext('ITEM_SEQ')
                
                # 상세 정보 조회
                detail = get_api_detail(item_seq)
                if not detail or not detail['date']: continue
                
                real_date = detail['date'].replace("-", "").replace(".", "")
                
                print(f"   -> [💎발굴] {product_name} (코드:{code}, 일자:{real_date})")
                
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
                time.sleep(0.05)

    
        except Exception as e:
            print(f"⚠️ 에러: {e}")
            continue

    print(f"\n=== 🏆 수집 완료: 잡동사니 제거 후 '순수 2026년 신약' {total_saved}건 확보! ===")

if __name__ == "__main__":
    main()
