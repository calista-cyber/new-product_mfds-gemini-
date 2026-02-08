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
    # 1.5 Flash 모델에게 직접 물어봅니다.
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    prompt = f"""
    제품명: {product_name}
    성분: {ingredients}
    이 약의 1. 효능군(category)과 2. 한줄요약(summary)을 JSON으로 답해.
    """
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    try:
        response = requests.post(url, json=payload, timeout=10)
        
        # 🚨 [핵심] 구글이 거절하면 그 이유(메시지)를 그대로 출력합니다.
        if response.status_code != 200:
            print(f"❌ 구글 거절 사유 (Code {response.status_code}):")
            print(f"   👉 메시지: {response.text}")
            return None

        # 성공하면 처리
        result = response.json()
        text = result['candidates'][0]['content']['parts'][0]['text']
        text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
            
    except Exception as e:
        print(f"❌ 시스템 에러: {e}")
        return None

def main():
    print("=== 🤖 AI 분석관 (정밀 진단 모드) 시작 ===")
    
    # 1. 키가 제대로 들어왔는지 길이 확인
    if GEMINI_API_KEY:
        print(f"🔑 API Key 상태: 로드됨 (길이: {len(GEMINI_API_KEY)}자)")
    else:
        print("🚨 API Key 상태: 없음 (NULL) - Secrets 설정을 확인하세요!")
        return

    # 2. 분석할 데이터 가져오기
    response = supabase.table("drug_approvals").select("*").is_("ai_category", "null").execute()
    drugs = response.data
    
    if not drugs:
        print(">> 분석할 대기열이 없습니다.")
        return

    # 3. 딱 1개만 시도해보고 로그 출력 (많이 할 필요 없음)
    drug = drugs[0]
    print(f">> 진단 대상: {drug['product_name']}")
    
    result = ask_gemini(drug['product_name'], drug['ingredients'])
    
    if result:
        print("🎉 진단 결과: 성공! (API 키와 모델 모두 정상입니다)")
        # 성공했으면 저장까지
        supabase.table("drug_approvals").update({
            "ai_category": result.get('category'),
            "ai_summary": result.get('summary')
        }).eq("item_seq", drug['item_seq']).execute()
    else:
        print("💥 진단 결과: 실패 (위의 구글 거절 사유를 확인하세요)")

if __name__ == "__main__":
    main()
