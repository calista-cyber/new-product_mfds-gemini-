import os, time, json, requests, gspread

# 1. 설정
gcp_secret = os.environ.get("GCP_SERVICE_ACCOUNT")
sheet_id = os.environ.get("GOOGLE_SHEET_ID")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# 🌟 구글 시트 인증
gc = gspread.service_account_from_dict(json.loads(gcp_secret))
worksheet = gc.open_by_key(sheet_id).sheet1

def ask_chatgpt(name, company, category, ingredient):
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}", 
        "Content-Type": "application/json"
    }
    
    # 🌟 요약을 빼고 직관적인 약효 분류만 추출하도록 프롬프트를 다이어트했습니다.
    prompt = f"""
    당신은 제약 전문가입니다. 아래 타사 신규 허가 의약품 정보를 분석하여, 직관적인 치료제 용도(분류)를 JSON으로 답하세요.
    
    - 제품명: {name}
    - 업체명: {company}
    - 구분: {category}
    - 주성분: {ingredient}
    
    형식: 
    {{"category": "예: 간질환 치료제, 비뇨기계 치료제 등 (일반적인 약효 분류 명칭)"}}
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
    print("=== 🤖 ChatGPT 분석관 출근! (약효 분류 전용 모드) ===")
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
                # 🌟 요약 열(K열)이 지워졌으므로 J열(AI_분류) 단 한 칸만 업데이트합니다.
                worksheet.update(range_name=f"J{r_num}", values=[[res.get('category')]])
                print(f"      ✅ 시트 반영 완료!")
            except Exception as e:
                print(f"      ❌ 시트 쓰기 에러: {e}")
                
        time.sleep(1.5)

if __name__ == "__main__":
    main()
