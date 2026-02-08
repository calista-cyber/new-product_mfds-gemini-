import streamlit as st
import pandas as pd
from supabase import create_client, Client
import io
import time

# 1. 페이지 설정
st.set_page_config(page_title="신규 의약품 허가 현황", layout="wide")

# 2. Supabase 연결
@st.cache_resource
def init_connection():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception:
        return None

supabase = init_connection()

if not supabase:
    st.error("DB 연결 실패. Streamlit Secrets에 SUPABASE_URL과 SUPABASE_KEY를 설정해주세요.")
    st.stop()

# 3. 데이터 불러오기 함수
def load_data():
    # 최근 허가일자 순으로 가져오기
    try:
        response = supabase.table("drug_approvals").select("*").order("approval_date", desc=True).execute()
        return pd.DataFrame(response.data)
    except Exception:
        return pd.DataFrame()

# --- UI 시작: 메인 목록 ---
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
        st.info("아직 수집된 데이터가 없습니다. GitHub Actions에서 'Run workflow'를 실행해보세요.")
    else:
        # [중요] DB 영어 컬럼명을 -> 한글로 변경
        rename_dict = {
            "item_seq": "품목기준코드",    # 🌟 팀장님 요청 반영 완료!
            "approval_date": "허가일자",
            "product_name": "제품명",
            "company": "업체명",
            "category": "전문/일반",
            "approval_type": "허가유형",
            "ingredients": "성분명",
            "efficacy": "효능효과",
            "ai_category": "AI분류",
            "ai_summary": "AI요약",
            "detail_url": "링크"
        }
        
        df_display = df.rename(columns=rename_dict)

        # 필터링 기능
        with st.expander("🔍 상세 검색 & 필터"):
            col_s1, col_s2 = st.columns(2)
            with col_s1:
                search_name = st.text_input("제품명으로 검색")
            with col_s2:
                if "AI분류" in df_display.columns:
                    unique_cats = ["전체"] + list(df_display["AI분류"].unique())
                    selected_cat = st.selectbox("효능군 필터 (AI)", unique_cats)
                else:
                    selected_cat = "전체"

        # 필터 적용 logic
        if search_name:
            df_display = df_display[df_display['제품명'].str.contains(search_name)]
        if "AI분류" in df_display.columns and selected_cat != "전체":
            df_display = df_display[df_display['AI분류'] == selected_cat]

        st.write(f"총 **{len(df_display)}**건의 데이터가 있습니다.")

        # 메인 테이블 표시
        st.dataframe(
            df_display,
            column_config={
                "링크": st.column_config.LinkColumn(
                    "상세보기", display_text="식약처 바로가기"
                ),
                # 품목기준코드는 숫자가 아니라 문자로 보이게 설정 (콤마 제거)
                "품목기준코드": st.column_config.TextColumn("품목기준코드"),
            },
            hide_index=True,
            use_container_width=True
        )

        # 엑셀 다운로드
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

# --- 💰 HA_money : 돈이 되는 수다 (게시판 기능) ---
st.divider() 
st.markdown("### 💰 HA_money : 돈이 되는 수다")
st.info("이 약들의 시장성과 전망에 대해 자유롭게 이야기 나눠보세요! (익명 보장)")

# 1. 댓글 입력 폼
with st.form("ha_money_form", clear_on_submit=True):
    col_input1, col_input2 = st.columns([1, 4])
    with col_input1:
        nickname = st.text_input("닉네임", placeholder="익명")
    with col_input2:
        content = st.text_input("내용", placeholder="예: 이 약은 A사 제품이랑 성분이 똑같네요. 가격 경쟁력이 관건일 듯!")
    
    submit_btn = st.form_submit_button("의견 등록 💬")
    
    if submit_btn and content:
        try:
            new_comment = {
                "user_nickname": nickname if nickname else "익명",
                "content": content
            }
            supabase.table("ha_money").insert(new_comment).execute()
            st.success("소중한 정보가 등록되었습니다! 💸")
            time.sleep(1) 
            st.rerun()    
        except Exception as e:
            st.error(f"등록 실패: {e}")

# 2. 댓글 목록 보여주기
try:
    response = supabase.table("ha_money").select("*").order("created_at", desc=True).limit(20).execute()
    comments = response.data

    if comments:
        for chat in comments:
            with st.chat_message("user"):
                st.write(f"**{chat['user_nickname']}**: {chat['content']}")
                # 날짜 자르기
                date_str = chat['created_at'][:16].replace("T", " ")
                st.caption(f"{date_str}")
    else:
        st.text("아직 등록된 글이 없습니다. 팀장님의 첫 의견을 남겨주세요!")

except Exception as e:
    # 테이블이 없을 때를 대비한 안내 메시지
    st.warning("게시판 데이터를 불러오는 중입니다. (잠시 후 다시 시도해주세요)")
