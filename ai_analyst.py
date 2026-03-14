import os, time, json, requests, gspread

# 1. 설정
gcp_secret = os.environ.get("GCP_SERVICE_ACCOUNT")
sheet_id = os.environ.get("GOOGLE_SHEET_ID")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# 🌟 구글 시트 인증
gc = gspread.service_account_from_dict(json.loads(gcp_secret))
worksheet = gc.open_by_key(sheet_id).sheet1

# ==========================================
# 🎯 [관리자 설정] AI가 최우선으로 선택할 지정 카테고리 목록
# 팀장님! 나중에 새로운 분류가 필요해지면 이 따옴표 안에 쉼표(,)로 연결해서 계속 추가하시면 됩니다!
TARGET_CATEGORIES = "정장제, 간질환 치료제, 위장관 치료제, 치매 치료제, 고혈압 치료제, 비타민D 유도체, 호흡기계 치료제, 제산제, 감기 치료제, 비뇨기 치료제, 비타민 및 미네랄 보충제, 고지혈 치료제, ADHD 치료제, 당뇨병 치료제, 탈모 치료제, 항암제"
# ==========================================

def ask_chatgpt(name, company, category, ingredient):
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}", 
        "Content-Type": "application/json"
    }
    
    # 🌟 팀장님의 리스트를 적용한 하이브리드 객관식+주관식 프롬프트
    prompt = f"""
    당신은 제약 전문가입니다. 아래 신규 허가 의약품 정보를 분석하여, 가장 적합한 약효 분류(효능군)를 JSON으로 답하세요.

    [분류 규칙]
    1. 최우선적으로 아래의 <지정 카테고리> 중에서 가장 알맞은 것을 딱 1개만 골라서 출력하세요.
    <지정 카테고리>: {TARGET_CATEGORIES}
    
    2. 만약 위 <지정 카테고리> 중에 적합한 것이 확실히 없다면, 전문가로서 알맞은 새로운 일반적인 효능군 명칭을 15자 이내로 직접 생성해서 출력하세요.

    [의약품 정보]
    - 제품명: {name}
    - 업체명: {company}
    - 구분: {category}
    - 주성분: {ingredient}
    
    형식: 
    {{"category": "선택하거나 생성한 분류명 딱 1개"}}
    """
    
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"}
    }
    
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=25).json()
        if 'choices' in res:
            return json.loads(res['choices'][0]['message']['content'])
        else:
            print(f"      ❌ GPT 응답 거절: {res}")
            return None
    except Exception as e:
        print(f"      ❌ 통신 에러: {e}")
        return None

def main():
    print("=== 🤖 ChatGPT 분석관 출근! (객관식 하이브리드 모드) ===")
    records = worksheet.get_all_records()
    pending = []
    
    for idx, row in enumerate(records):
        if not str(row.get("AI_분류", "")).strip():
            pending.append({"row_num": idx + 2, "data": row})
    
    if not pending: return print(">> 모든 분류 완료 🎉")

    print(f">> 분류 대기: 총 {len(pending)}건")
    for item in pending:
        r_num, d = item["row_num"], item["data"]
        name = d.get('제품명', '')
        if not name: continue 
        
        print(f"   🧠 약효 분류 중: [{name}]")
        res = ask_chatgpt(name, d.get('업체명', ''), d.get('전문/일반구분', ''), d.get('주성분', ''))
        
        if res:
            try:
                worksheet.update(range_name=f"J{r_num}", values=[[res.get('category')]])
                print(f"      ✅ 시트 반영 완료! (분류: {res.get('category')})")
            except Exception as e:
                print(f"      ❌ 시트 쓰기 에러: {e}")
                
        time.sleep(1.5)

if __name__ == "__main__":
    main()
