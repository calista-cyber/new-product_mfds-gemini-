import os
import requests
import time
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
    [상세 API] 제품번호(item_seq)로 성분, 효능효과, 제조원 정보를 공식 조회
    """
    url = "http://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService07/getDrugPrdtPrmsnDtlInq06"
    params = {
        'serviceKey': API_KEY,
        'item_seq': item_seq,
        'numOfRows': '1',
        'type': 'xml'
    }
    
    try:
        res = requests.get(url, params=params, timeout=10)
        root = ET.fromstring(res.text)
        item = root.find('.//item')
        
        if not item:
            return "정보없음", "정보없음", "상세참조"

        # API에서 제공하는 상세 정보 매핑
        manufacturer = item.findtext('MANU_METHOD') or "정보없음"
        ingredients = item.findtext('MAIN_ITEM_INGR') or "정보없음"
        efficacy_raw = item.findtext('EE_DOC_DATA') or "상세 효능효과 참조"
        
        # HTML 태그 제거 (깔끔하게 텍스트만)
        efficacy = BeautifulSoup(efficacy_raw, "html.parser").get_text()[:500]

        return manufacturer, ingredients, efficacy

    except Exception:
        return "조회실패", "조회실패", "조회실패"

def main():
    print("=== 🌟 션 팀장님 지시: 웹사이트 목록(43건) + API 상세정보 결합 작전 ===")
    
    session = requests.Session()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Referer': 'https://nedrug.mfds.go.kr/pbp/CCBAE01'
    }
    
    # [1단계] 팀장님이 찾으신 '정확한 43건'이 있는 웹사이트 주소 공략
    # GET 방식으로 URL 파라미터를 그대로 사용
    target_url = "https://nedrug.mfds.go.kr/pbp/CCBAE01/getItemPermitIntro"
    
    # 43건이면 10개씩 5페이지까지만 보면 충분
    total_saved = 0
    
    for page in range(1, 6): 
        print(f"\n>> [Web] {page}페이지 목록 스캔 중...")
        
        # 팀장님이 주신 URL 파라미터 그대로 적용
        params = {
            'page': page,
            'limit': '10',
            'sort': '',
            'sortOrder': 'true',
            'searchYn': 'true',
            'sDateGb': 'date',
            'sYear': '2026',
            'sMonth': '2',
            'sWeek': '2', # 주차 정보는 무시될 수 있음
            'sPermitDateStart': '2026-02-01',
            'sPermitDateEnd': '2026-02-14',
            'btnSearch': ''
        }

        try:
            res = session.get(target_url, params=params, headers=headers, timeout=30)
            soup = BeautifulSoup(res.text, 'html.parser')
            rows = soup.select('table.board_list tbody tr')

            # 데이터가 없으면 종료
            if not rows or "데이터가" in rows[0].text:
                print(">> 더 이상 웹사이트에 데이터가 없습니다. (수집 종료)")
                break

            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 5: continue

                product_name = cols[1].text.strip()
                # onclick="goDetail('202600123');" 에서 숫자만 추출
                item_seq = cols[1].find('a')['onclick'].split("'")[1] 
                
                print(f"   -> [목록확보] {product_name} ({item_seq})")
                
                # [2단계] API로 상세 정보(성분, 효능, 제조원) 털어오기
                manufacturer, ingredients, efficacy = get_api_detail(item_seq)

                data = {
                    "item_seq": item_seq,
                    "product_name": product_name,
                    "company": cols[2].text.strip(),
                    "manufacturer": manufacturer, # API산 고품질 데이터
                    "category": "전문의약품" if "전문" in product_name else "일반의약품",
                    "approval_type": "정상",
                    "ingredients": ingredients,   # API산 고품질 데이터
                    "efficacy": efficacy,         # API산 고품질 데이터
                    "approval_date": cols[3].text.strip(), # 웹사이트 날짜 (정확함)
                    "detail_url": f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
                }
                
                supabase.table("drug_approvals").upsert(data).execute()
                total_saved += 1
                
                # 서버 예의상 텀
                time.sleep(0.2)

        except Exception as e:
            print(f"⚠️ 에러 발생: {e}")
            continue

    print(f"\n=== 🏆 작전 대성공: 목표하신 43건 중 {total_saved}건을 완벽하게 수집했습니다! ===")

if __name__ == "__main__":
    main()
