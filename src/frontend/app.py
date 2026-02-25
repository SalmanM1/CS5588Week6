"""
TruPharma GenAI Assistant  ·  Home
===================================
Main landing page: navigate to Safety Chat or Signal Heatmap Dashboard.
"""

import sys
from pathlib import Path

# ── Ensure project root is importable ─────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st
import streamlit.components.v1 as components

# ─── Page config (sidebar starts collapsed on homepage) ────────
st.set_page_config(
    page_title="TruPharma | Clinical Intelligence",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── Force-collapse sidebar on homepage even after navigation ─
components.html("""
<script>
(function() {
    const doc = window.parent.document;
    const sidebar = doc.querySelector('[data-testid="stSidebar"]');
    if (sidebar && sidebar.getAttribute('aria-expanded') !== 'false') {
        const btn = doc.querySelector('[data-testid="stSidebarCollapseButton"]');
        if (btn) btn.click();
    }
})();
</script>
""", height=0)

# ─── Hide built-in page nav ──────────────────────────────────
st.markdown("""
<style>
div[data-testid="stSidebarNav"] { display: none !important; }
section[data-testid="stSidebar"] nav { display: none !important; }
section[data-testid="stSidebar"] ul[role="list"] { display: none !important; }
section[data-testid="stSidebar"] > div:first-child { padding-top: 0rem !important; }
section[data-testid="stSidebar"] ul[data-testid="stSidebarNavItems"] { display: none !important; }
</style>
""", unsafe_allow_html=True)

# ─── Landing page styling ────────────────────────────────────
st.markdown("""<style>
.landing-title {
    font-size: 3.2rem;
    font-weight: 800;
    text-align: center;
    margin: 2rem 0 0.5rem 0;
    color: #111827;
    letter-spacing: -0.02em;
    line-height: 1.2;
}
.landing-subtitle {
    font-size: 1.25rem;
    color: #6b7280;
    text-align: center;
    margin-bottom: 3rem;
    font-weight: 600;
}
.nav-buttons {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1.25rem;
    max-width: 420px;
    margin: 0 auto;
}
.nav-btn-block {
    width: 100%;
    padding: 1.25rem 1.5rem;
    font-size: 1.1rem;
    font-weight: 700;
    border-radius: 14px;
    border: 2px solid #E5E7EB;
    background: #ffffff;
    color: #111827;
    box-shadow: 0 2px 4px rgba(0,0,0,0.06);
    transition: border-color 0.2s, box-shadow 0.2s;
}
.nav-btn-block:hover {
    border-color: #F2994A;
    box-shadow: 0 4px 12px rgba(242, 153, 74, 0.2);
}
.nav-btn-block.primary-demo {
    border-left: 6px solid #2E7D32;
    background: linear-gradient(135deg, #f0fdf4 0%, #ffffff 100%);
}
.nav-btn-block.heatmap {
    border-left: 6px solid #6366f1;
    background: linear-gradient(135deg, #eef2ff 0%, #ffffff 100%);
}
html, body,
p, h1, h2, h3, h4, h5, h6,
span, div, li, td, th, label, a,
input, textarea, select, button,
.stMarkdown, .stText, .stCaption {
    font-family: "Times New Roman", Times, serif !important;
    line-height: 1.4;
}
[data-testid="stIconMaterial"],
.material-symbols-rounded,
[data-testid="collapsedControl"] span,
span[class*="icon"] {
    font-family: "Material Symbols Rounded" !important;
}
</style>""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
#  MAIN LANDING
# ══════════════════════════════════════════════════════════════
st.markdown(
    "<div class='landing-title'>TruPharma GenAI Assistant</div>",
    unsafe_allow_html=True,
)
st.markdown(
    "<div class='landing-subtitle'>Clinical Intelligence · Drug Label Evidence RAG</div>",
    unsafe_allow_html=True,
)

# Two navigation buttons
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    st.markdown("<div class='nav-buttons'>", unsafe_allow_html=True)

    if st.button(
        "🟢 **Safety Chat**  \n*Drug-label questions, RAG answers, knowledge graph*",
        key="nav_safety_chat",
        use_container_width=True,
    ):
        st.switch_page("pages/primary_demo.py")

    if st.button(
        "📊 **Signal Heatmap Dashboard**  \n*Analyst disparity and signal visualization*",
        key="nav_heatmap",
        use_container_width=True,
    ):
        st.switch_page("pages/signal_heatmap.py")

    st.markdown("</div>", unsafe_allow_html=True)
