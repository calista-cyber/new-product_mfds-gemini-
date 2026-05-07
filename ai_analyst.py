import os, time, json, requests, gspread, re

# 1. 환경 변수 설정
gcp_secret = os.environ.get("GCP_SERVICE_ACCOUNT")
sheet_id = os.environ.get("GOOGLE_SHEET_ID")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
MFDS_API_KEY = os.environ.get("MFDS_API_KEY")

# 구글 시트 인증
gc = gspread.service_account_from_dict(json.loads(gcp_secret))
doc = gc.open_by_key(sheet_id)
worksheet = doc.sheet1

# [관리자 설정] 분류 가이드라인
TARGET_CATEGORIES = "정장제, 간질환 치료제, 위장관 치료제, 치매 치료제, 고혈압 치료제, 비타민D 유도체, 호흡기계 치료제, 제산제, 감기 치료제, 비뇨기 치료제, 비타민 및 미네랄 보충제, 고지혈 치료제, ADHD 치료제, 당뇨병 치료제, 탈모 치료제, 항암제, 항혈전제/응고제, 순환기계 복합제"

def get_fixed_mapping():
    try:
        mapping_ws = doc.worksheet("매핑사전")
        data = mapping_ws.get_all_records()
        return { str(row['성분명']).strip(): str(row['분류명']).strip() for row in data if row.get('성분명') }
    except:
        return {}

def get_efficacy_from_mfds_api(item_seq, item_name):
    """품목기준코드를 우선 사용하여 식약처 공식 효능효과 데이터를 가져옵니다."""
    if not MFDS_API_KEY:
        print("      ⚠️ MFDS_API_KEY 미설정")
        return ""
    
    url = "http://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService05/getDrugPrdtPrmsnInq05"
    
    # 품목기준코드가 있으면 seq로 검색, 없으면 제품명으로 검색
    params = {
        "serviceKey": MFDS_API_KEY,
        "type": "json",
        "numOfRows": 1,
        "pageNo": 1
    }
    
    if item_seq:
        params["item_seq"] = item_seq
    else:
        params["item_name"] = item_name
    
    try:
        res = requests.get(url, params=params, timeout=15)
        data = res.json()
        items = data.get('body', {}).get('items', [])
        
        if items:
            # EE_DOC_DATA (효능효과) 추출 및 정제
            raw_efficacy = items[0].get('EE_DOC_DATA', '')
            clean_text = re.sub(r'<[^>]*>', ' ', raw_efficacy) # XML 태그 제거
            return ' '.join(clean_text.split())[:2000]
        return ""
    except Exception as e:
        print(f"      ❌ API 호출 실패: {e}")
        return ""

def ask_chatgpt(name, ingredient, efficacy_text=""):
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    
    prompt = f"""
    당신은 대한민국 제약 전문가입니다. 아래 의약품 정보를 분석하여 정확한 효능군을 JSON으로 답하세요.

    [분류 규칙]
    1. <지정 카테고리> 목록에서 가장 알맞은 1개를 선택하세요.
    <지정 카테고리>: {TARGET_CATEGORIES}
    2. 목록에 없다면 표준 의학 용어로 15자 이내의 분류명을 생성하세요.
    3. 복합제인 경우 대표적인 효능군 하나만 선택하세요.

    [의약품 정보]
    - 제품명: {name} / 주성분: {ingredient}
    """
    
    if efficacy_text:
        prompt += f"\n- [공식 효능효과]: {efficacy_text}\n(이 데이터를 최우선 근거로 분류하세요.)"
    
    prompt += '\n형식: {"category": "분류명"}'
    
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"}
    }
    
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=25).json()
        return json.loads(res['choices'][0]['message']['content'])
    except:
        return None

def main():
    print("=== 🤖 품목기준코드 기반 정밀 분석 가동 ===")
    
    FIXED_MAPPING = get_fixed_mapping()
    records = worksheet.get_all_records()
    pending = [{"row_num": i + 2, "data": r} for i, r in enumerate(records) if not str(r.get("AI_분류", "")).strip()]
    
    if not pending: return print(">> 모든 데이터 분류 완료")

    session_cache = {}

    for item in pending:
        r_num, d = item["row_num"], item["data"]
        name = d.get('제품명', '')
        ingredient = str(d.get('주성분', '')).strip()
        approval_type = str(d.get('허가심사유형', '')).strip()
        item_seq = str(d.get('품목기준코드', '')).strip() # 시트에서 코드 추출
        
        if not name: continue 

        final_cat = None

        # 1. 매핑 사전 확인
        for key, val in FIXED_MAPPING.items():
            if key in ingredient:
                final_cat = val
                break
        
        # 2. 세션 캐시 확인
        if not final_cat and ingredient in session_cache:
            final_cat = session_cache[ingredient]

        # 3. API 기반 정밀 분석
        if not final_cat:
            print(f"   🧠 [분석 중] {name} (코드: {item_seq})...")
            
            efficacy_text = ""
            special_types = ["신약", "자료제출의약품", "희귀", "유전자치료제"]
            if any(t in approval_type for t in special_types):
                efficacy_text = get_efficacy_from_mfds_api(item_seq, name)

            res = ask_chatgpt(name, ingredient, efficacy_text)
            if res:
                final_cat = res.get('category')
                session_cache[ingredient] = final_cat

        # 4. 시트 업데이트
        if final_cat:
            try:
                worksheet.update(range_name=f"J{r_num}", values=[[final_cat]])
                print(f"      ✅ 완료: {final_cat}")
            except Exception as e:
                print(f"      ❌ 업데이트 실패: {e}")
        
        time.sleep(1)

    print(">> 분석 완료")

if __name__ == "__main__":
    main()
