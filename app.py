import streamlit as st
import pandas as pd
from supabase import create_client, Client
import io

# 1. 페이지 설정
st.set_page_config(page_title="신규 의약품 허가 현황", layout="wide")

# 2. Supabase 연결 (Streamlit Secrets 사용)
@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_connection()

# 3. 데이터 불러오기 함수
def load_data():
    # 최근 허가일자 순으로 가져오기
    response = supabase.table("drug_approvals").select("*").order("approval_date", desc=True).execute()
    df = pd.DataFrame(response.data)
    return df

# --- UI 시작 ---
st.title("💊 신규 의약품 허가 현황 (누적 관리)")
st.caption("매주 일요일 밤 9시, 식약처 데이터가 자동 업데이트됩니다.")

# 데이터 로드
if st.button("🔄 데이터 새로고침"):
    st.cache_data.clear()

try:
    df = load_data()
    
    if df.empty:
        st.warning("아직 데이터가 없습니다.")
    else:
        # 필터링 기능 (사이드바)
        st.sidebar.header("검색 필터")
        search_name = st.sidebar.text_input("제품명 검색")
        search_company = st.sidebar.text_input("업체명 검색")
        
        if search_name:
            df = df[df['product_name'].str.contains(search_name)]
        if search_company:
            df = df[df['company'].str.contains(search_company)]

        # 메인 테이블 표시
        st.subheader(f"총 {len(df)}건의 신규 허가 품목")
        
        # 상세링크를 클릭 가능한 형태로 보여주기 위해 Column Config 사용
        st.dataframe(
            df,
            column_config={
                "detail_url": st.column_config.LinkColumn(
                    "상세보기", display_text="식약처 바로가기"
                ),
                "approval_date": "허가일자",
                "product_name": "제품명",
                "manufacturer": "위탁제조사",
                "efficacy": "효능효과"
            },
            hide_index=True,
            use_container_width=True
        )

        # 엑셀 다운로드 버튼
        # 메모리 내에서 엑셀 파일 생성
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='신규허가목록')
            
        st.download_button(
            label="📥 엑셀로 다운로드",
            data=buffer.getvalue(),
            file_name=f"NewDrug_List_{pd.Timestamp.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

except Exception as e:
    st.error(f"데이터를 불러오는 중 오류가 발생했습니다: {e}")