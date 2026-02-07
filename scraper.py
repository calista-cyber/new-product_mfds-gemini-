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
    """ [상세 API] 성분, 제조원, 효능 등 정밀 조회 """
    url = "http://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService07/getDrugPrdtPrmsnDtlInq06"
    params = {'serviceKey': API_KEY, 'item_seq': item_seq, 'numOfRows': '1', 'type': 'xml'}
    try:
        res = requests.get(url, params=params, timeout=10)
        root = ET.fromstring(res.text)
        item = root.find('.//item')
        if not item: return "정보없음", "정보없음", "상세참조"
        
        return (
            item.findtext('MANU_METHOD') or "정보없음",
            item.findtext('MAIN_ITEM_INGR') or "정보없음",
            BeautifulSoup(item.findtext('EE_DOC_DATA') or "상세참조", "html.parser").get_text()[:500]
        )
    except:
        return "조회실패", "조회실패", "조회실패"

def main():
    print("=== 🌟 션 팀장님 지시: API 역순(최신순) 정밀 타격 시작 ===")
    
    list_url = "http://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService07/getDrugPrdtPrmsnInq07"
    
    # [1단계] 전체 데이터 개수(totalCount) 확인을 위한 정찰
    print(">> [정찰] 전체 데이터 개수를 파악합니다...")
    init_params = {'serviceKey': API_KEY, 'pageNo': '1', 'numOfRows': '1', 'type': 'xml'}
    
    try:
        res = requests.get(list_url, params=init_params, timeout=10)
        root = ET.fromstring(res.text)
        total_count_str = root.findtext('.//totalCount')
        
        if not total_count_str:
            print("❌ API 응답에서 totalCount를 찾을 수 없습니다. (키 확인 필요)")
            return
            
        total_count = int(total_count_str)
        print(f">> 식약처 DB 총 데이터: {total_count}건")
        
        # [2단계] 마지막 페이지 계산 (최신 데이터가 있는 곳)
        # 한 페이지에 100개씩 본다고 가정
        rows_per_page = 100
        last_page = math.ceil(total_count / rows_per_page)
        
        print(f">> 최신 데이터는 {last_page}페이지 근처에 있습니다. 역순 수색 시작!")
        
        target_saved = 0
        
        # 마지막 페이지부터 거꾸로 3페이지 정도 뒤짐 (최신 -> 과거 순)
        for page in range(last_page, last_page - 5, -1):
            if page < 1: break
            
            print(f"\n>> [API] {page}페이지 (최신구간) 스캔 중...")
            params = {
                'serviceKey': API_KEY,
                'pageNo': str(page),
                'numOfRows': str(rows_per_page),
                'type': 'xml'
            }
            
            res = requests.get(list_url, params=params, timeout=30)
            root = ET.fromstring(res.text)
            items = root.findall('.//item')
            
            if not items:
                print(">> 데이터 없음, 다음 페이지로...")
                continue
                
            # 페이지 내에서도 리스트가 오름차순일 수 있으니 역순으로 뒤집어서 확인
            for item in reversed(items):
                # 날짜 확인
                p_date = item.findtext('ITEM_PERMIT_DATE') or item.findtext('PERMIT_DATE')
                if not p_date: continue
                
                p_date_clean = p_date.replace("-", "").replace(".", "") # YYYYMMDD
                
                # 🎯 타겟 기간: 2026년 2월 1일 ~ 2026년 2월 14일
                # (너무 최신이라 미래 날짜가 찍힌 데이터가 있을 수도 있으니 시작일만 체크해도 됨)
                if p_date_clean >= "20260201":
                    item_seq = item.findtext('ITEM_SEQ')
                    product_name = item.findtext('ITEM_NAME')
                    
                    print(f"   -> [신규포착] {product_name} ({p_date_clean})")
                    
                    # [3단계] 상세 채우기
                    manufacturer, ingredients, efficacy = get_api_detail(item_seq)
                    
                    data = {
                        "item_seq": item_seq,
                        "product_name": product_name,
                        "company": item.findtext('ENTP_NAME'),
                        "manufacturer": manufacturer, 
                        "category": item.findtext('ETC_OTC_NAME') or "구분없음",
                        "approval_type": item.findtext('PRDUCT_TYPE_NAME') or "정상",
                        "ingredients": ingredients,
                        "efficacy": efficacy,
                        "approval_date": p_date,
                        "detail_url": f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
                    }
                    
                    supabase.table("drug_approvals").upsert(data).execute()
                    target_saved += 1
                    time.sleep(0.1)
                
                elif p_date_clean < "20260201":
                    # 2월 1일 이전 데이터가 나오기 시작하면 더 이상 볼 필요 없음 (수집 종료)
                    # 단, 페이지 내 정렬이 섞여있을 수 있으니 해당 페이지는 다 보는게 안전
                    pass

        print(f"\n=== 🏆 작전 대성공: 최신 데이터 {target_saved}건(목표 43건)을 확보했습니다! ===")

    except Exception as e:
        print(f"❌ 시스템 오류: {e}")

if __name__ == "__main__":
    main()
