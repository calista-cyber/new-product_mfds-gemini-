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

# 3. 데이터 로드 함수 [💡수정: 최신 날짜가 위로 오도록 내림차순 정렬]
@st.cache_data(ttl=600)
def load_data():
    data = worksheet_data.get_all_records()
    df = pd.DataFrame(data)
    if '허가일' in df.columns:
        df['허가일_dt'] = pd.to_datetime(df['허가일'], errors='coerce')
        # 허가일 기준 내림차순 정렬 (최신 허가가 1번으로 옴)
        df = df.sort_values(by='허가일_dt', ascending=False).reset_index(drop=True)
    return df

@st.cache_data(ttl=5)
def load_comments():
    data = worksheet_comments.get_all_records()
    return pd.DataFrame(data)

# AI 분석 함수 [💡수정: 주간(weekly)과 전체(total) 모드 분리]
@st.cache_data(ttl=3600)
def get_ai_analysis(df_input, mode="weekly"):
    if df_input.empty:
        return "분석할 데이터가 없습니다."
    
    summary = ""
    for _, row in df_input.head(30).iterrows():
        summary += f"- {row.get('제품명')}({row.get('주성분')}): {row.get('AI_분류')}\n"
    
    if mode == "weekly":
        prompt = f"다음 주간 의약품 허가 목록을 바탕으로 제약 전문가 입장에서 핵심 트렌드 3가지를 요약해줘:\n{summary}"
    else:
        # 전체 데이터 분석 시 5줄 내외로 제한
        prompt = f"다음 누적 허가 데이터를 바탕으로 전체 시장의 흐름과 전망을 딱 5줄 내외로 짧고 명확하게 요약해줘:\n{summary}"
        
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

    # "데이터에 있는 가장 최근 날짜" 기준 1주일 필터링
    if not df.empty and '허가일_dt' in df.columns:
        latest_date = df['허가일_dt'].max() 
        start_date = latest_date - pd.Timedelta(days=7) 
        df_recent = df[df['허가일_dt'] >= start_date]
    else:
        df_recent = pd.DataFrame()

    # --- 탭 1: 인사이트 분석 ---
    with tab1:
        # [섹션 1: 주간 인사이트]
        st.subheader("🚀 최근 주간 핵심 허가 트렌드")
        with st.status("주간 트렌드 분석 중...", expanded=True):
            st.markdown(get_ai_analysis(df_recent, mode="weekly"))
        
        st.divider()
        
        # [섹션 2: 전체 인사이트 추가]
        st.subheader("🌍 누적 데이터 허가 트렌드")
        with st.container(border=True):
            st.info(get_ai_analysis(df, mode="total"))
            
        st.divider()
        
        st.subheader("📈 최근 주간 핵심 지표")
        if df_recent.empty:
            st.warning("분석할 데이터가 없습니다.")
        else:
            col_v1, col_v2, col_v3 = st.columns(3)

            def make_summary(df_in, col_name):
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
                st.markdown("**3. 주요 성분 Top 10**")
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

        # 연번 매기기 (이미 내림차순 정렬된 상태에서 1번부터 쫙 붙습니다!)
        df_list = df_list.reset_index(drop=True)
        df_list.index = df_list.index + 1
        df_list.insert(0, 'No.', df_list.index)

        show_cols = ["No.", "제품명", "주성분", "업체명", "허가일", "전문/일반구분", "허가심사유형", "AI_분류", "상세링크"]
        available = [c for c in show_cols if c in df_list.columns]
        
        st.write(f"총 **{len(df_list)}**건 (최신 허가일 기준 정렬)")
        st.dataframe(
            df_list[available],
            column_config={"상세링크": st.column_config.LinkColumn("상세보기", display_text="식약처 바로가기"), "No.": st.column_config.NumberColumn("No.", format="%d")},
            hide_index=True, use_container_width=True
        )

    # --- 탭 3: 게시판 ---
    with tab3:
        st.info("이 약들의 시장성과 전망에 대해 자유롭게 이야기 나눠보세요! (실시간 반영)")
        with st.form("ha_form", clear_on_submit=True):
            c1, c2 = st.columns([1, 4])
            nick = c1.text_input("닉네임", placeholder="익명")
            cont = c2.text_input("내용", placeholder="이 약의 미래 가치는 어떨까요?")
            if st.form_submit_button("의견 등록 💬") and cont:
                try:
                    now = datetime.now(pytz.timezone('Asia/Seoul')).strftime("%Y-%m-%d %H:%M:%S")
                    worksheet_comments.append_row([now, nick if nick else "익명", cont])
                    st.success("등록되었습니다! 💸")
                    time.sleep(1)
                    st.rerun()
                except:
                    st.error("등록에 실패했습니다. 시트를 확인해주세요.")

        try:
            comm = load_comments()
            if not comm.empty:
                comm = comm.sort_values(by="작성일시", ascending=False)
                for _, r in comm.head(20).iterrows():
                    with st.chat_message("user"):
                        st.write(f"**{r.get('닉네임', '익명')}**: {r.get('내용', '')}")
                        st.caption(f"{r.get('작성일시', '')}")
            else:
                st.text("아직 등록된 의견이 없습니다. 첫 의견을 남겨보세요!")
        except:
            st.warning("게시판 데이터를 불러오는 중입니다...")

except Exception as e:
    st.error(f"오류 발생: {e}")
