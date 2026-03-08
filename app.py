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

# 2. 연결 설정 함수
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

# 연결 실행
gc, ai_client = init_connections()
sheet_id = st.secrets["GOOGLE_SHEET_ID"]

# 시트 데이터 불러오기
try:
    doc = gc.open_by_key(sheet_id)
    worksheet_data = doc.sheet1
    try:
        worksheet_comments = doc.worksheet("HA_money")
    except:
        worksheet_comments = doc.add_worksheet(title="HA_money", rows="1000", cols="3")
        worksheet_comments.append_row(["작성일시", "닉네임", "내용"])
except Exception as e:
    st.error(f"구글 시트 접근 실패: {e}")
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

# AI 분석 함수
@st.cache_data(ttl=3600)
def get_ai_analysis(df_recent):
    if df_recent.empty:
        return "최근 1주일간 신규 허가 데이터가 없습니다."
    summary = ""
    for _, row in df_recent.head(30).iterrows():
        summary += f"- {row.get('제품명')}({row.get('주성분')}): {row.get('AI_분류')}\n"
    prompt = f"다음 의약품 허가 목록을 바탕으로 주간 트렌드와 인사이트를 제약 전문가 입장에서 요약해줘:\n{summary}"
    try:
        res = ai_client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
        return res.choices[0].message.content
    except:
        return "AI 분석을 불러올 수 없습니다."

# --- 메인 화면 시작 ---
st.title("💊 의약품 허가 트렌드 대시보드")

try:
    df = load_data()
    tab1, tab2, tab3 = st.tabs(["📊 인사이트 분석", "📋 허가 데이터 목록", "💰 HA_money"])

    # 최근 7일 데이터 필터링
    last_7_days = pd.Timestamp.now() - pd.Timedelta(days=7)
    df_recent = df[df['허가일_dt'] >= last_7_days]

    # --- 탭 1: 인사이트 분석 ---
    with tab1:
        st.subheader("🚀 주간 신규 허가 경향 분석 (AI)")
        with st.status("AI 분석 진행 중...", expanded=True):
            st.markdown(get_ai_analysis(df_recent))
        
        st.divider()
        st.subheader("📈 주간 핵심 지표 (최근 7일 기준)")
        
        if df_recent.empty:
            st.warning("최근 7일간 데이터가 없습니다.")
        else:
            col_v1, col_v2, col_v3 = st.columns(3)

            def make_summary(df_in, col_name):
                # 건수 기준 정렬 및 No. 부여
                res = df_in[col_name].value_counts().reset_index()
                res.columns = [col_name, '건수']
                res = res.sort_values(by='건수', ascending=False).reset_index(drop=True)
                res.insert(0, 'No.', range(1, len(res) + 1))
                return res

            with col_v1:
                st.markdown("**1. AI 효능군 (많이 나온 순)**")
                if 'AI_분류' in df_recent.columns:
                    c_df = make_summary(df_recent, 'AI_분류').head(10)
                    st.bar_chart(c_df.set_index('AI_분류')['건수'], color="#FF4B4B")
                    st.dataframe(c_df, hide_index=True, use_container_width=True)

            with col_v2:
                st.markdown("**2. 허가심사 유형**")
                if '허가심사유형' in df_recent.columns:
                    t_df = make_summary(df_recent, '허가심사유형')
                    st.bar_chart(t_df.set_index('허가심사유형')['건수'], color="#0068C9")
                    st.dataframe(t_df, hide_index=True, use_container_width=True)

            with col_v3:
                st.markdown("**3. 주간 주요 성분 Top 10**")
                if '주성분' in df_recent.columns:
                    i_df = make_summary(df_recent, '주성분').head(10)
                    st.bar_chart(i_df.set_index('주성분')['건수'], color="#29B094")
                    st.dataframe(i_df, hide_index=True, use_container_width=True)

    # --- 탭 2: 데이터 목록 ---
    with tab2:
        with st.expander("🔍 상세 검색 및 필터", expanded=True):
            col_s1, col_s2, col_s3 = st.columns([4, 4, 2])
            with col_s1:
                search = st.text_input("제품명/주성분 검색")
            with col_s2:
                # 필터 복구
                if 'AI_분류' in df.columns:
                    cats = ["전체"] + sorted([str(c) for c in df['AI_분류'].unique() if c])
                    sel_cat = st.selectbox("효능군 필터", cats)
                else: sel_cat = "전체"
            with col_s3:
                if st.button("🔄 새로고침"):
                    st.cache_data.clear()
                    st.rerun()
                
        df_list = df.copy()
        if '품목기준코드' in df_list.columns:
            df_list['상세링크'] = 'https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq=' + df_list['품목기준코드'].astype(str)
            
        if search:
            df_list = df_list[df_list['제품명'].str.contains(search, na=False) | df_list['주성분'].str.contains(search, na=False)]
        if sel_cat != "전체":
            df_list = df_list[df_list['AI_분류'] == sel_cat]

        # 연번 부여
        df_list = df_list.reset_index(drop=True)
        df_list.index = df_list.index + 1
        df_list.insert(0, 'No.', df_list.index)

        show_cols = ["No.", "제품명", "주성분", "업체명", "허가일", "전문/일반구분", "허가심사유형", "AI_분류", "상세링크"]
        available = [c for c in show_cols if c in df_list.columns]
        
        st.write(f"총 **{len(df_list)}**건")
