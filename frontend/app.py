"""Executar da raiz: uv run --frozen streamlit run frontend/app.py."""

import streamlit as st

from frontend.pages.modules import PAGE_DESCRIPTIONS, render_page

st.set_page_config(page_title="Biosaúde | OPME", page_icon="🔴", layout="wide")
st.markdown(
    """<style>
    .stApp {background-color: #FFFFFF; color: #292D32;}
    [data-testid="stSidebar"] {background-color: #F4F5F7;}
    h1, h2, h3 {color: #292D32;}
    .brand {border-left: 4px solid #B91C1C; padding-left: 1rem; margin-bottom: 1.5rem;}
    </style>""",
    unsafe_allow_html=True,
)
st.sidebar.title("Biosaúde")
st.sidebar.caption("OPME • Automação supervisionada")
page = st.sidebar.radio("Navegação", options=list(PAGE_DESCRIPTIONS))
st.sidebar.divider()
st.sidebar.caption("MVP inicial • Integrações desativadas")
st.markdown('<div class="brand"><h1>Biosaúde OPME</h1></div>', unsafe_allow_html=True)
render_page(page)
