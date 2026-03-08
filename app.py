import streamlit as st
import pandas as pd
import gspread
import json
import time
from datetime import datetime
import pytz

# 1. 페이지 설정
st.set_page_config(page_title="신규 의약품 허가 현황", layout="wide")

# 2. 구글 시트 연결
@st.cache_resource
def init_connection():
    gcp_secret = st.secrets["GCP_SERVICE_ACCOUNT"]
    gc = gspread.service_account_from_dict(json.loads(gcp_secret))
    return gc

try:
    gc = init_connection()
    sheet_id = st.secrets["GOOGLE_SHEET_ID"]
    doc = gc.open_by_key(sheet_id)
    
    worksheet_data = doc.sheet1
    
    try:
        worksheet_comments = doc.worksheet("HA_money")
    except gspread.exceptions.WorksheetNotFound:
        worksheet_comments = doc.add_worksheet(title="HA_money", rows="1000", cols="3")
        worksheet_comments.append_row(["작성일시", "닉네임", "내용"])
        
except Exception as e:
    st.error(f"구글 시트 연결 실패: {e}")
    st.stop()

# 3. 데이터 불러오기
@st.cache_data(ttl=600)
def load_data():
    data = worksheet_data.get_all_records()
    return pd.DataFrame(data)

def load_comments():
    data = worksheet_comments.get_all_records()
    return pd.DataFrame(data)

# --- UI 시작 ---
st.title("💊 신규 의약품 허가 현황")
st.caption("AI 분석관이 제공하는 제약 트렌드 & 인사이트")

col1, col2 = st.columns([8, 2])
with col1:
    st.write("매주 금요일 업데이트 | 2026년 데이터 누적 관리")
with col2:
    if st.button("🔄 목록 새로고침"):
        st.cache_data.clear()
        st.rerun()

try:
    df = load_data()
    
    if df.empty:
        st.info("데이터가 없습니다. GitHub Actions가 실행되었는지 확인하세요.")
    else:
        # 필터링 영역
        with st.expander("🔍 상세 검색 & 필터", expanded=True):
            col_s1, col_s2 = st.columns(2)
            with col_s1:
                search_name = st.text_input("제품명 또는 주성분으로 검색")
            with col_s2:
                if "AI_분류" in df.columns:
                    unique_cats = ["전체"] + [c for c in df["AI_분류"].unique() if str(c).strip() != ""]
                    selected_cat = st.selectbox("효능군 필터 (AI)", unique_cats)
                else:
                    selected_cat = "전체"

        # 데이터 가공 및 링크 생성
        df_display = df.copy()

        # 🔗 품목기준코드를 활용해 실제 식약처 상세페이지 URL 생성
        if '품목기준코드' in df_display.columns:
            base_url = 'https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq='
            df_display['상세링크'] = base_url + df_display['품목기준코드'].astype(str)
        
        # 필터 적용
        if search_name:
            df_display = df_display[
                df_display['제품명'].str.contains(search_name, na=False) | 
                df_display['주성분'].str.contains(search_name, na=False)
            ]
        if "AI_분류" in df_display.columns and selected_cat != "전체":
            df_display = df_display[df_display['AI_분류'] == selected_cat]

        st.write(f"총 **{len(df_display)}**건의 데이터가 있습니다.")

        # 📋 보여줄 컬럼 순서 설정 (허가심사유형 추가)
        cols_to_show = ["제품명", "주성분", "업체명", "허가일", "전문/일반구분", "허가심사유형", "AI_분류", "상세링크"]
        cols_to_show = [c for c in cols_to_show if c in df_display.columns]
        
        st.dataframe(
            df_display[cols_to_show],
            column_config={
                "상세링크": st.column_config.LinkColumn("상세보기", display_text="식약처 바로가기"),
            },
            hide_index=True,
            use_container_width=True
        )

except Exception as e:
    st.error(f"데이터 로드 중 오류: {e}")

# --- 💰 HA_money 게시판 ---
st.divider() 
st.markdown("### 💰 HA_money : 신제품이 만들어지는 수다")
st.info("이 약들의 시장성과 전망에 대해 자유롭게 이야기 나눠보세요!")

with st.form("ha_money_form", clear_on_submit=True):
    col_input1, col_input2 = st.columns([1, 4])
    with col_input1:
        nickname = st.text_input("닉네임", placeholder="익명")
    with col_input2:
        content = st.text_input("내용", placeholder="이 약의 시장성은 어떨까요?")
    
    submit_btn = st.form_submit_button("의견 등록 💬")
    
    if submit_btn and content:
        try:
            kst = pytz.timezone('Asia/Seoul')
            now_str = datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S")
            user_nick = nickname if nickname else "익명"
            worksheet_comments.append_row([now_str, user_nick, content])
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
except Exception:
    st.warning("게시판 로딩 중...")
