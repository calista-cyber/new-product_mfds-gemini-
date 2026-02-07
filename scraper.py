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

def get_detail_and_date(item_seq):
    """ [상세 API] 날짜 및 상세 정보 조회 """
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

def scan_range(start_page, end_page, list_url):
    """ 지정된 페이지 범위를 스캔하여 저장 (저장된 개수 반환) """
    saved_count = 0
    # start부터 end까지 (순방향 또는 역방향)
    step = 1 if start_page <= end_page else -1
    
    # range의 끝은 포함되지 않으므로 조정
    for page in range(start_page, end_page + step, step):
        if page < 1: continue
        
        print(f">> [스캔] {page}페이지 데이터를 분석합니다...")
        try:
            params = {'serviceKey': API_KEY, 'pageNo': str(page), 'numOfRows': '100', 'type': 'xml'}
            res = requests.get(list_url, params=params, timeout=30)
            items = ET.fromstring(res.text).findall('.//item')
            
            if not items: continue

            # 한 페이지 내의 아이템 전수 검사
            for item in items:
                item_seq = item.findtext('ITEM_SEQ')
                product_name = item.findtext('ITEM_NAME')
                
                # 상세 조회로 날짜 확인
                detail = get_detail_and_date(item_seq)
                if not detail or not detail['date']: continue
                
                real_date = detail['date'].replace("-", "").replace(".", "")
                
                # 🎯 타겟: 2026년 2월 1일 ~ 2월 14일 (멈추지 않고 계속 찾음)
                if "20260201" <= real_date <= "20260214":
                    print(f"   -> [포착!] {product_name} ({real_date})")
                    
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
                    saved_count += 1
                    time.sleep(0.05) # API 매너 호출
                    
        except Exception as e:
            print(f"⚠️ {page}페이지 에러: {e}")
            continue
            
    return saved_count

def main():
    print("=== 🌟 션 팀장님 지시: '양동작전' (앞뒤 전수조사) 시작 ===")
    list_url = "http://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService07/getDrugPrdtPrmsnInq07"
    
    # [1단계] 전체 페이지 수 계산
    print(">> [정찰] 전체 데이터 규모 파악 중...")
    try:
        res = requests.get(list_url, params={'serviceKey': API_KEY, 'numOfRows': '1', 'type': 'xml'}, timeout=10)
        total_count = int(ET.fromstring(res.text).findtext('.//totalCount'))
        last_page = math.ceil(total_count / 100)
        print(f">> 총 {total_count}건 (약 {last_page}페이지)")
    except:
        print("❌ API 접속 실패")
        return

    total_saved = 0

    # [2단계] 뒷문 공략 (마지막 5페이지: 보통 여기에 최신 데이터가 있음)
    # 뒤죽박죽 섞여있을 수 있으니 넉넉하게 뒤에서 10페이지 검사
    print("\n🚀 [작전1] 뒷문 공략 (최신 데이터 추정 구역)")
    total_saved += scan_range(last_page, last_page - 10, list_url)

    # [3단계] 앞문 공략 (처음 5페이지: 혹시 역순 정렬일 경우 대비)
    print("\n🚀 [작전2] 앞문 공략 (혹시 모를 역순 대비)")
    total_saved += scan_range(1, 5, list_url)

    print(f"\n=== 🏆 작전 종료: 총 {total_saved}건(목표 43건) 확보 완료! ===")

if __name__ == "__main__":
    main()
