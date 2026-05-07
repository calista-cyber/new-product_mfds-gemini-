import os, time, json, requests, gspread
from bs4 import BeautifulSoup

# 1. 설정
gcp_secret = os.environ.get("GCP_SERVICE_ACCOUNT")
sheet_id = os.environ.get("GOOGLE_SHEET_ID")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# 구글 시트 인증
gc = gspread.service_account_from_dict(json.loads(gcp_secret))
doc = gc.open_by_key(sheet_id)
worksheet = doc.sheet1

# ==========================================
# 🎯 [관리자 설정] 타겟 카테고리 (AI 분류 가이드라인)
TARGET_CATEGORIES = "정장제, 간질환 치료제, 위장관 치료제, 치매 치료제, 고혈압 치료제, 비타민D 유도체, 호흡기계 치료제, 제산제, 감기 치료제, 비뇨기 치료제, 비타민 및 미네랄 보충제, 고지혈 치료제, ADHD 치료제, 당뇨병 치료제, 탈모 치료제, 항암제, 항혈전제/응고제, 순환기계 복합제"
# ==========================================

def get_fixed_mapping():
    """구글 시트의 '매핑사전' 탭에서 고정 규칙을 읽어옵니다."""
    try:
        mapping_ws = doc.worksheet("매핑사전")
        data = mapping_ws.get_all_records()
        mapping_dict = { str(row['성분명']).strip(): str(row['분류명']).strip() for row in data if row.get('성분명') }
        print(f"📚 매핑사전 로드 완료: {len(mapping_dict)}개 규칙 적용")
        return mapping_dict
    except Exception as e:
        print(f"⚠️ '매핑사전' 탭을 찾을 수 없거나 데이터가 비어있습니다. (Error: {e})")
        return {}

def extract_efficacy_text(url):
    """상세링크에서 웹페이지 텍스트를 추출합니다."""
    if not url or not str(url).startswith('http'):
        return ""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')
        text = soup.get_text(separator=' ', strip=True)
        return text[:1500] # API 토큰 낭비 방지를 위해 최대 1500자 제한
    except Exception as e:
        print(f"      ⚠️ 링크 텍스트 수집 실패: {e}")
        return ""

def ask_chatgpt(name, company, category, ingredient, efficacy_text=""):
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}", 
        "Content-Type": "application/json"
    }
    
    prompt = f"""
    당신은 대한민국 제약 전문가입니다. 아래 의약품의 '주성분' 기전을 분석하여 정확한 효능군을 JSON으로 답하세요.

    [분류 규칙]
    1. 최우선적으로 아래 <지정 카테고리> 목록에서 가장 알맞은 1개를 선택하세요.
    <지정 카테고리>: {TARGET_CATEGORIES}
    2. 목록에 없다면 표준 의학 용어로 15자 이내의 분류명을 생성하세요. (예: 간질환 치료제, 항혈전제/응고제 등)
    3. 복합제인 경우 대표적인 효능군 하나만 선택하세요.

    [의약품 정보]
    - 제품명: {name} / 주성분: {ingredient}
    """
    
    # 신약/자료제출의약품/유전자치료제인 경우 추출된 효능효과 데이터를 프롬프트에 추가
    if efficacy_text:
        prompt += f"\n- [중요 분석 조건]: 이 의약품은 신약, 유전자치료제 또는 자료제출의약품입니다. 아래 실제 효능효과 텍스트를 분석하여 분류의 최우선 근거로 삼으세요.\n[효능효과 데이터]: {efficacy_text}\n"
    
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
    print("=== 🤖 하이브리드 AI 분석관 가동 (효능효과 정밀 분석 모드) ===")
    
    FIXED_MAPPING = get_fixed_mapping()
    
    records = worksheet.get_all_records()
    pending = [{"row_num": i + 2, "data": r} for i, r in enumerate(records) if not str(r.get("AI_분류", "")).strip()]
    
    if not pending: return print(">> 모든 데이터가 이미 분류되어 있습니다.")

    print(f">> 분석 시작: 총 {len(pending)}건")
    
    session_cache = {}

    for item in pending:
        r_num, d = item["row_num"], item["data"]
        name = d.get('제품명', '')
        ingredient = str(d.get('주성분', '')).strip()
        approval_type = str(d.get('허가심사유형', '')).strip()
        detail_link = str(d.get('상세링크', '')).strip()

        if not name: continue 

        final_cat = None

        # 1. 시트 매핑사전 확인
        for key, val in FIXED_MAPPING.items():
            if key in ingredient:
                final_cat = val
                print(f"   ⚡ [사전 적용] {name} -> {final_cat}")
                break
        
        # 2. 세션 캐시 확인
        if not final_cat and ingredient in session_cache:
            final_cat = session_cache[ingredient]
            print(f"   ♻️ [캐시 재사용] {name} -> {final_cat}")

        # 3. AI 분석 진행
        if not final_cat:
            print(f"   🧠 [AI 분석 중] {name} (유형: {approval_type})...")
            
            efficacy_text = ""
            if ("신약" in approval_type or "자료제출의약품" in approval_type or "유전자치료제" in approval_type) and detail_link:
                print(f"      🔗 상세링크 텍스트 스크래핑 진행 중... (유형: {approval_type})")
                efficacy_text = extract_efficacy_text(detail_link)

            res = ask_chatgpt(name, d.get('업체명', ''), d.get('전문/일반구분', ''), ingredient, efficacy_text)
            if res:
                final_cat = res.get('category')
                session_cache[ingredient] = final_cat 

        # 4. 결과 업데이트
        if final_cat:
            try:
                worksheet.update(range_name=f"J{r_num}", values=[[final_cat]])
            except Exception as e:
                print(f"      ❌ 시트 쓰기 실패: {e}")
        
        time.sleep(1.5) # 스크래핑 및 API 호출 부하 방지

    print(">> 모든 분석 및 업데이트 완료!")

if __name__ == "__main__":
    main()
