import time
import requests
import streamlit as st
from st_keyup import st_keyup

# --- 설정 ---
API_BASE_URL = "http://s-extension-dev.onkakao.net" # API Ingress 주소
PAGE_TITLE = "LLM 검색어 시스템"
PAGE_ICON = "🔍"

st.set_page_config(page_title=PAGE_TITLE, page_icon=PAGE_ICON)

# --- 스타일링 (CSS) ---
st.markdown("""
<style>
    .stTextInput > div > div > input {
        font-size: 20px;
        padding: 10px;
    }
    .suggestion-box {
        background-color: #f0f2f6;
        border-radius: 5px;
        padding: 10px;
        margin-top: -15px;
        margin-bottom: 20px;
    }
    .suggestion-item {
        padding: 5px;
        cursor: pointer;
        font-size: 16px;
    }
    .suggestion-item:hover {
        background-color: #e0e2e6;
        color: #1f77b4;
    }
    .related-tag {
        display: inline-block;
        background-color: #e8f0fe;
        color: #1967d2;
        padding: 5px 10px;
        border-radius: 15px;
        margin: 5px;
        font-size: 14px;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

st.title(f"{PAGE_ICON} {PAGE_TITLE}")
st.write("KoGPT와 Qwen 모델이 자동완성 검색어와 연관검색어를 추천해줍니다.")

# --- 세션 상태 초기화 ---
if "query" not in st.session_state:
    st.session_state.query = ""
if "selected_keyword" not in st.session_state:
    st.session_state.selected_keyword = ""

# --- 검색창 ---
#query = st.text_input("검색어를 입력하세요", value=st.session_state.query, placeholder="예: 아메리카노", key="search_input")
query = st_keyup(
    "검색어를 입력하세요",
    value=st.session_state.selected_keyword if st.session_state.selected_keyword else "",
    placeholder="예: 아메리카노",
    key="search_input",
    debounce=300
)

# 사용자가 직접 타이핑을 시작하면 선택된 키워드 초기화 (새로운 검색 의도)
if query != st.session_state.selected_keyword:
    st.session_state.selected_keyword = ""

# --- 1. 자동완성 API 호출 (입력 중일 때) ---
if query and not st.session_state.selected_keyword:
    try:
        start_time = time.time()  # 시간 측정 시작

        # 자동완성 API 호출
        response = requests.get(
            f"{API_BASE_URL}/api/v1/auto/search",
            params={"q": query, "n": 5, "type": "full"},
            timeout=5.0  # 2초 넘으면 포기 (UX 보호)
        )

        latency = (time.time() - start_time) * 1000 # ms 단위 변환

        if response.status_code == 200:
            data = response.json()
            subkeys = data.get("subkeys", [])

            if subkeys:
                st.markdown(f'<div class="latency-metric">⚡ API Latency: {latency:.0f}ms</div>', unsafe_allow_html=True)
                st.markdown('<div class="suggestion-box">', unsafe_allow_html=True)

                for item in subkeys:
                    keyword = item['subkey']
                    prob = item['prob']

                    # 버튼 클릭 시 연관검색어 트리거
                    if st.button(f"{keyword}", key=f"btn_{keyword}", help=f"확률: {prob:.1%}"):
                        st.session_state.selected_keyword = keyword
                        st.rerun()

                st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.warning(f"API 응답 오류: {response.status_code}")

    except Exception as e:
        st.error(f"API 연결 실패 (혹시 서버가 꺼졌나요?): {e}")

# --- 2. 연관검색어 API 호출 (검색어 선택 시) ---
target_query = st.session_state.selected_keyword if st.session_state.selected_keyword else query

if target_query:
    st.divider()
    st.subheader(f"💡 '{target_query}'의 연관 검색어")

    # 로딩 바 표시
    with st.spinner("AI가 생각을 정리하고 있습니다..."):
        try:
            start_time = time.time()

            # 연관검색어 API 호출
            rel_response = requests.get(
                f"{API_BASE_URL}/api/v1/relkey/search",
                params={"q": target_query, "n": 8},
                timeout=30.0 # 생성 모델은 시간이 좀 걸릴 수 있음
            )

            latency = (time.time() - start_time) * 1000

            if rel_response.status_code == 200:
                rel_data = rel_response.json()
                related_keywords = rel_data.get("related_keywords", [])

                if related_keywords:
                    st.markdown(f'<div class="latency-metric">⚡ Generation Latency: {latency:.0f}ms</div>', unsafe_allow_html=True)

                    # 태그 형태로 예쁘게 보여주기
                    tags_html = ""
                    for item in related_keywords:
                        # SubkeyResponse 구조에 맞게 처리 (subkey, prob)
                        kw = item['subkey']
                        tags_html += f'<span class="related-tag"># {kw}</span>'

                    st.markdown(tags_html, unsafe_allow_html=True)
                else:
                    st.info("연관된 검색어를 찾지 못했습니다.")
            else:
                st.error(f"연관검색어 API 오류: {rel_response.status_code}")

        except Exception as e:
            st.error(f"연관검색어 API 연결 실패: {e}")