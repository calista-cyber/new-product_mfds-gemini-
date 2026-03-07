import os
import time
import json
import requests
import gspread
from google.oauth2.service_account import Credentials

# 1. 설정 (구글 시트 & Gemini 키)
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
gcp_secret = os.environ.get("GCP_SERVICE_ACCOUNT")
sheet_id = os.environ.get("GOOGLE_SHEET_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not gcp_secret or not sheet_id or not GEMINI_API_KEY:
    print("🚨 필수 환경변수(구글 키, 시트 ID, Gemini 키) 누락!")
    exit()

credentials = Credentials.from_service_account_info(json.loads(gcp_secret), scopes=scope)
gc = gspread.authorize(credentials)
worksheet = gc.open_by_key(sheet_id).sheet1

def ask_gemini(product_name, ingredients, review_type):
    candidate_models = ["gemini-1.5-flash", "gemini-1.5-pro"]

    prompt = f"""
    당신은 제약/바이오 전문가입니다. 다음 약품 정보를 분석해주세요.
    - 제품명: {product_name}
    - 주성분: {ingredients}
    - 허가심사유형: {review_type}

    출력형식은 반드시 아래와 같은 JSON 형태여야 합니다:
    {{
        "category": "당뇨병 치료제, 내분비 질환 (#신약)", 
        "summary": "제2형 당뇨병 성인 환자의 혈당 조절을 돕는 알약입니다."
    }}
    """
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    for model_name in candidate_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
        try:
            response = requests.post(url, json=payload, timeout=15)
            if response.status_code == 200:
                result = response.json()
                text = result['candidates'][0]['content']['parts'][0]['text']
                text = text.replace("```json", "").replace("```", "").strip()
                return json.loads(text)
            else:
                # 🌟 에러가 나면 왜 났는지 확실하게 출력!
                print(f"      [디버그] API 에러 ({response.status_code}): {response.text[:100]}...")
        except Exception as e:
            print(f"      [디버그] 파이썬 에러: {e}")
            continue
            
    return None

def main():
    print("=== 🤖 AI 약품 분석관 (구글 시트 모드) 출근! ===")
    
    records = worksheet.get_all_records()
    
    pending_items = []
    for idx, row in enumerate(records):
        # AI_분류가 비어있는 항목만 골라내기
        if not row.get("AI_분류") or str(row.get("AI_분류")).strip() == "":
            pending_items.append({"row_num": idx + 2, "data": row})
            
    if not pending_items:
        print(">> 분석할 대기열이 없습니다. 모두 완료 상태입니다! 🎉")
        return

    print(f">> 분석할 대기열: {len(pending_items)}건 발견")
    
    count = 0
    for item in pending_items:
        row_num = item["row_num"]
        data = item["data"]
        
        name = data.get('제품명', '')
        ingr = data.get('주성분', '')
        review = data.get('허가심사유형', '')
        
        print(f"   🧠 분석 중: [{name}]...")
        ai_result = ask_gemini(name, ingr, review)
        
        if ai_result:
            worksheet.update_cell(row_num, 10, ai_result.get('category', '분류 실패'))
            worksheet.update_cell(row_num, 11, ai_result.get('summary', '요약 실패'))
            print(f"   ✅ 완료: {ai_result.get('category')}")
            count += 1
        else:
            print(f"   ⚠️ AI 분석 실패 ({name})")
            
        # 🌟 가장 중요한 부분! 구글 서버가 과부하로 화내지 않도록 1건 처리 후 5초씩 휴식
        time.sleep(5) 

    print(f"=== 🏆 총 {count}건 구글 시트에 AI 분석 업데이트 완료! ===")

if __name__ == "__main__":
    main()
