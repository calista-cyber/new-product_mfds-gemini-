import streamlit as st
import pandas as pd
import gspread
import json
import time
from datetime import datetime, timedelta
import pytz
from openai import OpenAI

# 1. 페이지 설정 (가장 상단에 위치해야 합니다)
st.set_page_config(page_title="의약품 허가 인사이트 대시보드", layout="wide")

# 2. 연결 설정 (구글 시트 & OpenAI)
@st.cache_resource
def init_connections():
    try:
        # 구글 시트 연결
        gcp_secret = st.secrets["GCP_SERVICE_ACCOUNT"]
        gc = gspread.service_account_from_dict(json.loads(gcp_secret))
        
        # OpenAI 연결 (Secrets에 OPENAI_API_KEY가 등록되어 있어야 합니다)
        client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        return gc, client
    except Exception as e:
        st.error(f"연결 설정 중 오류 발생: {e}")
        st.stop()

gc, ai_client = init_connections()
sheet_id = st.secrets["GOOGLE_SHEET_ID"]

try:
    doc = gc.open_by_key(sheet_id)
    worksheet_data = doc.sheet1
    
    # 댓글 시트 확인 (없으면 자동으로 생성)
    try:
        worksheet_comments = doc.worksheet("HA_money")
    except gspread.exceptions.WorksheetNotFound:
        worksheet_comments = doc.add_worksheet(title="HA_money", rows="1000", cols="3")
        worksheet_comments.append_row(["작성일시", "닉네임", "내용"])
except Exception as e:
    st.error(f"시트 접근 실패: {e}")
    st.stop()

# 3. 데이터 로드 함수
@st.cache_data(ttl=600)
def load_data():
    data = worksheet_data.get_all_records()
    df = pd.DataFrame(data)
    # 날짜 형식 변환 (날짜 비교 에러 방지를 위해 pd.to_datetime 사용)
    if '허가일' in df.columns:
        df['허가일_dt'] = pd.to_datetime(df['허가일'], errors='coerce')
    return df

@st.cache_data(ttl=600)
def load_comments():
    data = worksheet_comments.get_all_records()
    return pd.DataFrame(data)

# --- OpenAI 트렌드 분석 함수 ---
@st.cache_data(ttl=3600)
def get_ai_trend_analysis(df_recent):
    if df_recent.empty:
        return "최근 1주일간 신규 허가된 품목이 없어 분석을 진행할 수 없습니다."
    
    # 분석용 텍스트 요약
    summary_text = ""
    for _, row in df_recent.head(30).iterrows():
        summary_text += f"- 제품명: {row.get('제품명','N/A')}, 성분: {row.get('주성분','N/A')}, 분류: {row.get('AI_분류','N/A')}, 유형: {row.get('허가심사유형','N/A')}\n"
    
    prompt = f"""
    당신은 제약 시장 분석 전문가입니다. 아래는 최근 대한민국에서 허가된 신규 의약품 목록입니다.
    데이터를 분석하여 다음 3가지를 한국어로 전문성 있게 요약 분석해주세요:
    1. 이번 주의 주요 허가 트렌드 (어떤 효능군이나 치료영역이 집중되었는가?)
    2. 주목할 만한 성분이나 특징적인 품목 (제약사 입장에서의 R&D 의미)
    3. 제약 시장 및 영업/마케팅 측면의 인사이트

    목록:
    {summary_text}
    """
    
    try:
        response = ai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI 분석 중 오류 발생: {e}"

# --- 메인 화면 시작 ---
st.title("💊 의약품 허가 트렌드 대시보드")

