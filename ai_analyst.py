import os, time, json, requests, gspread
from google.oauth2.service_account import Credentials

# 1. 설정
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
gcp_secret = os.environ.get("GCP_SERVICE_ACCOUNT")
sheet_id = os.environ.get("GOOGLE_SHEET_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") # 🌟 제미니 키로 변경!

credentials = Credentials.from_service_account_info(json.loads(gcp_secret), scopes=scope)
gc = gspread.authorize(credentials)
worksheet = gc.open_by_key(sheet_id).sheet1

def ask_gemini(name, company, category, ingredient):
    """제미니 API를 활용한 안전한 JSON 분석 요청"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    
    prompt = f"""
    당신은 제약 전문가입니다. 아래 의약품 정보를 분석하여 '분류'와 '요약'을 JSON으로 답해 주세요.
    - 제품명: {name}
    - 업체명: {company}
    - 구분: {category}
    - 주성분: {ingredient}
    
    반드시 다음 JSON 형식만 출력하세요: {{"category": "예: 당뇨병 치료제", "summary": "예: 엠파글리플로진을 주성분으로 하는 제2형 당뇨병 치료제입니다."}}
    """
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"} # JSON 형태 강제
    }
    
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=25).json()
        if 'candidates' in res:
            text_result = res['candidates'][0]['content']['parts'][0]['text']
            return json.loads(text_result)
        else:
            print(f"      ❌ 제미니 거절: {res}")
            return None
    except Exception as e:
        print(f"      ❌ 통신 에러: {e}")
        return None

def main():
    print("=== 🤖 제미니 분석관 출근! ===")
    records = worksheet.get_all_records()
    pending = []
    
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
        res = ask_gemini(name, d.get('업체명', ''), d.get('전문/일반구분', ''), d.get('주성분', ''))
        
        if res:
            try:
                worksheet.update(range_name=f"J{r_num}:K{r_num}", values=[[res.get('category'), res.get('summary')]])
                print(f"      ✅ 시트 반영 완료!")
            except Exception as e:
                print(f"      ❌ 시트 쓰기 에러: {e}")
        time.sleep(2) # 무료 API 한도 보호를 위한 대기

if __name__ == "__main__":
    main()
