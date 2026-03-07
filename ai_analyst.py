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
    prompt = f"의약품[{name}], 업체[{company}], 구분[{category}]를 분석해서 {{'category':'한줄분류', 'summary':'핵심요약'}} JSON으로만 답해."
    payload = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}], "response_format": {"type": "json_object"}}
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=25).json()
        return json.loads(res['choices'][0]['message']['content'])
    except: return None

def main():
    print("=== 🤖 ChatGPT 분석관 출근! ===")
    records = worksheet.get_all_records()
    pending = []
    for idx, row in enumerate(records):
        if not str(row.get("AI_분류", "")).strip():
            pending.append({"row_num": idx + 2, "data": row})
    
    if not pending: return print(">> 분석할 대기열 없음 🎉")

    print(f">> 분석 시작: 총 {len(pending)}건")
    for item in pending:
        r_num, d = item["row_num"], item["data"]
        print(f"   🧠 분석 중: [{d.get('제품명')}]")
        res = ask_chatgpt(d.get('제품명'), d.get('업체명'), d.get('전문/일반구분'))
        if res:
            # J열(10)과 K열(11)을 확실하게 동시 업데이트
            worksheet.update(range_name=f"J{r_num}:K{r_num}", values=[[res.get('category'), res.get('summary')]])
            print(f"      ✅ 시트 반영 완료! (J{r_num}, K{r_num})")
        time.sleep(2)

if __name__ == "__main__":
    main()
