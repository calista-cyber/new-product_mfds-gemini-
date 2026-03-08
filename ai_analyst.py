import os, time, json, requests, gspread

# 1. 설정
gcp_secret = os.environ.get("GCP_SERVICE_ACCOUNT")
sheet_id = os.environ.get("GOOGLE_SHEET_ID")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# 🌟 구글 시트 인증 (가장 안정적인 gspread 내장 프리패스 함수 적용)
gc = gspread.service_account_from_dict(json.loads(gcp_secret))
worksheet = gc.open_by_key(sheet_id).sheet1

def ask_chatgpt(name, company, category, ingredient):
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}", 
        "Content-Type": "application/json"
    }
    
    # 🌟 팀장님의 맞춤형 '전략 자문관' 프롬프트 완벽 적용!
    prompt = f"""
    당신은 우리 제약회사의 신제품 개발 전략 자문관이며 한국제약업계 이해도가 높은 전문가입니다.
    
    [우리 회사 정보 및 관심 영역]
    - 주력 분야: 퍼스트 제네릭 및 개량신약 발굴
    - 주요 파이프라인: 비뇨기계, 프로바이오틱스(정장생균), 하부위장관, 간질환, 탈모, 만성질환(당뇨, 순환기 등), 종합병원 정형외과 사용가능 약물 등
    - 주요제품(특징): 노르믹스(비흡수성 항생제, 간성혼수, 설사), 바이오탑(정장생균), 엘리가드(비뇨기 전립선암), 알파본(콜레칼시페롤), 헤어그로(남성형탈모), 아다모(남성형탈모), 하노마린(간질환보조제)
    - 개발 파이프라인: 로수바스타틴/에제티미브 복합제 로미브OD, 프레가발린 단일제 프레논OD 등 제형 차별화 개발. 전립선암 라인업 추가를 위한 엔잘루타미드 연질캡슐, 콜레칼시페롤 1mcg 알파본디, 미녹시딜 외용액제 판그로액, 두타스테리드/탐스로신 복합제 콤비다트, 피타바스타틴/에제티미브 복합제 피타제로
    
    아래 타사 신규 허가 의약품 정보를 분석하여, 단순 정보 나열이 아닌 '우리 회사 관점의 전략적 인사이트'를 도출해 JSON으로 답하세요.
    
    - 제품명: {name}
    - 업체명: {company}
    - 구분: {category}
    - 주성분: {ingredient}
    
    형식: 
    {{"category": "경쟁/시너지/관심/무관 중 택1 (혹은 자유로운 전략적 분류)", 
      "summary": "예: 당사의 엔잘루타마이드 파이프라인 및 비뇨기계 라인업(엘리가드 등)과 경쟁/시너지가 예상되는 품목임. 혹은 당사 주력 분야와 무관한 품목임 등 구체적인 전략적 의견을 전문가 시각에서 작성."}}
    """
    
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"}
    }
    
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=25).json()
        if 'choices' in res:
            return json.loads(res['choices'][0]['message']['content'])
        else:
            print(f"      ❌ GPT 응답 거절: {res}")
            return None
    except Exception as e:
        print(f"      ❌ 통신 에러: {e}")
        return None

def main():
    print("=== 🤖 ChatGPT 전략 자문관 출근! (맞춤형 인사이트 모드) ===")
    records = worksheet.get_all_records()
    pending = []
    
    for idx, row in enumerate(records):
        if not str(row.get("AI_분류", "")).strip():
            pending.append({"row_num": idx + 2, "data": row})
    
    if not pending: return print(">> 모든 분석 완료 🎉")

    print(f">> 전략 분석 대기: 총 {len(pending)}건")
    for item in pending:
        r_num, d = item["row_num"], item["data"]
        name = d.get('제품명', '')
        if not name: continue 
        
        print(f"   🧠 전략 분석 중: [{name}]")
        res = ask_chatgpt(name, d.get('업체명', ''), d.get('전문/일반구분', ''), d.get('주성분', ''))
        
        if res:
            try:
                worksheet.update(range_name=f"J{r_num}:K{r_num}", values=[[res.get('category'), res.get('summary')]])
                print(f"      ✅ 시트 반영 완료!")
            except Exception as e:
                print(f"      ❌ 시트 쓰기 에러: {e}")
                
        time.sleep(1.5)

if __name__ == "__main__":
    main()
