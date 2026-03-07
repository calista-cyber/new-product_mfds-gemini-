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
    print("🚨 필수 환경변수 누락! 금고(Secrets)를 확인하세요.")
    exit()

# 구글 시트 연결
credentials = Credentials.from_service_account_info(json.loads(gcp_secret), scopes=scope)
gc = gspread.authorize(credentials)
worksheet = gc.open_by_key(sheet_id).sheet1

def ask_gemini(product_name, ingredients, review_type):
    # 🌟 [해결] 404 에러 방지를 위해 v1beta 주소와 정확한 모델명 사용
    model = "gemini-1.5-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
    
    prompt = f"""
    당신은 제약 전문가입니다. 다음 약품을 분석해서 'category'와 'summary'를 JSON으로 답하세요.
    - 제품명: {product_name}
    - 주성분: {ingredients}
    - 유형: {review_type}
    
    응답 예시: {{"category": "고혈압 치료제 (#신약)", "summary": "혈압을 낮춰주는 효과가 있는 약입니다."}}
    """
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    try:
        response = requests.post(url, json=payload, timeout=15)
        if response.status_code == 200:
            res_json = response.json()
            # AI가 준 텍스트에서 JSON만 쏙 뽑아내기
            text = res_json['candidates'][0]['content']['parts'][0]['text']
            text = text.replace("```json", "").replace("```", "").strip()
            return json.loads(text)
        else:
            print(f"      ❌ API 응답 오류 ({response.status_code}): {response.text[:100]}")
    except Exception as e:
        print(f"      ❌ 연결 에러: {e}")
    return None

def main():
    print("=== 🤖 AI 분석관 출근 (v1beta 모드) ===")
    
    # 시트 데이터 전체 읽기
    records = worksheet.get_all_records()
    
    # 'AI_분류' 칸이 비어있는 행만 골라내기
    pending = []
    for i, row in enumerate(records):
        if not str(row.get("AI_분류")).strip():
            pending.append({"row": i + 2, "data": row})
    
    if not pending:
        print(">> 모든 분석이 완료되었습니다! 🎉")
        return

    print(f">> 총 {len(pending)}건의 분석을 시작합니다.")
    
    count = 0
    for item in pending:
        row_num = item["row"]
        data = item["data"]
        name = data.get('제품명', '알 수 없음')
        
        print(f"   🧠 분석 중: [{name}]...")
        res = ask_gemini(name, data.get('주성분', ''), data.get('허가심사유형', ''))
        
        if res:
            # J열(10), K열(11)에 각각 분류와 요약 입력
            worksheet.update_cell(row_num, 10, res.get('category', '분류 실패'))
            worksheet.update_cell(row_num, 11, res.get('summary', '요약 실패'))
            print(f"      ✅ 업데이트 성공!")
            count += 1
        
        # 🌟 구글 서버 진정시키기 (4초 휴식)
        time.sleep(4)

    print(f"=== 🏆 총 {count}건 AI 분석 완료! 시트를 확인하세요! ===")

if __name__ == "__main__":
    main()
