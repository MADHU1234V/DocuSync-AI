"""Streamlit user interface; API remains the authority for authentication and isolation."""

import requests
import streamlit as st

from src.config import get_settings

API_URL = get_settings().api_base_url
st.set_page_config(page_title="DocuSync AI", page_icon="📚", layout="wide")

for key, default in (("token", None), ("username", None), ("messages", [])):
    if key not in st.session_state:
        st.session_state[key] = default


def api_headers() -> dict:
    return {"Authorization": f"Bearer {st.session_state.token}"} if st.session_state.token else {}


def show_error(response: requests.Response) -> None:
    try:
        message = response.json().get("detail", response.text)
    except ValueError:
        message = response.text or "Request failed"
    st.error(message)


st.title("📚 DocuSync AI")
st.caption("A private question-answering workspace for your PDF documents.")

try:
    health_response = requests.get(f"{API_URL}/health", timeout=5)
    if health_response.ok and not health_response.json().get("ai_configured", False):
        st.warning("AI is not configured. Add a Google AI API key as GOOGLE_API_KEY in .env, then restart FastAPI. "
                   "The ADC setup script configures Vertex AI credentials, which this API-key configuration does not use.")
except requests.RequestException:
    st.error(f"The API server is unavailable at {API_URL}. Start FastAPI, then refresh this page.")

with st.sidebar:
    st.header("Account")
    if st.session_state.token:
        st.success(f"Signed in as **{st.session_state.username}**")
        if st.button("Log out", use_container_width=True):
            st.session_state.token = None
            st.session_state.username = None
            st.session_state.messages = []
            st.rerun()
    else:
        mode = st.radio("Account action", ["Log in", "Create account"], horizontal=True, label_visibility="collapsed")
        with st.form("auth_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            st.caption("Passwords must be at least 12 characters.")
            submitted = st.form_submit_button(mode, use_container_width=True)
        if submitted:
            try:
                if mode == "Create account":
                    response = requests.post(f"{API_URL}/register", json={"username": username, "password": password}, timeout=30)
                    if response.status_code == 201:
                        st.success("Account created. Log in with your new credentials.")
                    else:
                        show_error(response)
                else:
                    response = requests.post(f"{API_URL}/login", data={"username": username, "password": password}, timeout=30)
                    if response.ok:
                        result = response.json()
                        st.session_state.token = result["access_token"]
                        st.session_state.username = result["username"]
                        st.rerun()
                    show_error(response)
            except requests.RequestException:
                st.error(f"Cannot reach the API at {API_URL}. Start the FastAPI server first.")

if not st.session_state.token:
    st.info("Log in or create an account from the sidebar to open your private document vault.")
    st.stop()

manager_tab, chat_tab = st.tabs(["Document Manager", "Chat Interface"])
with manager_tab:
    st.subheader("Your documents")
    uploaded = st.file_uploader("Upload a text-based PDF", type=["pdf"], accept_multiple_files=False)
    if uploaded is not None and st.button("Upload and index", type="primary"):
        with st.spinner("Uploading and indexing…"):
            try:
                response = requests.post(
                    f"{API_URL}/upload-document", headers=api_headers(),
                    files={"file": (uploaded.name, uploaded.getvalue(), "application/pdf")}, timeout=(15, 600),
                )
                if response.status_code == 201:
                    st.success(f"Indexed {uploaded.name}")
                    st.rerun()
                show_error(response)
            except requests.RequestException as exc:
                st.error(f"Upload failed: {exc}")

    try:
        response = requests.get(f"{API_URL}/documents", headers=api_headers(), timeout=30)
        if response.ok:
            docs = response.json()
            if not docs:
                st.caption("No documents yet. Upload a PDF to get started.")
            for doc in docs:
                col_name, col_status, col_action = st.columns([5, 2, 1])
                col_name.write(f"**{doc['filename']}**\n\nAdded {doc['created_at']}")
                col_status.caption(doc["status"].capitalize())
                if col_action.button("Delete", key=f"delete_{doc['id']}"):
                    deletion = requests.delete(f"{API_URL}/documents/{doc['id']}", headers=api_headers(), timeout=30)
                    if deletion.ok:
                        st.rerun()
                    show_error(deletion)
        else:
            show_error(response)
    except requests.RequestException:
        st.error("Cannot reach the API service.")

with chat_tab:
    st.subheader("Ask your documents")
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message.get("sources"):
                with st.expander("Sources"):
                    for source in message["sources"]:
                        st.write(f"[{source['id']}] {source['filename']} — page {source['page']}")
    question = st.chat_input("Ask a question about your PDFs")
    if question:
        st.session_state.messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            with st.spinner("Searching your documents…"):
                try:
                    response = requests.post(f"{API_URL}/query", headers=api_headers(), json={"question": question}, timeout=(15, 180))
                    if response.ok:
                        result = response.json()
                        st.markdown(result["answer"])
                        if result.get("sources"):
                            with st.expander("Sources"):
                                for source in result["sources"]:
                                    st.write(f"[{source['id']}] {source['filename']} — page {source['page']}")
                        st.session_state.messages.append({"role": "assistant", "content": result["answer"], "sources": result.get("sources", [])})
                    else:
                        show_error(response)
                except requests.RequestException as exc:
                    st.error(f"Could not reach the API: {exc}")
