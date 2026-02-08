import os
import time
import json
import google.generativeai as genai
from supabase import create_client, Client

# 1. 설정 (환경변수에서 키를 가져옵니다)
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") # 깃허브 시크릿에서 가져옴

# Supabase 연결
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
# Gemini 연결
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash') # 빠르고 저렴한 모델

def ask_gemini(product_name, ingredients):
    """
    약 이름과 성분을 주면 -> 효능군(category)과 1줄요약(summary)을 반환
    """
    prompt = f"""
    너는 제약 전문가야. 아래 의약품 정보를 보고 JSON 형식으로 답변해.
    
    제품명: {product_name}
    성분: {ingredients}
    
    [질문]
    1. category: 이 약의 효능군을 한국어 명사 1단어로 분류해 (예: 항생제, 해열진통제, 소화제, 고혈압치료제, 비타민제 등).
    2. summary: 이 약이 어떤 환자에게 쓰이는지 초등학생도 이해하게 1문장으로 요약해.
    
    [출력형식]
    {{"category": "...", "summary": "..."}}
    """
    try:
        response = model.generate_content(prompt)
        text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception as e:
        print(f"🤖 AI 분석 실패 ({product_name}): {e}")
        return None

def main():
    print("=== 🤖 AI 약품 분석관 출근했습니다! ===")
    
    # 1. 아직 분석 안 된(ai_category가 비어있는) 약만 가져오기
    # 주의: Supabase에 'ai_category' 컬럼이 미리 만들어져 있어야 합니다!
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
        
        # Gemini에게 물어보기
        ai_result = ask_gemini(name, ingr)
        
        if ai_result:
            # 2. 결과 저장 (업데이트)
            supabase.table("drug_approvals").update({
                "ai_category": ai_result.get('category', '기타'),
                "ai_summary": ai_result.get('summary', '정보없음')
            }).eq("item_seq", seq).execute()
            
            print(f"   ✅ [{name}] 분류: {ai_result.get('category')} | 요약 완료")
            count += 1
        
        # 너무 빨리 요청하면 체할 수 있으니 1초 휴식
        time.sleep(1)

    print(f"=== 🏆 총 {count}건 AI 분석 완료! ===")

if __name__ == "__main__":
    main()
