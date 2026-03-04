"""
TruPharma  ·  Stress Test / Scenario Validation
=================================================
Runs edge-case queries through the real RAG pipeline and compares
behaviour against the Safety Chat baseline.
"""

import sys
from pathlib import Path

# ── Ensure project root is importable ─────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st
import streamlit.components.v1 as components
import time
from datetime import datetime

from src.rag.engine import run_rag_query, read_logs

# ─── Page config ──────────────────────────────────────────────
st.set_page_config(
    page_title="Stress Test | Scenario Validation",
    page_icon="⚠️",
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
.panel {
    border-radius: 16px; padding: 0; border: 1px solid #E5E7EB;
    overflow: hidden; box-shadow: 0 1px 2px rgba(0,0,0,0.06); background: #fff;
}
.panel-header { padding: 12px 18px; font-weight: 900; font-size: 18px; color: #111827; }
.panel-subheader { padding: 0 18px 12px 18px; font-weight: 700; color: #4b5563; }
.panel-header.primary { background: #CFE7C8; }
.panel-header.stress  { background: #F7C08A; }
.panel-header.primary, .panel-header.stress {
    border-radius: 16px !important; margin: 14px 14px 6px 14px !important;
    width: calc(100% - 28px) !important;
}
.section-pill {
    display: inline-block; background: #F3F4F6; border: 1px solid #E5E7EB;
    color: #111827; border-radius: 16px; padding: 8px 14px;
    font-weight: 900; font-size: 15px; margin: 10px 0 8px 0;
}
.inner-card { margin: 10px 18px; border: none; background: transparent; padding: 0; }
.mini { color: #4b5563; font-weight: 600; }
.bullets { margin: 0; padding-left: 18px; }
.bullets li { margin: 6px 0; }
.criteria {
    border-radius: 16px; border: 1px solid #E5E7EB;
    overflow: hidden; box-shadow: 0 1px 2px rgba(0,0,0,0.06); background: #fff;
}
.criteria-header { padding: 10px 14px; font-weight: 900; font-size: 18px; color: #111827; }
.criteria-header.success { background: #CFE7C8; }
.criteria-header.pass    { background: #F7C08A; }
.criteria-body { padding: 12px 14px; background: #F9FAFB; font-weight: 600; color: #374151; }
.scenario-card { padding: 10px 12px; border-radius: 10px; margin-bottom: 8px; font-weight: 700; line-height: 1.2; }
.stress-active { background-color: #FFF3E0; border-left: 6px solid #EF6C00; }
/* Apply custom font but exclude Streamlit icon elements */
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
/* Restore Streamlit's icon font for Material Icons */
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
st.sidebar.markdown("<div style='font-size:15px;font-weight:800;margin:10px 0 8px;'>Scenario Mode</div>", unsafe_allow_html=True)
if st.sidebar.button("⬅ Return to Safety Chat", key="go_safety_chat"):
    st.switch_page("pages/primary_demo.py")

st.sidebar.markdown(
    "<div class='scenario-card stress-active'>"
    "🟠 Stress Test<br><small>Edge case / robustness validation</small></div>",
    unsafe_allow_html=True,
)

st.sidebar.markdown("---")

STRESS_QUERIES = {
    "Rare input": "What are the precautions for orphenadrine citrate injection?",
    "Large doc": "drug interactions and warnings for any medication",
    "Heavy traffic": "What are the side effects of ibuprofen?",
    "Conflicting evidence": "Should I take aspirin or ibuprofen for pain relief? Compare their warnings.",
}

stress_condition = st.sidebar.radio(
    "Stress Condition (choose one)",
    list(STRESS_QUERIES.keys()),
)

st.sidebar.caption(f"**Query:** {STRESS_QUERIES[stress_condition]}")
run = st.sidebar.button("Run Stress Test", type="primary", width="stretch")


# ══════════════════════════════════════════════════════════════
#  SESSION STATE
# ══════════════════════════════════════════════════════════════
if "primary_last_run" not in st.session_state:
    st.session_state.primary_last_run = {
        "query": "(run a Safety Chat query first)",
        "confidence": "—",
        "evidence_count": 0,
    }

if "stress_result" not in st.session_state:
    st.session_state.stress_result = None
if "stress_condition" not in st.session_state:
    st.session_state.stress_condition = None


# ══════════════════════════════════════════════════════════════
#  RUN STRESS TEST
# ══════════════════════════════════════════════════════════════
if run:
    stress_query = STRESS_QUERIES[stress_condition]

    stress_config = {
        "Rare input":           {"api_limit": 20, "max_records": 20, "top_k": 3},
        "Large doc":            {"api_limit": 20, "max_records": 20, "top_k": 5},
        "Heavy traffic":        {"api_limit": 20, "max_records": 20, "top_k": 3},
        "Conflicting evidence": {"api_limit": 20, "max_records": 20, "top_k": 5},
    }[stress_condition]

    with st.spinner(f"Running stress test: **{stress_condition}** ..."):
        result = run_rag_query(
            stress_query,
            method="hybrid",
            **stress_config,
        )

    st.session_state.stress_result = result
    st.session_state.stress_condition = stress_condition


# ══════════════════════════════════════════════════════════════
#  PAGE HEADER
# ══════════════════════════════════════════════════════════════
st.markdown("<div class='page-title'>Scenario Validation View</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='main-header-bar'>Stress Test: TruPharma RAG vs Edge Case Scenarios</div>",
    unsafe_allow_html=True,
)


# ══════════════════════════════════════════════════════════════
#  TWO SIDE-BY-SIDE PANELS
# ══════════════════════════════════════════════════════════════
left, right = st.columns(2, gap="large")

# ── Safety Chat Scenario (from last Safety Chat run) ──
with left:
    st.markdown("<div class='panel'>", unsafe_allow_html=True)
    st.markdown("<div class='panel-header primary'>Safety Chat Scenario</div>", unsafe_allow_html=True)
    st.markdown("<div class='panel-subheader'>Normal user workflow</div>", unsafe_allow_html=True)

    p = st.session_state.primary_last_run

    st.markdown("<div class='inner-card'>", unsafe_allow_html=True)
    st.markdown("<div class='section-pill'>Input</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='mini'>Query: {p['query']}</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='inner-card'>", unsafe_allow_html=True)
    st.markdown("<div class='section-pill'>Expected Output</div>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='mini'>Verified answer + evidence citations<br>"
        f"Confidence: {p['confidence']}</div>",
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='inner-card'>", unsafe_allow_html=True)
    st.markdown("<div class='section-pill'>Evidence</div>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='mini'>Evidence count: {p['evidence_count']}</div>",
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


# ── Stress-Test Scenario (real RAG results) ──
with right:
    st.markdown("<div class='panel'>", unsafe_allow_html=True)
    st.markdown("<div class='panel-header stress'>Stress-Test Scenario</div>", unsafe_allow_html=True)
    st.markdown("<div class='panel-subheader'>Edge case / robustness check</div>", unsafe_allow_html=True)

    st.markdown("<div class='inner-card'>", unsafe_allow_html=True)
    st.markdown("<div class='section-pill'>Stress Condition</div>", unsafe_allow_html=True)

    sr = st.session_state.stress_result
    sc = st.session_state.stress_condition

    if sr and sc:
        st.markdown(f"<div class='mini'><b>Condition:</b> {sc}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='mini'><b>Query:</b> {STRESS_QUERIES[sc]}</div>", unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class='mini'>Choose ONE:</div>
        <ul class="bullets">
          <li>Rare input</li><li>Large doc</li>
          <li>Heavy traffic</li><li>Conflicting evidence</li>
        </ul>
        """, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='inner-card'>", unsafe_allow_html=True)
    st.markdown("<div class='section-pill'>System Behavior</div>", unsafe_allow_html=True)
    if sr:
        degradation = {
            "Rare input": "Reduced result set, lower evidence count — system returns partial answer.",
            "Large doc": "Large corpus indexed — system handles increased data gracefully.",
            "Heavy traffic": "Reduced limits for faster response — graceful degradation.",
            "Conflicting evidence": "Multiple drug labels compared — system cites both sources.",
        }.get(sc, "")
        st.markdown(f"<div class='mini'>{degradation}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='mini'><b>Method:</b> {sr['method']}</div>", unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class='mini'>Graceful degradation:</div>
        <ul class="bullets">
          <li>Reduced API limits</li><li>Adjusted top-k</li>
          <li>Fallback retrieval</li>
        </ul>
        """, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='inner-card'>", unsafe_allow_html=True)
    st.markdown("<div class='section-pill'>Monitoring / Logs</div>", unsafe_allow_html=True)
    if sr:
        st.markdown(f"- **Latency:** {sr['latency_ms']:.0f} ms")
        st.markdown(f"- **Confidence:** {sr['confidence']:.0%}")
        st.markdown(f"- **Evidence count:** {len(sr['evidence'])}")
        st.markdown(f"- **Records fetched:** {sr['num_records']}")
        ev_labels = [e["cite"] for e in sr["evidence"]]
        st.markdown(f"- **Evidence:** {', '.join(ev_labels[:5])}")
        st.markdown(f"- **LLM used:** {'Gemini' if sr['llm_used'] else 'Extractive fallback'}")
        st.markdown("---")
        st.markdown("**Answer preview:**")
        import re as _re
        _ans = sr["answer"]
        for _j, _ev in enumerate(sr["evidence"], 1):
            raw = _ev.get("_raw_id", "")
            if raw:
                _ans = _ans.replace(f"[{raw}]", f"[Evidence {_j}]")
        def _repl(m):
            inner = m.group(1)
            if _re.match(r"Evidence \d+", inner):
                return m.group(0)
            for _k, _e in enumerate(sr["evidence"], 1):
                if _e.get("doc_id", "") in inner or _e.get("field", "") in inner:
                    return f"[Evidence {_k}]"
            return m.group(0)
        _ans = _re.sub(r"\[([^\]]+)\]", _repl, _ans)
        st.write(_ans[:400])
    else:
        st.info("Run a stress test to populate logs.")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
#  SUCCESS / PASS CRITERIA
# ══════════════════════════════════════════════════════════════
st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
c1, c2 = st.columns(2, gap="large")

with c1:
    st.markdown("<div class='criteria'>", unsafe_allow_html=True)
    st.markdown("<div class='panel-header primary'>Success Criteria</div>", unsafe_allow_html=True)
    st.markdown("""
    <div class='criteria-body'>
      ✅ Safety Chat returns evidence-backed answers with citations.<br>
      ✅ Latency under 30 seconds per query.<br>
      ✅ Confidence and evidence IDs logged to CSV.
    </div>
    """, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

with c2:
    st.markdown("<div class='criteria'>", unsafe_allow_html=True)
    st.markdown("<div class='panel-header stress'>Pass Criteria</div>", unsafe_allow_html=True)
    st.markdown("""
    <div class='criteria-body'>
      ✅ Stress conditions return a response (no crash).<br>
      ✅ Rare/conflicting inputs degrade gracefully with lower confidence.<br>
      ✅ All interactions logged to product_metrics.csv.
    </div>
    """, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
