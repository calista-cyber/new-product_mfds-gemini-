import os
import time
import json
import requests
from supabase import create_client, Client

# 1. 설정
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def ask_gemini(product_name, ingredients):
    # 🌟 [전략] 4가지 모델을 순서대로 다 찔러봅니다. (하나라도 되면 성공!)
    candidate_models = [
        "gemini-1.5-flash",       # 1순위
        "gemini-1.5-flash-001",   # 2순위 (정식명칭)
        "gemini-pro",             # 3순위 (가장 안정적)
        "gemini-1.0-pro"          # 4순위 (구형)
    ]

    prompt = f"""
    제품명: {product_name}
    성분: {ingredients}
    이 약의 1. 효능군(category, 한단어 명사)과 2. 한줄요약(summary)을 JSON으로 답해.
    """
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    # 🔄 모델 리스트를 돌면서 시도
    for model_name in candidate_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
        
        try:
            # print(f"   👉 시도 중: {model_name}...") # 디버깅용 (주석처리)
            response = requests.post(url, json=payload, timeout=10)
            
            # 성공(200)하면 바로 결과 반환하고 탈출!
            if response.status_code == 200:
                result = response.json()
                text = result['candidates'][0]['content']['parts'][0]['text']
                text = text.replace("```json", "").replace("```", "").strip()
                return json.loads(text)
            
            # 실패하면 다음 모델로 넘어감 (Continue)
            
        except Exception:
            continue

    # 모든 모델이 다 실패했을 때
    print(f"⚠️ 모든 AI 모델 접속 실패 ({product_name})")
    return None

def main():
    print("=== 🤖 AI 약품 분석관 (Multi-Model) 출근! ===")
    
    # 분석 안 된 것 가져오기
    response = supabase.table("drug_approvals").select("*").is_("ai_category", "null").execute()
    drugs = response.data
    
    if not drugs:
        print(">> 분석할 대기열이 없습니다. 모두 완료 상태입니다! 🎉")
        return

    print(f">> 분석할 대기열: {len(drugs)}건 발견")
    
    count = 0
    for drug in drugs:
        seq = drug['item_seq']
        name = drug['product_name']
        ingr = drug['ingredients'] or "정보없음"
        
        ai_result = ask_gemini(name, ingr)
        
        if ai_result:
            supabase.table("drug_approvals").update({
                "ai_category": ai_result.get('category', '기타'),
                "ai_summary": ai_result.get('summary', '정보없음')
            }).eq("item_seq", seq).execute()
            
            print(f"   ✅ [{name}] 분류: {ai_result.get('category')} | 요약 완료")
            count += 1
            time.sleep(1) # 과부하 방지

    print(f"=== 🏆 총 {count}건 AI 분석 완료! ===")

if __name__ == "__main__":
    main()
