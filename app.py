import streamlit as st
import pandas as pd
from supabase import create_client, Client
import io

# 1. 페이지 설정
st.set_page_config(page_title="신규 의약품 허가 현황", layout="wide")

# 2. Supabase 연결
@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

try:
    supabase = init_connection()
except Exception as e:
    st.error("DB 연결 실패. Secrets 설정을 확인해주세요.")
    st.stop()

# 3. 데이터 불러오기 함수
def load_data():
    # 최근 허가일자 순으로 가져오기
    response = supabase.table("drug_approvals").select("*").order("approval_date", desc=True).execute()
    df = pd.DataFrame(response.data)
    return df

# --- UI 시작 ---
st.title("💊 신규 의약품 허가 현황 (누적 관리)")

col1, col2 = st.columns([8, 2])
with col1:
    st.caption("매주 일요일 밤 9시 자동 업데이트 (수동 업데이트 가능)")
with col2:
    if st.button("🔄 목록 새로고침"):
        st.cache_data.clear()

try:
    df = load_data()
    
    if df.empty:
        st.info("아직 수집된 데이터가 없습니다. GitHub Actions에서 'Run workflow'를 실행해보세요.")
    else:
        # [중요] DB 영어 컬럼명을 -> 한글로 변경 (사용자 보기 편하게)
        df_display = df.rename(columns={
            "approval_date": "허가일자",
            "product_name": "제품명",
            "company": "업체명",
            "manufacturer": "위탁제조업체",
            "category": "전문/일반",
            "approval_type": "허가유형",
            "ingredients": "성분명",
            "efficacy": "효능효과",
            "detail_url": "링크"
        })

        # 필터링 기능
        with st.expander("🔍 상세 검색 열기"):
            search_name = st.text_input("제품명으로 검색")
            if search_name:
                df_display = df_display[df_display['제품명'].str.contains(search_name)]

        st.write(f"총 **{len(df_display)}**건의 데이터가 있습니다.")

        # 메인 테이블 표시 (링크 기능 포함)
        st.dataframe(
            df_display,
            column_config={
                "링크": st.column_config.LinkColumn(
                    "상세보기", display_text="식약처 바로가기"
                ),
            },
            hide_index=True,
            use_container_width=True
        )

        # 엑셀 다운로드 (한글 컬럼 적용된 상태로 다운로드)
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_display.to_excel(writer, index=False, sheet_name='신규허가목록')
            
        st.download_button(
            label="📥 엑셀로 다운로드",
            data=buffer.getvalue(),
            file_name=f"의약품허가목록_{pd.Timestamp.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

except Exception as e:
    st.error(f"데이터 로드 중 오류: {e}")