try:
    df = load_data()
    
    # 탭 구성 (인사이트 / 데이터 목록 / 게시판)
    tab1, tab2, tab3 = st.tabs(["📊 인사이트 분석", "📋 허가 데이터 목록", "💰 HA_money"])

    # --- 탭 1: 시각화 및 AI 분석 ---
    with tab1:
        st.subheader("🚀 주간 신규 허가 경향 분석 (OpenAI)")
        
        # [수정됨] 에러 발생 지점: 날짜 비교 형식을 판다스 형식으로 통일
        last_7_days = pd.Timestamp.now() - pd.Timedelta(days=7)
        df_recent = df[df['허가일_dt'] >= last_7_days]
        
        with st.status("AI 분석관이 트렌드를 파악 중입니다...", expanded=True):
            analysis_result = get_ai_trend_analysis(df_recent)
            st.markdown(analysis_result)
        
        st.divider()
        
        st.subheader("📈 핵심 지표 시각화 (전체 데이터)")
        col_v1, col_v2, col_v3 = st.columns(3)
        
        with col_v1:
            st.markdown("**1. AI 효능군 분류 (Top 10)**")
            if 'AI_분류' in df.columns:
                cat_counts = df['AI_분류'].value_counts().head(10)
                st.bar_chart(cat_counts, color="#FF4B4B")
        
        with col_v2:
            st.markdown("**2. 허가심사 유형 분포**")
            if '허가심사유형' in df.columns:
                type_counts = df['허가심사유형'].value_counts()
                st.bar_chart(type_counts, color="#0068C9")
                
        with col_v3:
            st.markdown("**3. 주요 주성분 (Top 10)**")
            if '주성분' in df.columns:
                ing_counts = df['주성분'].value_counts().head(10)
                st.bar_chart(ing_counts, color="#29B094")

    # --- 탭 2: 데이터 목록 ---
    with tab2:
        col_s1, col_s2 = st.columns([8, 2])
        with col_s1:
            search_name = st.text_input("🔍 제품명 또는 주성분 검색")
        with col_s2:
            if st.button("🔄 데이터 새로고침"):
                st.cache_data.clear()
                st.rerun()
                
        df_display = df.copy()
        
        # 🔗 상세링크 생성
        if '품목기준코드' in df_display.columns:
            base_url = 'https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq='
            df_display['상세링크'] = base_url + df_display['품목기준코드'].astype(str)
            
        if search_name:
            df_display = df_display[
                df_display['제품명'].str.contains(search_name, na=False) | 
                df_display['주성분'].str.contains(search_name, na=False)
            ]

        cols_to_show = ["제품명", "주성분", "업체명", "허가일", "전문/일반구분", "허가심사유형", "AI_분류", "상세링크"]
        cols_to_show = [c for c in cols_to_show if c in df_display.columns]
        
        st.dataframe(
            df_display[cols_to_show],
            column_config={
                "상세링크": st.column_config.LinkColumn("상세보기", display_text="식약처 바로가기")
            },
            hide_index=True, 
            use_container_width=True
        )

    # --- 탭 3: HA_money 게시판 ---
    with tab3:
        st.info("이 약들의 시장성과 전망에 대해 자유롭게 이야기 나눠보세요! (익명 보장)")
        
        with st.form("ha_money_form", clear_on_submit=True):
            col_input1, col_input2 = st.columns([1, 4])
            with col_input1:
                u_nick = st.text_input("닉네임", placeholder="익명")
            with col_input2:
                u_content = st.text_input("내용", placeholder="이 약의 미래 가치는 어떨까요?")
            
            submit_btn = st.form_submit_button("의견 등록 💬")
            
            if submit_btn and u_content:
                try:
                    kst = pytz.timezone('Asia/Seoul')
                    now_str = datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S")
                    user_nick = u_nick if u_nick else "익명"
                    worksheet_comments.append_row([now_str, user_nick, u_content])
                    st.success("등록되었습니다! 💸")
                    time.sleep(1) 
                    st.rerun()    
                except Exception as e:
                    st.error(f"등록 실패: {e}")

        try:
            comments_df = load_comments()
            if not comments_df.empty:
                comments_df = comments_df.sort_values(by="작성일시", ascending=False)
                for _, row in comments_df.head(20).iterrows():
                    with st.chat_message("user"):
                        st.write(f"**{row.get('닉네임', '익명')}**: {row.get('내용', '')}")
                        st.caption(f"{row.get('작성일시', '')}")
            else:
                st.text("아직 등록된 의견이 없습니다.")
        except Exception:
            st.warning("게시판 데이터를 불러오는 중입니다...")

except Exception as e:
    st.error(f"대시보드 실행 중 오류 발생: {e}")
