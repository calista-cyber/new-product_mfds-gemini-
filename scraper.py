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
        
        # HTML 태그 제거 (깔끔하게 텍스트만 추출)
        efficacy = BeautifulSoup(efficacy_raw, "html.parser").get_text()[:500]

        return manufacturer, ingredients, efficacy

    except Exception:
        return "조회실패", "조회실패", "조회실패"

def main():
    print("=== 🌟 션 팀장님 지시: 세션 획득 후 43건 정밀 타격 (최종) ===")
    
    # 세션 유지를 위한 객체 생성
    session = requests.Session()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Referer': 'https://nedrug.mfds.go.kr/pbp/CCBAE01'
    }
    
    # [1단계] 메인 페이지 먼저 방문하여 '입장권(Cookie)' 획득
    print(">> [입장] 식약처 로비(메인페이지)에서 통행증 발급 중...")
    try:
        session.get("https://nedrug.mfds.go.kr/pbp/CCBAE01", headers=headers, timeout=30)
        time.sleep(1) # 도장 찍는 시간 대기
    except Exception as e:
        print(f"⚠️ 메인 페이지 접속 실패: {e}")
        return

    # [2단계] 팀장님이 확인하신 파라미터 그대로 목록 요청
    target_url = "https://nedrug.mfds.go.kr/pbp/CCBAE01/getItemPermitIntro"
    total_saved = 0
    
    # 43건이면 넉넉히 1~5페이지 스캔
    for page in range(1, 6): 
        print(f"\n>> [Web] {page}페이지 목록 스캔 중...")
        
        # 팀장님의 브라우저 URL 파라미터 완벽 복제
        params = {
            'page': page,
            'limit': '10',
            'sort': '',
            'sortOrder': 'true',
            'searchYn': 'true',
            'sDateGb': 'date',
            'sYear': '2026',
            'sMonth': '2',
            'sWeek': '2', 
            'sPermitDateStart': '2026-02-01', # 팀장님 설정 날짜
            'sPermitDateEnd': '2026-02-14',   # 팀장님 설정 날짜
            'btnSearch': '',
            'garaInputBox': '' 
        }

        try:
            # 세션(입장권)을 들고 GET 요청
            res = session.get(target_url, params=params, headers=headers, timeout=30)
            soup = BeautifulSoup(res.text, 'html.parser')
            rows = soup.select('table.board_list tbody tr')

            if not rows or "데이터가" in rows[0].text:
                print(">> 더 이상 데이터가 없습니다. (수집 종료)")
                break

            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 5: continue

                product_name = cols[1].text.strip()
                # onclick에서 번호 추출
                try:
                    item_seq = cols[1].find('a')['onclick'].split("'")[1]
                except:
                    continue
                
                print(f"   -> [발견] {product_name} ({item_seq})")
                
                # [3단계] API로 빈칸(성분/제조원) 채우기
                manufacturer, ingredients, efficacy = get_api_detail(item_seq)

                data = {
                    "item_seq": item_seq,
                    "product_name": product_name,
                    "company": cols[2].text.strip(),
                    "manufacturer": manufacturer, 
                    "category": "전문의약품" if "전문" in product_name else "일반의약품",
                    "approval_type": "정상",
                    "ingredients": ingredients,
                    "efficacy": efficacy,
                    "approval_date": cols[3].text.strip(),
                    "detail_url": f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
                }
                
                # Supabase에 저장
                supabase.table("drug_approvals").upsert(data).execute()
                total_saved += 1
                time.sleep(0.1) # 서버 부하 방지

        except Exception as e:
            print(f"⚠️ 페이지 처리 중 에러: {e}")
            continue

    print(f"\n=== 🏆 작전 대성공: 목표하신 43건 중 {total_saved}건을 금고에 넣었습니다! ===")

if __name__ == "__main__":
    main()
