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
    # 🌟 [전략] 3가지 모델을 순서대로 다 찔러봅니다. (하나라도 되면 성공!)
    candidate_models = [
        "gemini-1.5-flash",       # 1순위: 최신형
        "gemini-1.5-flash-001",   # 2순위: 최신형(정식명칭)
        "gemini-pro",             # 3순위: 구형이지만 가장 안정적
        "gemini-1.0-pro"          # 4순위: 최후의 보루
    ]

    prompt = f"""
    너는 제약 전문가야. 아래 의약품 정보를 보고 JSON 형식으로 답변해.
    
    제품명: {product_name}
    성분: {ingredients}
    
    [질문]
    1. category: 이 약의 효능군을 한국어 명사 1단어로 분류해 (예: 항생제, 소화제, 진통제, 비타민제 등).
    2. summary: 이 약이 어떤 환자에게 쓰이는지 초등학생도 이해하게 1문장으로 요약해.
    
    [출력형식]
    {{"category": "...", "summary": "..."}}
    """
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }

    # 🔄 모델 리스트를 돌면서 시도
    for model_name in candidate_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            
            # 성공(200)하면 바로 결과 반환하고 탈출!
            if response.status_code == 200:
                result = response.json()
                try:
                    text = result['candidates'][0]['content']['parts'][0]['text']
                    text = text.replace("```json", "").replace("```", "").strip()
                    return json.loads(text)
                except (KeyError, IndexError):
                    continue # 응답은 왔는데 내용이 이상하면 다음 모델로
            
            # 404나 400 에러면 다음 모델 시도
            # print(f"   (시도중) {model_name} 실패.. 다음 모델 검색")
            
        except Exception:
            continue

    # 모든 모델이 다 실패했을 때
    print(f"⚠️ 모든 AI 모델 접속 실패 ({product_name}) - API KEY를 확인하세요.")
    return None

def main():
    print("=== 🤖 AI 약품 분석관(Multi-Model Try) 출근했습니다! ===")
    
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
