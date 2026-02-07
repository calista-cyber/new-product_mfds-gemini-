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
    print("=== 🌟 션 팀장님 지시: 세션 획득 후 43건 정밀 타격 (재시도) ===")
    
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
