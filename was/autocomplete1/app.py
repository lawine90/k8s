import streamlit as st
import requests
import time
# 🌟 [삭제] st_keyup 제거 (기본 st.text_input 사용)
# from st_keyup import st_keyup

# --- 설정 ---
API_BASE_URL = "http://s-extension-dev.onkakao.net"
PAGE_TITLE = "LLM 검색어 시스템"
PAGE_ICON = "🔍"

# 모델의 응답 속도가 느리므로 타임아웃을 넉넉하게 설정
TIMEOUT_SECONDS = 60.0

st.set_page_config(page_title=PAGE_TITLE, page_icon=PAGE_ICON)

# --- 스타일링 (CSS) ---
st.markdown("""
<style>
    /* 기본 입력 필드 스타일 유지 */
    .stTextInput > div > div > input {
        font-size: 20px;
        padding: 10px;
    }
    /* 자동완성 박스: 왼쪽 컬럼에 사용 */
    .suggestion-box {
        background-color: #f0f2f6;
        border-radius: 5px;
        padding: 15px;
        margin-bottom: 20px;
        min-height: 200px;
    }
    /* 연관 검색어 태그: 오른쪽 컬럼에 사용 */
    .related-tag {
        display: inline-block;
        background-color: #e8f0fe;
        color: #1967d2;
        padding: 6px 12px;
        border-radius: 20px;
        margin: 5px;
        font-size: 15px;
        font-weight: 600;
        border: 1px solid #d2e3fc;
    }
    /* 응답 속도 표시 */
    .latency-metric {
        font-size: 12px;
        color: #888;
        text-align: right;
        margin-top: 5px;
    }
    /* Streamlit 기본 버튼 스타일 제거 및 텍스트 맞춤 */
    .stButton>button {
        width: 100%;
        text-align: left;
    }
</style>
""", unsafe_allow_html=True)

st.title(f"{PAGE_ICON} {PAGE_TITLE}")
st.write("KoGPT(자동완성)와 Qwen(연관검색어) 모델이 엔터 입력 시 결과를 보여줍니다.")

# --- 세션 상태 초기화 ---
if "submitted_query" not in st.session_state:
    st.session_state.submitted_query = ""

# --- 1. 검색창 및 폼 (엔터 입력 트리거) ---
with st.form("search_form"):
    # 🌟 [수정] 기본 st.text_input 사용 (엔터 입력 시 submit)
    query = st.text_input(
        "검색어를 입력하세요",
        placeholder="예: 아이폰 17",
        key="search_input_field"
    )
    # 🌟 검색 버튼 (엔터 입력과 동일하게 폼을 제출)
    submitted = st.form_submit_button("🔍 검색 (Enter)")

# 🌟 폼이 제출되었거나 (Enter), 이전에 제출된 쿼리가 있을 경우에만 실행
if submitted or st.session_state.submitted_query:
    if submitted and query:
        # 새로운 쿼리가 제출되면 세션에 저장
        st.session_state.submitted_query = query
        target_query = query
    elif st.session_state.submitted_query:
        target_query = st.session_state.submitted_query
    else:
        # 빈 쿼리 제출 시 무시
        st.stop()

    st.divider()

    # 2. 레이아웃 분할 (왼쪽: 자동완성, 오른쪽: 연관검색어)
    col1, col2 = st.columns(2)

    # === 왼쪽: 자동완성 (Auto) 서비스 호출 ===
    with col1:
        st.subheader("자동완성 후보 (KoGPT)")
        with st.spinner("자동완성 후보 로딩 중..."):
            try:
                start_time_auto = time.time()

                auto_response = requests.get(
                    f"{API_BASE_URL}/api/v1/auto/search",
                    params={"q": target_query, "n": 5, "type": "full"},
                    timeout=TIMEOUT_SECONDS
                )
                latency_auto = (time.time() - start_time_auto) * 1000

                if auto_response.status_code == 200:
                    data = auto_response.json()
                    subkeys = data.get("subkeys", [])

                    st.markdown(f'<div class="latency-metric">⚡ Latency: {latency_auto:.0f}ms</div>', unsafe_allow_html=True)
                    st.markdown('<div class="suggestion-box">', unsafe_allow_html=True)

                    if subkeys:
                        for item in subkeys:
                            # keyword = item.get('subkey', '')
                            # prob = item.get('prob', 0.0)
                            keyword = item[0]
                            prob = item[1]
                            st.markdown(f"**{keyword}** <small>({prob:.2%})</small>", unsafe_allow_html=True)
                    else:
                        st.info("자동완성 결과 없음.")

                    st.markdown('</div>', unsafe_allow_html=True)
                else:
                    st.error(f"자동완성 API 오류: {auto_response.status_code}")

            except requests.exceptions.Timeout:
                st.error(f"자동완성 API 타임아웃 발생 (>{TIMEOUT_SECONDS}s)")
            except Exception as e:
                st.error(f"자동완성 API 연결 실패: {e}")

    # === 오른쪽: 연관검색어 (Relkey) 서비스 호출 ===
    with col2:
        st.subheader("연관 검색어 생성 (Qwen)")
        with st.spinner("연관 키워드 생성 중... (LLM 추론)"):
            try:
                start_time_rel = time.time()

                rel_response = requests.get(
                    f"{API_BASE_URL}/api/v1/relkey/search",
                    params={"q": target_query, "n": 8},
                    timeout=TIMEOUT_SECONDS
                )

                latency_rel = (time.time() - start_time_rel) * 1000

                if rel_response.status_code == 200:
                    rel_data = rel_response.json()
                    related_keywords = rel_data.get("subkeys", []) # RelkeyResponse의 subkeys 사용

                    st.markdown(f'<div class="latency-metric">⚡ Generation Latency: {latency_rel:.0f}ms</div>', unsafe_allow_html=True)

                    if related_keywords:
                        tags_html = "".join([f'<span class="related-tag"># {kw}</span>' for kw in related_keywords])
                        st.markdown(tags_html, unsafe_allow_html=True)
                    else:
                        st.info("연관 키워드 생성 결과 없음.")
                else:
                    st.error(f"연관검색어 API 오류: {rel_response.status_code}")

            except requests.exceptions.Timeout:
                st.error(f"연관검색어 API 타임아웃 발생 (>{TIMEOUT_SECONDS}s)")
            except Exception as e:
                st.error(f"연관검색어 API 연결 실패: {e}")
