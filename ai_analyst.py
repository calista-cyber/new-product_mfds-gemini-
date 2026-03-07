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

def ask_chatgpt(name, ingr, rv):
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    
    prompt = f"약품[{name}], 성분[{ingr}], 유형[{rv}] 분석해서 {{'category':'분류', 'summary':'요약'}} JSON으로 답해."
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
        "response_format": { "type": "json_object" }
    }
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=15).json()
        return json.loads(res['choices'][0]['message']['content'])
    except: return None

def main():
    print("=== 🤖 ChatGPT 분석관 출근! ===")
    records = worksheet.get_all_records()
    pending = [{"row": i+2, "data": r} for i, r in enumerate(records) if not str(r.get("AI_분류")).strip()]
    
    if not pending: return print(">> 분석할 대기열 없음 🥳")

    for item in pending:
        row_num, data = item["row"], item["data"]
        print(f"   🧠 GPT 분석 중: [{data.get('제품명')}]")
        res = ask_chatgpt(data.get('제품명'), data.get('주성분'), data.get('허가심사유형'))
        if res:
            worksheet.update_cell(row_num, 10, res.get('category'))
            worksheet.update_cell(row_num, 11, res.get('summary'))
            print("      ✅ 업데이트 성공!")
        time.sleep(1)

if __name__ == "__main__":
    main()
