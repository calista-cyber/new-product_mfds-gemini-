import os, time, json, requests, gspread
from google.oauth2.service_account import Credentials

# 1. 설정
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
gcp_secret = os.environ.get("GCP_SERVICE_ACCOUNT")
sheet_id = os.environ.get("GOOGLE_SHEET_ID")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

credentials = Credentials.from_service_account_info(json.loads(gcp_secret), scopes=scope)
gc = gspread.authorize(credentials)
worksheet = gc.open_by_key(sheet_id).sheet1

def ask_chatgpt(name, company, category, ingredient):
    """시트에 이미 수집된 핵심 정보(주성분 포함)를 GPT에게 주어 분석하게 합니다."""
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    
    prompt = f"""
    당신은 제약 전문가입니다. 아래 의약품 정보를 분석하여 '분류'와 '요약'을 JSON으로 답해 주세요.
    - 제품명: {name}
    - 업체명: {company}
    - 구분: {category}
    - 주성분: {ingredient}
    
    형식: {{"category": "예: 당뇨병 치료제", "summary": "예: 엠파글리플로진을 주성분으로 하는 제2형 당뇨병 치료제입니다."}}
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
    print("=== 🤖 ChatGPT 분석관 (주성분 활용 안전 모드) 출근! ===")
    records = worksheet.get_all_records()
    pending = []
    
    # AI_분류(J열)가 비어있는 행만 추출
    for idx, row in enumerate(records):
        if not str(row.get("AI_분류", "")).strip():
            pending.append({"row_num": idx + 2, "data": row})
    
    if not pending: return print(">> 모든 분석 완료 🎉")

    print(f">> 분석 대기: 총 {len(pending)}건")
    for item in pending:
        r_num, d = item["row_num"], item["data"]
        name = d.get('제품명', '')
        
        if not name: continue 
        
        print(f"   🧠 분석 중: [{name}]")
        # 주성분(C열) 정보까지 함께 넘겨줍니다.
        res = ask_chatgpt(name, d.get('업체명', ''), d.get('전문/일반구분', ''), d.get('주성분', ''))
        
        if res:
            try:
                worksheet.update(range_name=f"J{r_num}:K{r_num}", values=[[res.get('category'), res.get('summary')]])
                print(f"      ✅ 시트 반영 완료!")
            except Exception as e:
                print(f"      ❌ 시트 쓰기 에러: {e}")
                
        time.sleep(1.5) # 안전한 속도 조절

if __name__ == "__main__":
    main()
