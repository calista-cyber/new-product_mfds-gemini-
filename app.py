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

    # 공통: 최근 7일 데이터 필터링
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
        
        if df_recent.empty:
            st.warning("최근 7일 이내에 허가된 데이터가 없어 시각화할 수 없습니다.")
        else:
            col_v1, col_v2, col_v3 = st.columns(3)

            # 시각화 데이터 가공 함수 (정렬 및 연번 추가)
            def get_chart_data(df_in, col_name):
                # 건수 기준 내림차순 정렬
                res = df_in[col_name].value_counts().reset_index()
                res.columns = [col_name, '건수']
                res = res.sort_values(by='건수', ascending=False).reset_index(drop=True)
                # No. 컬럼 추가 (1부터 시작)
                res.insert(0, 'No.', range(1, len(res) + 1))
                return res

            with col_v1:
