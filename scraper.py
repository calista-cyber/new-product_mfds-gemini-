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

def get_full_detail(item_seq):
    """
    [상세 API] 목록에는 없는 '효능효과', '위탁제조업체' 등을 가져옵니다.
    """
    url = "http://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService07/getDrugPrdtPrmsnDtlInq06"
    params = {'serviceKey': API_KEY, 'item_seq': item_seq, 'numOfRows': '1', 'type': 'xml'}
    
    try:
        res = requests.get(url, params=params, timeout=10)
        root = ET.fromstring(res.text)
        item = root.find('.//item')
        
        if not item: return None

        # 상세 API에서 추가 정보 추출
        manufacturer = item.findtext('MANU_METHOD') or "정보없음" # 위탁/제조
        efficacy_raw = item.findtext('EE_DOC_DATA') or "상세참조"
        efficacy = BeautifulSoup(efficacy_raw, "html.parser").get_text()[:500]
        
        return {
            'manu': manufacturer,
            'effi': efficacy
        }
    except:
        return None

def main():
    print("=== 🌟 션 팀장님 지시: API 명세서 기반 '마지막 페이지' 공략 ===")
    
    list_url = "http://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService07/getDrugPrdtPrmsnInq07"
    
    # [1단계] 전체 데이터 개수(totalCount) 확인 (정찰)
    print(">> [정찰] 전체 데이터 개수를 파악하여 '끝 페이지'를 계산합니다...")
    try:
        # 파라미터 없이 요청하면 totalCount를 줍니다.
        res = requests.get(list_url, params={'serviceKey': API_KEY, 'numOfRows': '1', 'type': 'xml'}, timeout=10)
        root = ET.fromstring(res.text)
        
        total_count_str = root.findtext('.//totalCount')
        if not total_count_str:
            print("❌ API 응답 오류: totalCount를 찾을 수 없습니다.")
            return
            
        total_count = int(total_count_str)
        # 한 페이지에 100개씩 볼 때 마지막 페이지 계산
        last_page = math.ceil(total_count / 100)
        print(f">> 총 {total_count}건 발견. 최신 데이터는 {last_page}페이지에 있습니다.")
        
    except Exception as e:
        print(f"❌ 정찰 실패: {e}")
        return

    # [2단계] 마지막 페이지부터 거꾸로(역순) 3페이지 스캔
    # (최신 데이터가 뒤에 쌓이는 구조이므로 뒤에서부터 봐야 2026년 데이터가 나옴)
    target_saved = 0
    
    for page in range(last_page, last_page - 4, -1):
        if page < 1: break
        
        print(f"\n>> [API] {page}페이지 (최신구간) 진입...")
        
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

            # 한 페이지 내에서도 순서가 섞여있을 수 있으니 역순 순회
            for item in reversed(items):
                # [명세서 확인] 날짜 태그: ITEM_PERMIT_DATE
                p_date = item.findtext('ITEM_PERMIT_DATE')
                
                if not p_date: continue
                
                # 날짜 형식 통일 (YYYY-MM-DD -> YYYYMMDD)
                p_date_clean = p_date.replace("-", "").replace(".", "")
                
                # 🎯 타겟: 2026년 2월 1일 이후 데이터
                if p_date_clean >= "20260201":
                    item_seq = item.findtext('ITEM_SEQ')
                    product_name = item.findtext('ITEM_NAME')
                    
                    print(f"   -> [포착] {product_name} ({p_date_clean})")
                    
                    # [3단계] 상세 정보 보강 (효능, 위탁제조 등)
                    detail = get_full_detail(item_seq)
                    manu = detail['manu'] if detail else "정보없음"
                    effi = detail['effi'] if detail else "상세참조"
                    
                    # [명세서 확인] 전문/일반 태그: SPCLTY_PBLC
                    category_code = item.findtext('SPCLTY_PBLC') or "구분없음"
                    
                    data = {
                        "item_seq": item_seq,
                        "product_name": product_name,
                        "company": item.findtext('ENTP_NAME'),
                        "manufacturer": manu,  # 상세API에서 온 값
                        "category": category_code, # 명세서 태그 적용
                        "approval_type": item.findtext('PRDUCT_TYPE_NAME') or "정상",
                        "ingredients": item.findtext('ITEM_INGR_NAME') or "성분정보없음", # 목록API에도 성분이 있음!
                        "efficacy": effi,      # 상세API에서 온 값
                        "approval_date": p_date,
                        "detail_url": f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
                    }
                    
                    supabase.table("drug_approvals").upsert(data).execute()
                    target_saved += 1
                    time.sleep(0.05) 
                
                elif p_date_clean < "20260201":
                    # 1월 데이터가 나오면 일단 패스 (페이지 전체를 확인하되 로그만 남김)
                    pass

        except Exception as e:
            print(f"⚠️ 페이지 처리 중 오류: {e}")
            continue

    print(f"\n=== 🏆 작전 성공: 총 {target_saved}건의 최신 데이터를 확보했습니다! ===")

if __name__ == "__main__":
    main()
