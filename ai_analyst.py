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

def ask_chatgpt(name, company, category):
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    prompt = f"의약품[{name}], 업체[{company}], 구분[{category}] 정보를 기반으로 전문적인 한줄분류와 핵심요약을 JSON으로 작성해. 형식: {{'category':'분류', 'summary':'요약'}}"
    
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
        "response_format": { "type": "json_object" }
    }
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=25).json()
        return json.loads(res['choices'][0]['message']['content'])
    except: return None

def main():
    print("=== 🤖 ChatGPT 분석관 가동! ===")
    records = worksheet.get_all_records()
    
    # AI_분류(J열)가 비어있는 행만 정확히 타겟팅
    pending = []
    for idx, row in enumerate(records):
        if not str(row.get("AI_분류", "")).strip():
            pending.append({"row_num": idx + 2, "data": row})
    
    if not pending: return print(">> 모든 분석이 완료되었습니다! 🎉")

    print(f">> 분석 대기: {len(pending)}건")
    for item in pending:
        r_num, d = item["row_num"], item["data"]
        name = d.get('제품명', '이름없음')
        
        print(f"   🧠 분석 중: [{name}] (행:{r_num})")
        res = ask_chatgpt(name, d.get('업체명', ''), d.get('전문/일반구분', ''))
        
        if res:
            # J열과 K열을 한꺼번에 업데이트하여 확실하게 기록
            try:
                worksheet.update(f"J{r_num}:K{r_num}", [[res.get('category'), res.get('summary')]])
                print(f"      ✅ 시트 업데이트 성공! (J{r_num}, K{r_num})")
            except Exception as e:
                print(f"      ❌ 시트 기록 에러: {e}")
        
        time.sleep(2) # 안정성을 위해 2초 대기

if __name__ == "__main__":
    main()
