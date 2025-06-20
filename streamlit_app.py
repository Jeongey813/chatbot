import os
import datetime as dt
from typing import List, Dict, Any

import requests
import streamlit as st
from openai import OpenAI

###############################################################################
# CareerMate – Streamlit prototype                                            #
# --------------------------------------------------------------------------- #
# A profession‑aware assistant that curates news & events, gives explanations #
# and offers conversational feedback.                                         #
###############################################################################

st.set_page_config(page_title="CareerMate – Profession‑aware Chatbot", page_icon="💬", layout="wide")

# ──────────────────────────────────────────────────────────────────────────────
# Sidebar – user preferences & API keys
# ──────────────────────────────────────────────────────────────────────────────
st.sidebar.header("🔧 설정 / Settings")

openai_api_key = st.sidebar.text_input("OpenAI API Key", type="password", value=os.getenv("OPENAI_API_KEY", ""))
news_api_key = st.sidebar.text_input("News API Key (optional)", type="password", value=os.getenv("NEWS_API_KEY", ""))
event_api_key = st.sidebar.text_input("Eventbrite API Key (optional)", type="password", value=os.getenv("EVENTBRITE_API_KEY", ""))

profession = st.sidebar.text_input("🧑‍💼 직업 / 분야", placeholder="예: UI/UX 디자이너")
location = st.sidebar.text_input("📍 위치 (도시)", placeholder="예: Seoul")

st.sidebar.caption("API 키를 .streamlit/secrets.toml 또는 환경변수에 저장해 두면 더 편리합니다.")

# ──────────────────────────────────────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────────────────────────────────────
if not openai_api_key:
    st.error("❗ OpenAI API Key가 필요합니다.")
    st.stop()

# Create OpenAI client
client = OpenAI(api_key=openai_api_key)

# ──────────────────────────────────────────────────────────────────────────────
# Helper functions – external data fetch
# ──────────────────────────────────────────────────────────────────────────────

def _query_news(profession: str) -> List[Dict[str, str]]:
    """Fetch top 3 recent news headlines related to the profession."""
    if not news_api_key:
        return []
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": profession or "career",
        "language": "ko,en",
        "sortBy": "publishedAt",
        "pageSize": 3,
        "apiKey": news_api_key,
    }
    try:
        res = requests.get(url, params=params, timeout=10)
        res.raise_for_status()
        data = res.json()
        return [
            {"title": art["title"], "url": art["url"], "source": art["source"]["name"]}
            for art in data.get("articles", [])
        ]
    except Exception as e:
        st.warning(f"뉴스를 불러오는 데 실패했습니다: {e}")
        return []


def _query_events(location: str, profession: str) -> List[Dict[str, str]]:
    """Fetch upcoming events in the user's city (next 30 days)."""
    if not event_api_key or not location:
        return []

    url = "https://www.eventbriteapi.com/v3/events/search/"
    params = {
        "q": profession or "networking",
        "location.address": location,
        "start_date.range_start": dt.datetime.utcnow().isoformat() + "Z",
        "start_date.range_end": (dt.datetime.utcnow() + dt.timedelta(days=30)).isoformat() + "Z",
        "token": event_api_key,
        "expand": "venue",
    }
    try:
        res = requests.get(url, params=params, timeout=10)
        res.raise_for_status()
        data = res.json()
        events = []
        for ev in data.get("events", [])[:3]:
            events.append(
                {
                    "name": ev["name"]["text"],
                    "url": ev["url"],
                    "start": ev["start"]["local"][:10],
                    "venue": ev.get("venue", {}).get("name", ""),
                }
            )
        return events
    except Exception as e:
        st.warning(f"이벤트를 불러오는 데 실패했습니다: {e}")
        return []


# Cached wrappers
@st.cache_data(show_spinner=False)
def fetch_news_and_events(profession: str, location: str):
    return _query_news(profession), _query_events(location, profession)

# ──────────────────────────────────────────────────────────────────────────────
# System prompt builder
# ──────────────────────────────────────────────────────────────────────────────

def build_system_prompt() -> str:
    date_str = dt.datetime.now().strftime("%Y-%m-%d")
    base = (
        "You are CareerMate, a multilingual professional assistant. "
        "Today's date is "
        f"{date_str}."
    )
    if profession:
        base += f" The user's profession is '{profession}'."
    if location:
        base += f" The user is located in {location}."
    base += (
        " Curate relevant news and events, and provide clear, concise, and actionable feedback. "
        "When asked for a daily briefing, provide a bullet summary in Korean, then offer deeper dives."
    )
    return base

# ──────────────────────────────────────────────────────────────────────────────
# UI – main
# ──────────────────────────────────────────────────────────────────────────────

st.title("💬 CareerMate – 커리어메이트")

st.markdown(
    """
    **직업 맞춤형 뉴스·이벤트·피드백 챗봇**  
    원하는 정보를 물어보거나, **/brief** 명령어로 데일리 브리핑을 받아보세요.
    """
)

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages: List[Dict[str, Any]] = []
    st.session_state.messages.append({"role": "system", "content": build_system_prompt()})

# Display existing messages
for m in st.session_state.messages:
    if m["role"] == "system":
        continue  # don't show system prompt
    with st.chat_message(m["role"]):
        st.markdown(m["content"], unsafe_allow_html=True)

# Chat input
user_input = st.chat_input("메시지를 입력하세요… (/brief 로 데일리 브리핑)")

if user_input:

    # Store user message
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # Special command: /brief generates daily briefing using external data
    if user_input.strip().lower().startswith("/brief"):
        with st.spinner("뉴스와 이벤트를 모으는 중…"):
            news, events = fetch_news_and_events(profession, location)

        # Build briefing prompt
        briefing_context = """You gathered the following data:\n\n"""
        if news:
            briefing_context += "Recent news headlines:\n" + "\n".join(f"- {n['title']} ({n['source']})" for n in news) + "\n\n"
        if events:
            briefing_context += "Upcoming events:\n" + "\n".join(
                f"- {e['start']} {e['name']} @ {e['venue']}" for e in events
            ) + "\n\n"
        if not news and not events:
            briefing_context += "(No external data available)\n\n"
        briefing_context += "Please craft a Korean daily briefing in bullet points (max 120 words), then suggest next actions."

        # Add as system‑level augmentation
        st.session_state.messages.append({"role": "system", "content": briefing_context})

    # Call OpenAI chat completion
    with st.chat_message("assistant"):
        with st.spinner("답변 작성 중…"):
            response_chunks = client.chat.completions.create(
                model="gpt-4o-mini-turbo",  # or change to suitable model id
                messages=[
                    {"role": m["role"], "content": m["content"]}
                    for m in st.session_state.messages
                ],
                stream=True,
            )
            response_text = st.write_stream(response_chunks)

    # Save assistant response
    st.session_state.messages.append({"role": "assistant", "content": response_text})

# Footer
st.caption("Made with Streamlit • © 2025 CareerMate")
