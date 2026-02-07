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
    print("=== 🌟 션 팀장님 전략: '2026 트리거' 스마트 탐색 가동 ===")
    
    list_url = "http://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService07/getDrugPrdtPrmsnInq07"
    
    # [1단계] 끝 페이지 계산
    print(">> [정찰] 전체 데이터 규모 확인 중...")
    try:
        res = requests.get(list_url, params={'serviceKey': API_KEY, 'numOfRows': '1', 'type': 'xml'}, timeout=10)
        total_count = int(ET.fromstring(res.text).findtext('.//totalCount'))
        last_page = math.ceil(total_count / 100)
        print(f">> 총 {total_count}건. 마지막 {last_page}페이지부터 역순으로 훑습니다.")
    except:
        print("❌ API 접속 실패")
        return

    target_saved = 0
    
    # 상태 변수들
    found_2026_trigger = False  # 2026년을 한번이라도 찾았는지?
    consecutive_old_count = 0   # 연속으로 옛날 데이터가 나온 횟수

    # [2단계] 역순 스캔 (마지막 페이지 -> 1페이지)
    # 넉넉하게 뒤에서부터 30페이지를 봅니다 (하지만 트리거 로직으로 조기 종료 가능)
    for page in range(last_page, last_page - 30, -1):
        if page < 1: break
        
        # 종료 조건: 2026년을 찾은 후에, 옛날 데이터만 200개 연속으로 나오면 "진짜 끝"으로 간주
        if found_2026_trigger and consecutive_old_count >= 200:
            print(f"\n>> 🛑 [종료] 2026년 데이터 확보 후, 2025년 데이터가 {consecutive_old_count}건 연속 발견됨.")
            print(">> 더 이상의 최신 데이터는 없다고 판단하여 퇴근합니다.")
            break

        print(f"\n>> [스캔] {page}페이지 분석 중... (연속 구형 데이터: {consecutive_old_count}건)")
        
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
                
                # [상황 A] 2026년 데이터 발견!
                if year_prefix == "2026":
                    found_2026_trigger = True  # 트리거 발동! (이제부터 집중)
                    consecutive_old_count = 0  # 옛날 데이터 카운트 리셋 (섞여있을 수 있으므로)
                    
                    item_seq = item.findtext('ITEM_SEQ')
                    product_name = item.findtext('ITEM_NAME')
                    
                    # 상세 API로 정밀 검증
                    detail = get_detail_info(item_seq)
                    if not detail or not detail['date']: continue
                    
                    real_date = detail['date'].replace("-", "").replace(".", "")
                    
                    # 🎯 타겟: 2월 1일 ~ 2월 14일
                    if "20260201" <= real_date <= "20260214":
                        print(f"   -> [🎯보물확보] {product_name} ({real_date})")
                        
                        data = {
                            "item_seq": item_seq,
                            "product_name": product_name,
                            "company": item.findtext('ENTP_NAME'),
                            "manufacturer": detail['manu'],
                            "category": item.findtext('SPCLTY_PBLC') or "구분없음",
                            "approval_type": item.findtext('PRDUCT_TYPE_NAME') or "정상",
                            "ingredients": detail['ingr'],
                            "efficacy": detail['effi'],
