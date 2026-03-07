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
    print("🚨 필수 환경변수 누락! GitHub Secrets를 확인하세요.")
    exit()

# 구글 시트 연결
credentials = Credentials.from_service_account_info(json.loads(gcp_secret), scopes=scope)
gc = gspread.authorize(credentials)
worksheet = gc.open_by_key(sheet_id).sheet1

def ask_gemini(product_name, ingredients, review_type):
    # 🌟 가장 안정적인 v1beta 주소와 모델명 사용
    model = "gemini-1.5-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
    
    prompt = f"""
    당신은 제약 전문가입니다. 다음 약품을 분석해서 'category'와 'summary'를 JSON으로만 답하세요.
    - 제품명: {product_name}
    - 주성분: {ingredients}
    - 유형: {review_type}
    
    결과는 반드시 {{"category": "분류 내용", "summary": "요약 내용"}} 형태여야 합니다.
    """
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    try:
        response = requests.post(url, json=payload, timeout=20)
        if response.status_code == 200:
            res_json = response.json()
            text = res_json['candidates'][0]['content']['parts'][0]['text']
            # 마크다운 기호 제거 후 JSON 추출
            text = text.replace("```json", "").replace("```", "").strip()
            return json.loads(text)
        else:
            print(f"      ❌ API 응답 오류 ({response.status_code})")
    except Exception as e:
        print(f"      ❌ 연결 에러: {e}")
    return None

def main():
    print("=== 🤖 AI 분석관 최종 점검 모드 출근! ===")
    
    # 시트 데이터 전체 읽기
    records = worksheet.get_all_records()
    
    # 🌟 'AI_분류' 칸이 진짜로 비어있는지 아주 깐깐하게 검사
    pending = []
    for i, row in enumerate(records):
        ai_cat = str(row.get("AI_분류", "")).strip()
        if not ai_cat or ai_cat == "None" or ai_cat == "":
            pending.append({"row": i + 2, "data": row})
    
    if not pending:
        print(">> 모든 행의 AI 분석이 이미 완료된 것으로 보입니다! 🎉")
        return

    print(f">> 총 {len(pending)}건의 빈칸을 발견했습니다. 분석을 시작합니다.")
    
    count = 0
    for item in pending:
        row_num = item["row"]
        data = item["data"]
        name = data.get('제품명', '이름없음')
        
        print(f"   🧠 분석 중 ({row_num}행): [{name}]...")
        res = ask_gemini(name, data.get('주성분', ''), data.get('허가심사유형', ''))
        
        if res:
            # J열(10): AI_분류, K열(11): AI_요약
            worksheet.update_cell(row_num, 10, res.get('category', '분류 실패'))
            worksheet.update_cell(row_num, 11, res.get('summary', '요약 실패'))
            print(f"      ✅ 시트 업데이트 완료!")
            count += 1
        
        # 과부하 방지 (5초 휴식)
        time.sleep(5)

    print(f"=== 🏆 총 {count}건의 분석 결과가 시트에 반영되었습니다! ===")

if __name__ == "__main__":
    main()
