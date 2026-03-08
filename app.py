import streamlit as st
import pandas as pd
import gspread
import json
import time
from datetime import datetime, timedelta
import pytz
from openai import OpenAI

# 1. 페이지 설정
st.set_page_config(page_title="의약품 허가 인사이트 대시보드", layout="wide")

# 2. 연결 설정
@st.cache_resource
def init_connections():
    try:
        gcp_secret = st.secrets["GCP_SERVICE_ACCOUNT"]
        gc = gspread.service_account_from_dict(json.loads(gcp_secret))
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
    
    summary_text = ""
    for _, row in df_recent.head(30).iterrows():
        summary_text += f"- 제품명: {row.get('제품명','N/A')}, 성분: {row.get('주성분','N/A')}, 분류: {row.get('AI_분류','N/A')}, 유형: {row.get('허가심사유형','N/A')}\n"
    
    prompt = f"""당신은 제약 시장 분석 전문가입니다. 최근 1주일간 대한민국에서 허가된 신규 의약품 데이터를 요약 분석해주세요.
    1. 이번 주의 주요 허가 트렌드 (효능군 중심)
    2. 주목할 만한 성분이나 특징적인 품목 (R&D 의미)
    3. 영업/마케팅 인사이트
    목록:\n{summary_text}"""
    
    try:
        response = ai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI 분석 중 오류 발생: {e}"

# --- 메인 화면 ---
st.title("💊 의약품 허가 트렌드 대시보드")

try:
    df = load_data()
    tab1, tab2, tab3 = st.tabs(["📊 인사이트 분석", "📋 허가 데이터 목록", "💰 HA_money"])

    # 공통: 최근 7일 데이터 필터링 (KST 기준)
    last_7_days = pd.Timestamp.now() - pd.Timedelta(days=7)
    df_recent = df[df['허가일_dt'] >= last_7_days]

    # --- 탭 1: 인사이트 분석 ---
    with tab1:
        st.subheader("🚀 주간 신규 허가 경향 분석 (OpenAI)")
        with st.status("AI 분석관이 트렌드를 파악 중입니다...", expanded=True):
            analysis_result = get_ai_trend_analysis(df_recent)
            st.markdown(analysis_result)
        
        st.divider()
        st.subheader("📈 주간 핵심 지표 시각화 (최근 7일 기준)")
        
        # [수정] 콜론(:) 유무 완벽 확인
        if df_recent.empty:
            st.warning("최근 7일 이내에 허가된 데이터가 없어 시각화할 수 없습니다.")
        else:
            col_v1, col_v2, col_v3 = st.columns(3)

            # 시각화 데이터 가공용 함수 (정렬 및 연번 추가)
            def get_chart_data(df, col_name):
                # 건수 기준 내림차순 정렬
                res = df[col_name].value_counts().reset_index()
                res.columns = [col_name, '건수']
                res = res.sort_values(by='건수', ascending=False).reset_index(drop=True)
                # No. 컬럼 추가 (1부터 시작)
                res.insert(0, 'No.', range(1, len(res) + 1))
                return res

            with col_v1:
                st.markdown("**1. AI 효능군 (많이 나온 순)**")
                if 'AI_분류' in df_recent.columns:
                    cat_df = get_chart_data(df_recent, 'AI_분류').head(10)
                    # 그래프: 내림차순 정렬
                    st.bar_chart(cat_df.set_index('AI_분류')['건수'], color="#FF4B4B")
                    # 표: 연번 1번부터 시작 및 인덱스 숨김
                    st.dataframe(cat_df, hide_index=True, use_container_width=True)

            with col_v2:
                st.markdown("**2. 허가심사 유형 (많이 나온 순)**")
                if '허가심사유형' in df_recent.columns:
                    type_df = get_chart_data(df_recent, '허가심사유형')
                    st.bar_chart(type_df.set_index('허가심사유형')['건수'], color="#0068C9")
                    st.dataframe(type_df, hide_index=True, use_container_width=True)

            with col_v3:
                st.markdown("**3. 주간 주요 성분 Top 10**")
                if '주성분' in df_recent.columns:
                    ing_df = get_chart_data(df_recent, '주성분').head(10)
                    st.bar_chart(ing_df.set_index('주성분')['건수'], color="#29B094")
                    st.dataframe(ing_df, hide_index=True, use_container_width=True)

    # --- 탭 2: 데이터 목록 ---
    with tab2:
        with st.expander("🔍 상세 검색 및 필터", expanded=True):
            col_s1, col_s2, col_s3 = st.columns([4, 4, 2])
            with col_s1:
                search_name = st.text_input("제품명 또는 주성분 검색")
            with col_s2:
                # [복구] AI_분류 필터 다시 추가
                if 'AI_분류' in df.columns:
                    unique_cats = ["전체"] + sorted([str(c) for c in df['AI_분류'].unique() if c])
                    selected_cat = st.selectbox("AI 효능군 필터", unique_cats)
                else:
                    selected_cat = "전체"
            with col_s3:
                if st.button("🔄 데이터 새로고침"):
                    st.cache_data.clear()
                    st.rerun()
                
        df_display = df.copy()
        if '품목기준코드' in df_display.columns:
            df_display['상세링크'] = 'https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq=' + df_display['품목기준코드'].astype(str)
            
        if search_name:
            df_display = df_display[df_display['제품명'].str.contains(search_name, na=False) | df_display['주성분'].str.contains(search_name, na=False)]
        if selected_cat != "전체":
            df_display = df_display[df_display['AI_분류'] == selected_cat]

        # [수정] 전체 목록도 연번 1번부터 시작
        df_display = df_display.reset_index(drop=True)
        df_display.index = df_display.index + 1
        df_display.insert(0, 'No.', df_display.index)

        cols_to_show = ["No.", "제품명", "주성분", "업체명", "허가일", "전문/일반구분", "허가심사유형", "AI_분류", "상세링크"]
        cols_to_show = [c for c in cols_to_show if c in df_display.columns]
        
        st.write(f"검색 결과: 총 **{len(df_display)}**건")
        st.dataframe(
            df_display[cols_
