import os
import time
import json
import gspread
import google.generativeai as genai
from google.oauth2.service_account import Credentials

# 1. 설정
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
gcp_secret = os.environ.get("GCP_SERVICE_ACCOUNT")
sheet_id = os.environ.get("GOOGLE_SHEET_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# 구글 시트 연결
credentials = Credentials.from_service_account_info(json.loads(gcp_secret), scopes=scope)
gc = gspread.authorize(credentials)
worksheet = gc.open_by_key(sheet_id).sheet1

# 🌟 [공식 도구 설정] 404 에러 없는 안전한 방식
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

def ask_gemini(product_name, ingredients, review_type):
    prompt = f"""
    당신은 제약 전문가입니다. 다음 약품을 분석해서 JSON으로 답하세요.
    제품명: {product_name}
    성분: {ingredients}
    유형: {review_type}
    응답형식: {{"category": "질환/분류", "summary": "요약"}}
    """
    try:
        response = model.generate_content(prompt)
        text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception as e:
        print(f"      ❌ 분석 실패: {e}")
        return None

def main():
    print("=== 🤖 공식 도구로 AI 분석관 출근! ===")
    records = worksheet.get_all_records()
    pending = [{"row": i+2, "data": r} for i, r in enumerate(records) if not str(r.get("AI_분류")).strip()]
    
    if not pending: return print(">> 분석할 대기열 없음 🎉")

    for item in pending:
        row_num, data = item["row"], item["data"]
        print(f"   🧠 분석 중: {data.get('제품명')}...")
        
        res = ask_gemini(data.get('제품명'), data.get('주성분'), data.get('허가심사유형'))
        if res:
            worksheet.update_cell(row_num, 10, res.get('category', '분류실패'))
            worksheet.update_cell(row_num, 11, res.get('summary', '요약실패'))
            print(f"      ✅ 완료")
        
        time.sleep(5) # 넉넉한 휴식

if __name__ == "__main__":
    main()
