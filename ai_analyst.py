import os
import time
import json
import requests
from supabase import create_client, Client

# 1. 설정 및 진단
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

print(f"DEBUG: Supabase Key Loaded? {'YES' if SUPABASE_KEY else 'NO'}")
# 🌟 여기가 중요합니다! 키가 제대로 들어왔는지 확인 (보안상 길지만 출력)
if GEMINI_API_KEY:
    print(f"DEBUG: Gemini Key Loaded! Length: {len(GEMINI_API_KEY)}")
else:
    print("🚨 DEBUG: Gemini Key is MISSING! (None)")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def ask_gemini(product_name, ingredients):
    # 4가지 모델 순차 공격
    candidate_models = [
        "gemini-1.5-flash",
        "gemini-1.5-flash-001",
        "gemini-pro",
        "gemini-1.0-pro"
    ]

    prompt = f"""
    너는 제약 전문가야. 아래 의약품 정보를 보고 JSON 형식으로 답변해.
    제품명: {product_name}
    성분: {ingredients}
    [질문]
    1. category: 이 약의 효능군을 한국어 명사 1단어로 분류해.
    2. summary: 이 약이 어떤 환자에게 쓰이는지 초등학생도 이해하게 1문장으로 요약해.
    [출력형식] {{"category": "...", "summary": "..."}}
    """
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    for model_name in candidate_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                result = response.json()
                text = result['candidates'][0]['content']['parts'][0]['text']
                text = text.replace("```json", "").replace("```", "").strip()
                return json.loads(text)
        except Exception:
            continue

    print(f"⚠️ 모든 AI 모델 접속 실패 ({product_name}) - API KEY 확인 필요")
    return None

def main():
    print("=== 🤖 AI 약품 분석관(Diagnosis Mode) 출근했습니다! ===")
    
    response = supabase.table("drug_approvals").select("*").is_("ai_category", "null").execute()
    drugs = response.data
    
    if not drugs:
        print(">> 분석할 대기열이 없습니다. 모두 완료 상태입니다! 🎉")
        return

    print(f">> 분석할 대기열: {len(drugs)}건 발견")
    
    for drug in drugs:
        ai_result = ask_gemini(drug['product_name'], drug['ingredients'] or "정보없음")
        
        if ai_result:
            supabase.table("drug_approvals").update({
                "ai_category": ai_result.get('category', '기타'),
                "ai_summary": ai_result.get('summary', '정보없음')
            }).eq("item_seq", drug['item_seq']).execute()
            print(f"   ✅ [{drug['product_name']}] 완료")
            time.sleep(1)

    print("=== 🏆 AI 분석 완료! ===")

if __name__ == "__main__":
    main()
