"""
TruPharma  ·  Signal Heatmap Dashboard
=======================================
Analyst disparity and signal visualization.
"""

import sys
from pathlib import Path

# ── Ensure project root is importable ─────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st
import streamlit.components.v1 as components

# ─── Page config ──────────────────────────────────────────────
st.set_page_config(
    page_title="Signal Heatmap | TruPharma",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Force-expand sidebar on subpages after navigation ───────
components.html("""
<script>
(function() {
    const doc = window.parent.document;
    const sidebar = doc.querySelector('[data-testid="stSidebar"]');
    if (sidebar && sidebar.getAttribute('aria-expanded') === 'false') {
        const btn = doc.querySelector('[data-testid="collapsedControl"]');
        if (btn) btn.click();
    }
})();
</script>
""", height=0)

# ─── Hide built-in nav ───────────────────────────────────────
st.markdown("""
<style>
div[data-testid="stSidebarNav"] { display: none !important; }
section[data-testid="stSidebar"] nav { display: none !important; }
section[data-testid="stSidebar"] ul[role="list"] { display: none !important; }
section[data-testid="stSidebar"] > div:first-child { padding-top: 0rem !important; }
section[data-testid="stSidebar"] ul[data-testid="stSidebarNavItems"] { display: none !important; }
</style>
""", unsafe_allow_html=True)

# ─── Styling ──────────────────────────────────────────────────
st.markdown("""<style>
.main-header-bar {
    background: linear-gradient(90deg, #F2994A, #EB5757);
    color: white; padding: 12px 16px; border-radius: 10px;
    font-weight: 600; margin-bottom: 14px;
}
.page-title  { font-size: 34px; font-weight: 800; margin-bottom: 4px; }
.page-subtitle { color: #6b7280; font-weight: 600; margin-bottom: 14px; }
html, body,
p, h1, h2, h3, h4, h5, h6,
span, div, li, td, th, label, a,
input, textarea, select, button,
.stMarkdown, .stText, .stCaption,
[data-testid="stMetricValue"],
[data-testid="stMetricLabel"] {
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
#  SIDEBAR
# ══════════════════════════════════════════════════════════════
if st.sidebar.button("⬅ Return to Home", key="go_home"):
    st.switch_page("app.py")

st.sidebar.markdown(
    "<div style='font-size:15px;font-weight:800;margin:10px 0 8px;'>Signal Heatmap Dashboard</div>",
    unsafe_allow_html=True,
)
st.sidebar.caption("Analyst disparity and signal visualization.")


# ══════════════════════════════════════════════════════════════
#  MAIN CONTENT
# ══════════════════════════════════════════════════════════════
st.markdown("<div class='page-title'>Signal Heatmap Dashboard</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='page-subtitle'>Analyst disparity and signal visualization</div>",
    unsafe_allow_html=True,
)
st.markdown(
    "<div class='main-header-bar'>TruPharma Signal Heatmap — Placeholder</div>",
    unsafe_allow_html=True,
)

st.info(
    "This page is a placeholder for the Signal Heatmap Dashboard. "
    "Connect your signal or disparity data and visualizations here."
)
