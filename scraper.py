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
    """
    [상세 API] 진짜 허가일자 및 상세정보 조회
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
    print("=== 🌟 션 팀장님 힌트 적용: '2026 코드' 초고속 타격 작전 ===")
    
    list_url = "http://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService07/getDrugPrdtPrmsnInq07"
    
    # [1단계] 마지막 페이지 찾기 (최신 데이터 위치)
    print(">> [정찰] 데이터 끝 페이지 계산 중...")
    try:
        res = requests.get(list_url, params={'serviceKey': API_KEY, 'numOfRows': '1', 'type': 'xml'}, timeout=10)
        total_count = int(ET.fromstring(res.text).findtext('.//totalCount'))
        last_page = math.ceil(total_count / 100)
        print(f">> 총 {total_count}건. 최신 데이터는 {last_page}페이지부터 탐색합니다.")
    except Exception as e:
        print(f"❌ 접속 실패: {e}")
        return

    target_saved = 0
    stop_signal = False

    # [2단계] 마지막 페이지부터 역순으로 탐색
    # (최신 -> 과거 순으로 가다가 '2025'가 쏟아지면 멈춤)
    for page in range(last_page, 0, -1):
        if stop_signal: break
        
        print(f"\n>> [스캔] {page}페이지 분석 중 (2026년 타겟)...")
        
        try:
            params = {'serviceKey': API_KEY, 'pageNo': str(page), 'numOfRows': '100', 'type': 'xml'}
            res = requests.get(list_url, params=params, timeout=30)
            items = ET.fromstring(res.text).findall('.//item')
            
            if not items: continue

            # 최신순(역순)으로 검사
            count_2025_below = 0 # 2025년 이하 데이터 카운트
            
            for item in reversed(items):
                # 힌트 적용: 품목기준코드(PRDLST_STDR_CODE)의 앞 4자리가 연도!
                code = item.findtext('PRDLST_STDR_CODE') or item.findtext('ITEM_SEQ') or ""
                year_prefix = code[:4]
                
                # 1. 2026년 코드인 경우 -> 상세 조회 후 저장 (잠재적 타겟)
                if year_prefix == "2026":
                    item_seq = item.findtext('ITEM_SEQ')
                    product_name = item.findtext('ITEM_NAME')
                    
                    # 상세 API로 '진짜 날짜(월/일)' 확인
                    detail = get_detail_info(item_seq)
                    if not detail or not detail['date']: continue
                    
                    real_date = detail['date'].replace("-", "").replace(".", "")
                    
                    # 🎯 최종 타겟: 2026년 2월 1일 ~ 2월 14일
                    if "20260201" <= real_date <= "20260214":
                        print(f"   -> [🎯포착] {product_name} (코드:{code}, 일자:{real_date})")
                        
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
                    else:
                        # 2026년이지만 1월 데이터인 경우 -> 패스
                        pass

                # 2. 2025년 이하 코드인 경우 -> 카운트 증가
                elif year_prefix.isdigit() and int(year_prefix) <= 2025:
                    count_2025_below += 1

            # 한 페이지(100개) 안에 2025년 이하 데이터가 80개 이상이면?
            # -> 이제 2026년 구간은 끝났다고 판단하고 종료 (조기 퇴근)
            if count_2025_below >= 80:
                print(f">> 2025년 데이터({count_2025_below}건)가 주류입니다. 수집을 종료합니다.")
                stop_signal = True
                break

        except Exception as e:
            print(f"⚠️ 에러 발생: {e}")
            continue

    print(f"\n=== 🏆 작전 종료: 총 {target_saved}건(목표 43건) 정밀 타격 완료! ===")

if __name__ == "__main__":
    main()
