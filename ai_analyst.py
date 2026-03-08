import os, time, json, requests, gspread
from bs4 import BeautifulSoup
from google.oauth2.service_account import Credentials

# 1. 설정
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
gcp_secret = os.environ.get("GCP_SERVICE_ACCOUNT")
sheet_id = os.environ.get("GOOGLE_SHEET_ID")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

credentials = Credentials.from_service_account_info(json.loads(gcp_secret), scopes=scope)
gc = gspread.authorize(credentials)
worksheet = gc.open_by_key(sheet_id).sheet1

def get_detail_page_text(item_seq):
    """상세링크에 직접 들어가서 페이지의 전체 텍스트를 긁어옵니다."""
    url = f"https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq={item_seq}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")
        
        # 쓸데없는 코드(자바스크립트, 디자인 요소) 제거
        for script in soup(["script", "style"]):
            script.extract()
            
        # 순수 텍스트만 추출
        text = soup.get_text(separator=" ", strip=True)
        # GPT가 소화하기 좋게 최대 8,000자까지만 잘라서 반환 (효능/용법은 충분히 포함됨)
        return text[:8000]
    except Exception as e:
        print(f"      ⚠️ 상세 페이지 읽기 실패: {e}")
        return ""

def ask_chatgpt(product_name, page_text):
    """읽어온 상세 페이지 내용을 바탕으로 ChatGPT에게 요약을 지시합니다."""
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    
    prompt = f"""
    당신은 제약 전문가입니다. 아래는 의약품 [{product_name}]의 식약처 공식 상세 페이지 전체 내용입니다.
    이 내용을 꼼꼼히 분석하여, 이 약이 어떤 약인지 가장 핵심적인 '분류'와 '요약'을 JSON으로 작성해 주세요.
    형식: {{"category": "예: 당뇨병 치료제", "summary": "예: 혈당 조절을 돕는 제2형 당뇨병 치료제입니다."}}
    
    [상세 페이지 내용]
    {page_text}
    """
    
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"}
    }
    
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=30).json()
        return json.loads(res['choices'][0]['message']['content'])
    except Exception as e:
        print(f"      ❌ GPT 응답 오류: {e}")
        return None

def main():
    print("=== 🤖 ChatGPT 분석관 (상세링크 심층 분석 모드) 출근! ===")
    records = worksheet.get_all_records()
    pending = []
    
    # AI_분류가 비어있는 항목만 찾기
    for idx, row in enumerate(records):
        if not str(row.get("AI_분류", "")).strip():
            pending.append({"row_num": idx + 2, "data": row})
    
    if not pending: return print(">> 모든 분석이 완료되었습니다 🎉")

    print(f">> 분석 시작: 총 {len(pending)}건")
    for item in pending:
        r_num, d = item["row_num"], item["data"]
        name = d.get('제품명', '')
        item_seq = d.get('품목기준코드', '') # 상세링크에 접속하기 위한 열쇠
        
        if not name or not item_seq: continue 
        
        print(f"   🧠 상세 페이지 정독 및 분석 중: [{name}]")
        
        # 1. 로봇이 상세링크에 들어가서 글을 읽어옵니다.
        page_text = get_detail_page_text(item_seq)
        
        if not page_text:
            continue
            
        # 2. 읽어온 방대한 내용을 GPT에게 주고 요약시킵니다.
        res = ask_chatgpt(name, page_text)
        
        if res:
            try:
                # J열과 K열에 분석 결과 업데이트
                worksheet.update(range_name=f"J{r_num}:K{r_num}", values=[[res.get('category'), res.get('summary')]])
                print(f"      ✅ 시트 반영 완료!")
            except Exception as e:
                print(f"      ❌ 시트 쓰기 오류: {e}")
                
        time.sleep(1.5) # 안정성을 위한 대기 시간

if __name__ == "__main__":
    main()
