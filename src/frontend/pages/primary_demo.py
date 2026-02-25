"""
TruPharma GenAI Assistant  ·  Safety Chat
==========================================
Streamlit page: drug-label evidence RAG — openFDA pipeline,
grounded answers, knowledge graph, metrics.
"""

import sys
from pathlib import Path

# ── Ensure project root is importable ─────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime
import time

from src.rag.engine import run_rag_query, read_logs

# ─── Page config ──────────────────────────────────────────────
st.set_page_config(
    page_title="Safety Chat | TruPharma RAG",
    page_icon="🩺",
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

# ─── App styling ──────────────────────────────────────────────
st.markdown("""<style>
.main-header-bar {
    background: linear-gradient(90deg, #F2994A, #EB5757);
    color: white; padding: 12px 16px; border-radius: 10px;
    font-weight: 600; margin-bottom: 14px;
}
.scenario-card {
    padding: 10px 12px; border-radius: 10px;
    margin-bottom: 8px; font-weight: 700; line-height: 1.2;
}
.primary-active {
    background-color: #E8F5E9; border-left: 6px solid #2E7D32;
}
.card {
    background: #FFFFFF; border: 1px solid #E5E7EB;
    border-radius: 14px; padding: 14px 16px;
    box-shadow: 0 1px 2px rgba(0,0,0,0.06); margin-bottom: 14px;
}
.card-title { font-weight: 800; font-size: 16px; margin-bottom: 8px; }
.card-title.response { color: #1f7a8c; }
.card-title.evidence { color: #d35400; }
.card-title.metrics  { color: #2e7d32; }
.card-title.logs     { color: #6b7280; }
.kg-pill {
    display: inline-block; padding: 5px 14px; margin: 3px 4px;
    border-radius: 20px; font-size: 13px; font-weight: 700;
    line-height: 1.4;
}
.kg-pill.ingredient { background: #e0f2f1; color: #00695c; border: 1px solid #b2dfdb; }
.kg-pill.interaction { background: #fff3e0; color: #e65100; border: 1px solid #ffe0b2; }
.kg-pill.co-reported { background: #e3f2fd; color: #1565c0; border: 1px solid #bbdefb; }
.kg-pill.reaction { background: #fce4ec; color: #b71c1c; border: 1px solid #f8bbd0; }
.kg-section-label {
    font-weight: 800; font-size: 14px; margin: 12px 0 6px 0;
    padding-bottom: 4px; border-bottom: 2px solid #ede9fe;
    color: #5b21b6;
}
.kg-summary-card {
    background: linear-gradient(135deg, #faf5ff 0%, #ffffff 100%);
    border: 1px solid #ede9fe; border-radius: 12px;
    padding: 10px 14px; text-align: center;
}
.kg-summary-card .label { font-size: 11px; color: #6b7280; font-weight: 700; text-transform: uppercase; }
.kg-summary-card .value { font-size: 18px; font-weight: 800; color: #1f2937; margin: 2px 0; }
.kg-summary-card .sub { font-size: 11px; color: #9ca3af; }
.kg-risk-badge {
    display: inline-block; padding: 3px 10px; border-radius: 8px;
    font-weight: 800; font-size: 13px;
}
.kg-risk-badge.low { background: #d1fae5; color: #065f46; }
.kg-risk-badge.moderate { background: #fef3c7; color: #92400e; }
.kg-risk-badge.high { background: #fee2e2; color: #991b1b; }
.bullets { margin: 0; padding-left: 18px; }
.bullets li { margin: 6px 0; }
.pill-link {
    flex: 1; text-align: center; padding: 14px;
    border-radius: 14px; border: 1px solid #d1d5db;
    background: #ffffff; font-weight: 800; color: #111827;
    text-decoration: none !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.06);
}
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
#  SESSION STATE
# ══════════════════════════════════════════════════════════════
if "active_panel" not in st.session_state:
    st.session_state.active_panel = "ALL"
if "result" not in st.session_state:
    st.session_state.result = None
if "logs" not in st.session_state:
    st.session_state.logs = []

def set_panel(name: str):
    st.session_state.active_panel = (
        "ALL" if st.session_state.active_panel == name else name
    )


# ══════════════════════════════════════════════════════════════
#  SIDEBAR
# ══════════════════════════════════════════════════════════════
if st.sidebar.button("⬅ Return to Home", key="go_home"):
    st.switch_page("app.py")

st.sidebar.title("Scenario Mode")
st.sidebar.markdown(
    "<div class='scenario-card primary-active'>"
    "🟢 Safety Chat<br><small>Normal user workflow</small></div>",
    unsafe_allow_html=True,
)
if st.sidebar.button("⚠️ Go to Stress Test", key="go_stress"):
    st.switch_page("pages/stress_test.py")

st.sidebar.markdown("---")

# Example queries for convenience
st.sidebar.subheader("Example Queries")
EXAMPLES = [
    "-- Select an example --",
    "What are the drug interactions for ibuprofen?",
    "What is the recommended dosage for acetaminophen and are there any warnings?",
    "I am taking aspirin daily. What should I know about overdosage and when to stop use?",
    "What safety warnings exist for caffeine-containing products?",
    "What are the active ingredients in Tylenol and what are the drug interactions?",
    "What is the projected cost of antimicrobial resistance to GDP in 2050?",
]
example = st.sidebar.selectbox("Pick a sample question:", EXAMPLES, index=0)

st.sidebar.subheader("Query Input")
default_q = "" if example == EXAMPLES[0] else example
query_text = st.sidebar.text_area(
    "Enter your drug-label question:",
    value=default_q,
    placeholder="e.g. What are the side effects of ibuprofen?",
    height=100,
)

# ── Advanced settings (collapsible) ──
with st.sidebar.expander("Advanced Settings"):
    method = st.selectbox(
        "Retrieval method",
        ["hybrid", "dense", "sparse"],
        index=0,
    )
    top_k = st.slider("Top-K evidence", 3, 10, 5)
    gemini_key = st.text_input(
        "Google Gemini API key (optional)",
        type="password",
        help="If provided, answers are generated by Gemini 2.0 Flash. "
             "Otherwise, a rule-based extractive fallback is used.",
    )

run = st.sidebar.button("🔍 Run RAG Query", type="primary", width="stretch")

st.sidebar.markdown("---")
if st.sidebar.button("🔄 Reset Session"):
    st.session_state.clear()
    st.rerun()


# ══════════════════════════════════════════════════════════════
#  RUN LOGIC  (executes BEFORE rendering so state is updated)
# ══════════════════════════════════════════════════════════════
if run and query_text:
    with st.spinner("Fetching FDA drug labels and running RAG pipeline..."):
        result = run_rag_query(
            query_text,
            gemini_key=gemini_key,
            method=method,
            top_k=top_k,
            use_rerank=False,
        )
    st.session_state.result = result

    # Store for stress-test comparison page
    st.session_state.primary_last_run = {
        "query": query_text,
        "confidence": f"{result['confidence']:.0%}",
        "evidence_count": len(result["evidence"]),
    }

    st.session_state.logs.append(
        f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]  "
        f"Query completed in {result['latency_ms']} ms  ·  "
        f"Evidence: {len(result['evidence'])}  ·  "
        f"Confidence: {result['confidence']:.0%}"
    )

elif run and not query_text:
    st.sidebar.warning("Please enter a query first.")


# ══════════════════════════════════════════════════════════════
#  MAIN HEADER
# ══════════════════════════════════════════════════════════════
st.markdown("## TruPharma GenAI Assistant")
st.markdown(
    "<div class='main-header-bar'>Safety Chat — Drug Label Evidence RAG</div>",
    unsafe_allow_html=True,
)

# ── Pill row ──
c1, c2, c3, c4, c5 = st.columns(5, gap="small")
c1.button("Response", width="stretch",
           type="primary" if st.session_state.active_panel == "Response" else "secondary",
           key="pill_response", on_click=set_panel, args=("Response",))
c2.button("Knowledge Graph", width="stretch",
           type="primary" if st.session_state.active_panel == "KG" else "secondary",
           key="pill_kg", on_click=set_panel, args=("KG",))
c3.button("Evidence / Artifacts", width="stretch",
           type="primary" if st.session_state.active_panel == "Evidence" else "secondary",
           key="pill_evidence", on_click=set_panel, args=("Evidence",))
c4.button("Metrics & Monitoring", width="stretch",
           type="primary" if st.session_state.active_panel == "Metrics" else "secondary",
           key="pill_metrics", on_click=set_panel, args=("Metrics",))
c5.button("Logs", width="stretch",
           type="primary" if st.session_state.active_panel == "Logs" else "secondary",
           key="pill_logs", on_click=set_panel, args=("Logs",))

st.caption("Click a pill to focus; click again to return to the full dashboard view.")


# ══════════════════════════════════════════════════════════════
#  RENDER HELPERS
# ══════════════════════════════════════════════════════════════

def _normalize_citations(answer: str, evidence: list) -> str:
    """Replace any leftover raw chunk-ID citations with [Evidence N] labels."""
    import re
    for i, ev in enumerate(evidence, 1):
        raw_id = ev.get("_raw_id", "")
        if raw_id:
            answer = answer.replace(f"[{raw_id}]", f"[Evidence {i}]")
    # Catch any remaining bracket citations that aren't already [Evidence N]
    def _replace_unknown(m):
        inner = m.group(1)
        if re.match(r"Evidence \d+", inner):
            return m.group(0)
        for j, ev in enumerate(evidence, 1):
            if ev.get("doc_id", "") in inner or ev.get("field", "") in inner:
                return f"[Evidence {j}]"
        return m.group(0)
    answer = re.sub(r"\[([^\]]+)\]", _replace_unknown, answer)
    return answer


def render_response():
    st.markdown(
        "<div class='card'><div class='card-title response'>Response Panel</div>",
        unsafe_allow_html=True,
    )
    r = st.session_state.result
    if not r:
        st.info("Enter a drug-label question in the sidebar and click **Run RAG Query**.")
    else:
        st.markdown(f"**Confidence:** {r['confidence']:.0%}")
        llm_label = "Gemini 2.0 Flash" if r["llm_used"] else "Extractive fallback"
        st.markdown(f"**Generator:** {llm_label}")
        st.markdown("---")
        display_answer = _normalize_citations(r["answer"], r.get("evidence", []))
        st.markdown(display_answer)
    st.markdown("</div>", unsafe_allow_html=True)


def render_evidence():
    st.markdown(
        "<div class='card'><div class='card-title evidence'>Evidence / Artifacts</div>",
        unsafe_allow_html=True,
    )
    r = st.session_state.result
    if not r or not r["evidence"]:
        st.info("Evidence will appear here after running a query.")
    else:
        for i, ev in enumerate(r["evidence"], 1):
            with st.expander(f"Evidence {i}  ·  field: {ev['field']}"):
                st.markdown(f"**Document:** `{ev['doc_id']}`")
                st.markdown(f"**Field:** `{ev['field']}`")
                st.markdown("**Content:**")
                st.text(ev["content"][:600])
    st.markdown("</div>", unsafe_allow_html=True)


def _enrich_kg_data(ingredients, interactions, co_reported, reactions):
    """Derive severity, importance, and summary metrics from raw KG data."""
    max_rxn = max((r.get("report_count", 0) for r in reactions), default=1) or 1
    enriched_rx = []
    for rx in reactions:
        cnt = rx.get("report_count", 0)
        pct = cnt / max_rxn
        sev = "severe" if pct > 0.66 else ("moderate" if pct > 0.33 else "mild")
        enriched_rx.append({**rx, "_severity": sev, "_pct": round(pct * 100, 1), "_importance": pct})

    enriched_ix = []
    for ix in interactions:
        desc = (ix.get("description") or "").lower()
        if any(w in desc for w in ("contraindicated", "severe", "fatal", "death", "serious")):
            sev = "severe"
        elif any(w in desc for w in ("caution", "monitor", "moderate", "avoid", "careful")):
            sev = "moderate"
        else:
            sev = "mild"
        enriched_ix.append({**ix, "_severity": sev})

    max_co = max((c.get("report_count", 0) for c in co_reported), default=1) or 1
    enriched_co = []
    for cr in co_reported:
        cnt = cr.get("report_count", 0)
        enriched_co.append({**cr, "_pct": round(cnt / max_co * 100, 1), "_importance": cnt / max_co})

    most_common_rxn = max(enriched_rx, key=lambda r: r.get("report_count", 0)) if enriched_rx else None
    most_severe_ix = next(
        (ix for ix in enriched_ix if ix["_severity"] == "severe"),
        enriched_ix[0] if enriched_ix else None,
    )
    return {
        "ingredients": ingredients,
        "interactions": enriched_ix,
        "co_reported": enriched_co,
        "reactions": enriched_rx,
        "most_common_rxn": most_common_rxn,
        "most_severe_ix": most_severe_ix,
    }


def _build_kg_network_html(drug_name, ingredients, interactions, co_reported, reactions):
    """Build a full decision-support KG visualization with vis.js."""
    import json as _json, math

    nodes, edges, details_map = [], [], {}
    nid = 0
    RADIUS = 210

    # ── Center node ──
    center_id = nid
    nodes.append({
        "id": center_id, "label": drug_name.upper(),
        "x": 0, "y": 0, "fixed": {"x": True, "y": True},
        "color": {"background": "#7c3aed", "border": "#5b21b6",
                  "highlight": {"background": "#8b5cf6", "border": "#5b21b6"}},
        "font": {"color": "#fff", "size": 16, "face": "Times New Roman", "bold": True},
        "shape": "box", "borderWidth": 2,
        "margin": {"top": 10, "bottom": 10, "left": 14, "right": 14},
    })
    details_map[center_id] = {
        "name": drug_name.title(), "type_label": "Queried Drug", "color": "#7c3aed",
        "fields": [{"label": "Role", "value": "Central query subject"},
                    {"label": "Data sources", "value": "FDA labels, FAERS, openFDA"}],
    }

    # ── Category definitions ──
    categories = []
    if ingredients:
        categories.append(("ingredient", ingredients[:8], "#e0f2f1", "#00897b", "contains"))
    if interactions:
        categories.append(("interaction", interactions[:8], "#fff3e0", "#f57c00", "interacts"))
    if co_reported:
        categories.append(("co_reported", co_reported[:8], "#e3f2fd", "#1976d2", "co-reported"))
    if reactions:
        categories.append(("reaction", reactions[:8], "#fce4ec", "#c62828", "adverse rxn"))

    n_cat = len(categories)
    for ci, (cat, items, bg, border, edge_label) in enumerate(categories):
        sector_start = (2 * math.pi * ci / n_cat) - math.pi / 2
        sector_span = 2 * math.pi / n_cat
        n = len(items)
        for idx, item in enumerate(items):
            nid += 1
            angle = sector_start + sector_span * (idx + 1) / (n + 1)
            x = round(RADIUS * math.cos(angle))
            y = round(RADIUS * math.sin(angle))

            importance = item.get("_importance", 0.5)
            font_sz = round(11 + importance * 5)
            margin_v = round(6 + importance * 5)
            margin_h = round(10 + importance * 4)
            bw = round(1 + importance * 2, 1)
            edge_w = round(1.0 + importance * 2.5, 1)
            sev = item.get("_severity", "")
            dashes = (sev == "mild") if sev else False

            if cat == "ingredient":
                label = item["ingredient"]
                if item.get("strength"):
                    label += f"\n({item['strength']})"
                det_fields = [
                    {"label": "Dosage / Strength", "value": item.get("strength") or "See label"},
                    {"label": "Clinical relevance", "value": "Check for sodium load, allergens, or inactive excipients"},
                    {"label": "Source", "value": "FDA drug label"},
                ]
            elif cat == "interaction":
                label = item["drug_name"]
                desc = item.get("description") or "No description available"
                det_fields = [
                    {"label": "Clinical severity", "value": sev.title(), "badge": sev},
                    {"label": "Mechanism", "value": (desc[:160] + "...") if len(desc) > 160 else desc},
                    {"label": "Recommendation", "value": "Consult prescribing information"},
                    {"label": "Evidence", "value": "FDA label-derived"},
                ]
            elif cat == "co_reported":
                label = item["drug_name"]
                cnt = item.get("report_count", 0)
                det_fields = [
                    {"label": "Co-occurrence reports", "value": f"{cnt:,}"},
                    {"label": "Relative frequency", "value": f"{item.get('_pct', 0):.0f}%"},
                    {"label": "Source", "value": "FAERS"},
                ]
            else:
                label = item["reaction"]
                cnt = item.get("report_count", 0)
                det_fields = [
                    {"label": "Report count", "value": f"{cnt:,}"},
                    {"label": "Relative frequency", "value": f"{item.get('_pct', 0):.0f}%"},
                    {"label": "Severity", "value": sev.title(), "badge": sev},
                    {"label": "Onset timing", "value": "Data not available"},
                    {"label": "Source", "value": "FAERS"},
                ]

            nodes.append({
                "id": nid, "label": label, "x": x, "y": y,
                "color": {"background": bg, "border": border},
                "font": {"size": font_sz, "face": "Times New Roman"},
                "shape": "box", "borderWidth": bw,
                "margin": {"top": margin_v, "bottom": margin_v,
                           "left": margin_h, "right": margin_h},
            })
            edges.append({
                "id": f"e{nid}", "from": center_id, "to": nid,
                "label": edge_label, "width": edge_w,
                "font": {"size": 9, "color": "#999"},
                "color": {"color": border},
                "dashes": dashes,
            })
            type_labels = {"ingredient": "Active Ingredient", "interaction": "Drug Interaction",
                           "co_reported": "Co-Reported Drug", "reaction": "Adverse Reaction"}
            details_map[nid] = {
                "name": label.replace("\n", " "), "type_label": type_labels[cat],
                "color": border, "fields": det_fields,
            }

    nj = _json.dumps(nodes)
    ej = _json.dumps(edges)
    dj = _json.dumps(details_map)

    return f"""<html><head>
<script src="https://unpkg.com/vis-network@9.1.6/standalone/umd/vis-network.min.js"></script>
<style>
*{{box-sizing:border-box}}
body{{margin:0;padding:0;background:transparent;font-family:"Times New Roman",serif}}
#kg-root{{position:relative;width:100%}}

/* ── toolbar ── */
#kg-toolbar{{display:flex;gap:6px;align-items:center;padding:6px 8px;
  background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px 10px 0 0}}
#kg-search{{flex:1;max-width:220px;padding:5px 10px;border:1px solid #d1d5db;border-radius:7px;
  font-size:12px;font-family:inherit;outline:none}}
#kg-search:focus{{border-color:#7c3aed;box-shadow:0 0 0 2px rgba(124,58,237,.15)}}
.tb-btn{{padding:5px 11px;border:1px solid #d1d5db;border-radius:7px;background:#fff;
  font-size:11px;font-weight:700;cursor:pointer;font-family:inherit;color:#374151;
  transition:background .12s,box-shadow .12s}}
.tb-btn:hover{{background:#f3f4f6;box-shadow:0 1px 4px rgba(0,0,0,.08)}}
.tb-btn.active{{background:#ede9fe;border-color:#7c3aed;color:#5b21b6}}

/* ── graph canvas ── */
#kg-net{{width:100%;height:470px;border-left:1px solid #e5e7eb;border-right:1px solid #e5e7eb;
  background:#faf9fb}}

/* ── detail panel ── */
#kg-detail{{position:absolute;top:40px;right:0;width:260px;height:calc(100% - 40px);
  background:rgba(255,255,255,.97);border-left:2px solid #ede9fe;
  padding:14px;overflow-y:auto;transform:translateX(100%);
  transition:transform .25s ease;z-index:20;font-size:13px}}
#kg-detail.visible{{transform:translateX(0)}}
#kg-detail h3{{margin:0 0 2px;font-size:15px}}
.det-type{{font-size:11px;color:#6b7280;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid #e5e7eb}}
.det-row{{display:flex;justify-content:space-between;align-items:baseline;padding:5px 0;
  border-bottom:1px solid #f3f4f6}}
.det-label{{font-size:11px;color:#6b7280;font-weight:700;flex-shrink:0;margin-right:8px}}
.det-value{{font-size:12px;color:#1f2937;text-align:right}}
.det-badge{{font-size:10px;font-weight:800;padding:2px 8px;border-radius:6px;text-transform:uppercase}}
.det-badge.severe{{background:#fee2e2;color:#991b1b}}
.det-badge.moderate{{background:#fef3c7;color:#92400e}}
.det-badge.mild{{background:#d1fae5;color:#065f46}}
#kg-detail-close{{position:absolute;top:8px;right:10px;background:none;border:none;
  font-size:16px;cursor:pointer;color:#9ca3af;font-family:inherit}}
#kg-detail-close:hover{{color:#374151}}

/* ── hint ── */
#kg-hint{{position:absolute;bottom:8px;left:8px;z-index:15;
  background:rgba(255,255,255,.95);border:1px solid #e5e7eb;border-radius:10px;
  padding:9px 14px;font-size:11.5px;color:#6b7280;line-height:1.45;
  box-shadow:0 2px 8px rgba(0,0,0,.05);max-width:260px;transition:opacity .3s}}
#kg-hint b{{color:#374151}}
#kg-hint-close{{position:absolute;top:3px;right:7px;cursor:pointer;font-size:13px;
  color:#9ca3af;background:none;border:none;padding:0;font-family:inherit}}
#kg-hint-close:hover{{color:#374151}}

/* ── legend ── */
.legend{{display:flex;gap:14px;flex-wrap:wrap;padding:6px 8px;font-size:11.5px;
  background:#f9fafb;border:1px solid #e5e7eb;border-radius:0 0 10px 10px}}
.legend span{{display:inline-flex;align-items:center;gap:4px}}
.dot{{width:11px;height:11px;border-radius:3px;display:inline-block}}
.legend .sep{{border-left:1px solid #d1d5db;height:14px;margin:0 2px}}
.legend .dash-label{{color:#9ca3af;font-style:italic}}
</style></head><body>
<div id="kg-root">
  <div id="kg-toolbar">
    <input id="kg-search" placeholder="Search nodes..." autocomplete="off"/>
    <button class="tb-btn" id="kg-focus-btn" title="Highlight selected node and its connections">Focus</button>
    <button class="tb-btn" id="kg-reset-btn" title="Restore all nodes and zoom">Reset</button>
    <button class="tb-btn" id="kg-fit-btn" title="Auto-fit graph to window">Fit</button>
  </div>
  <div id="kg-net"></div>
  <div id="kg-detail">
    <button id="kg-detail-close">&times;</button>
    <div id="kg-detail-content"></div>
  </div>
  <div id="kg-hint">
    <button id="kg-hint-close">&times;</button>
    <b>Click a node</b> for detailed clinical info.
    <b>Drag nodes</b> to rearrange the layout and
    isolate relationships. Larger nodes indicate higher
    frequency or importance.
  </div>
</div>
<div class="legend">
  <span><span class="dot" style="background:#e0f2f1;border:1px solid #00897b"></span> Ingredient</span>
  <span><span class="dot" style="background:#fff3e0;border:1px solid #f57c00"></span> Interaction</span>
  <span><span class="dot" style="background:#e3f2fd;border:1px solid #1976d2"></span> Co-reported</span>
  <span><span class="dot" style="background:#fce4ec;border:1px solid #c62828"></span> Adverse Rxn</span>
  <span class="sep"></span>
  <span class="dash-label">Dashed = milder evidence</span>
</div>
<script>
var nodesData={nj};
var edgesData={ej};
var detailsMap={dj};
var nodes=new vis.DataSet(nodesData);
var edges=new vis.DataSet(edgesData);
var container=document.getElementById("kg-net");
var network=new vis.Network(container,{{nodes:nodes,edges:edges}},{{
  physics:{{solver:"forceAtlas2Based",
    forceAtlas2Based:{{gravitationalConstant:-38,centralGravity:0.006,
      springLength:145,springConstant:0.04,damping:0.45}},
    stabilization:{{iterations:160}}}},
  interaction:{{hover:true,tooltipDelay:120,zoomView:true,dragView:true}},
  edges:{{smooth:{{type:"cubicBezier",roundness:0.4}}}}
}});
var selectedNodeId=null;
var origN=JSON.stringify(nodesData);
var origE=JSON.stringify(edgesData);

network.once("stabilizationIterationsDone",function(){{
  network.fit({{animation:{{duration:400,easingFunction:"easeInOutQuad"}}}});
}});

/* ── Click → detail panel ── */
function esc(s){{var d=document.createElement("div");d.textContent=s;return d.innerHTML}}
function showDetail(id){{
  var d=detailsMap[id];if(!d)return;
  var h='<h3 style="color:'+esc(d.color)+'">'+esc(d.name)+'</h3>';
  h+='<div class="det-type">'+esc(d.type_label)+'</div>';
  for(var i=0;i<d.fields.length;i++){{
    var f=d.fields[i];
    h+='<div class="det-row"><span class="det-label">'+esc(f.label)+'</span>';
    if(f.badge){{h+='<span class="det-badge '+f.badge+'">'+esc(f.value)+'</span>'}}
    else{{h+='<span class="det-value">'+esc(f.value)+'</span>'}}
    h+='</div>';
  }}
  document.getElementById("kg-detail-content").innerHTML=h;
  document.getElementById("kg-detail").classList.add("visible");
}}
function hideDetail(){{document.getElementById("kg-detail").classList.remove("visible")}}
network.on("click",function(p){{
  if(p.nodes.length>0){{selectedNodeId=p.nodes[0];showDetail(selectedNodeId)}}
  else{{hideDetail()}}
}});
document.getElementById("kg-detail-close").addEventListener("click",hideDetail);

/* ── Search ── */
document.getElementById("kg-search").addEventListener("input",function(){{
  var q=this.value.toLowerCase().trim();
  if(!q){{resetView();return}}
  var keep=[0];
  nodes.forEach(function(n){{if(n.label.toLowerCase().indexOf(q)!==-1)keep.push(n.id)}});
  if(keep.length>1)fadeExcept(keep);
}});

/* ── Focus / fade ── */
function fadeExcept(keepIds){{
  var nu=[],eu=[];
  nodes.forEach(function(n){{
    if(keepIds.indexOf(n.id)===-1)
      nu.push({{id:n.id,color:{{background:"#f3f4f6",border:"#e5e7eb"}},
        font:{{color:"#d1d5db",size:10}}}});
  }});
  edges.forEach(function(e){{
    if(keepIds.indexOf(e.from)===-1||keepIds.indexOf(e.to)===-1)
      eu.push({{id:e.id,color:{{color:"#f0f0f0"}},font:{{color:"#f0f0f0"}}}});
  }});
  nodes.update(nu);edges.update(eu);
}}
document.getElementById("kg-focus-btn").addEventListener("click",function(){{
  if(selectedNodeId===null)return;
  var keep=network.getConnectedNodes(selectedNodeId);
  keep.push(selectedNodeId);keep.push(0);
  fadeExcept(keep);
  network.focus(selectedNodeId,{{scale:1.1,animation:{{duration:350}}}});
  this.classList.add("active");
}});

/* ── Reset ── */
function resetView(){{
  nodes.clear();nodes.add(JSON.parse(origN));
  edges.clear();edges.add(JSON.parse(origE));
  selectedNodeId=null;hideDetail();
  document.getElementById("kg-search").value="";
  document.getElementById("kg-focus-btn").classList.remove("active");
  network.fit({{animation:{{duration:350}}}});
}}
document.getElementById("kg-reset-btn").addEventListener("click",resetView);

/* ── Fit ── */
document.getElementById("kg-fit-btn").addEventListener("click",function(){{
  network.fit({{animation:{{duration:350,easingFunction:"easeInOutQuad"}}}});
}});

/* ── Dismiss hint ── */
document.getElementById("kg-hint-close").addEventListener("click",function(){{
  var h=document.getElementById("kg-hint");h.style.opacity="0";
  setTimeout(function(){{h.style.display="none"}},300);
}});
</script></body></html>"""


# ──────────────────────────────────────────────────────────────
#  PERSONALIZED RISK CALCULATOR
# ──────────────────────────────────────────────────────────────

_COMORBIDITY_WEIGHTS = {
    "Liver disease (hepatic impairment)": 0.9,
    "Kidney disease (renal impairment)": 0.8,
    "Heart disease / cardiovascular": 0.7,
    "Pregnancy / nursing": 0.9,
    "Blood disorders (coagulopathy)": 0.7,
    "GI disorders (ulcers, bleeding)": 0.6,
    "Diabetes": 0.4,
    "Hypertension": 0.4,
    "Asthma / respiratory": 0.4,
    "Immunocompromised": 0.5,
}


def _compute_personalized_risk(age_group, comorbidities,
                                dosage, duration, concurrent_meds,
                                reactions, interactions):
    """Compute a personalized risk score from transparent, justified factors."""
    factors = []  # list of (label, value, justification)
    score = 1.0   # baseline — every medication carries minimal inherent risk

    # ── Drug-data factors (derived from the KG) ──
    n_sev_ix = sum(1 for ix in interactions if ix.get("_severity") == "severe")
    n_mod_ix = sum(1 for ix in interactions if ix.get("_severity") == "moderate")
    n_sev_rx = sum(1 for rx in reactions if rx.get("_severity") == "severe")
    n_mod_rx = sum(1 for rx in reactions if rx.get("_severity") == "moderate")

    if n_sev_ix:
        v = round(n_sev_ix * 0.8, 1)
        names = ", ".join(ix["drug_name"] for ix in interactions
                          if ix.get("_severity") == "severe")[:80]
        factors.append((f"{n_sev_ix} severe interaction(s)", v,
                         f"FDA labels flag contraindications or serious risk with: {names}"))
        score += v
    if n_mod_ix:
        v = round(n_mod_ix * 0.3, 1)
        factors.append((f"{n_mod_ix} moderate interaction(s)", v,
                         "These interactions require monitoring or dose adjustment"))
        score += v
    if n_sev_rx:
        v = round(n_sev_rx * 0.5, 1)
        names = ", ".join(rx["reaction"] for rx in reactions
                          if rx.get("_severity") == "severe")[:80]
        factors.append((f"{n_sev_rx} high-frequency reaction(s)", v,
                         f"FAERS data shows frequent reports of: {names}"))
        score += v
    if n_mod_rx:
        v = round(n_mod_rx * 0.15, 1)
        factors.append((f"{n_mod_rx} moderate-frequency reaction(s)", v,
                         "These adverse events appear at moderate rates in FAERS"))
        score += v

    # ── Patient factors ──
    age_mult = {"Pediatric (<18)": 0.6, "Adult (18–64)": 0.0, "Elderly (65+)": 0.8}
    age_add = age_mult.get(age_group, 0.0)
    if age_add:
        just = ("Pediatric patients have immature hepatic/renal metabolism"
                if "Pediatric" in age_group else
                "Elderly patients have reduced clearance and higher sensitivity")
        factors.append((f"Age — {age_group}", age_add, just))
        score += age_add

    _COMORB_JUST = {
        "Liver disease (hepatic impairment)":
            "Most drugs are hepatically metabolized; impairment raises plasma levels and toxicity",
        "Kidney disease (renal impairment)":
            "Reduced renal clearance prolongs drug half-life and increases adverse-event risk",
        "Heart disease / cardiovascular":
            "Cardiovascular conditions can be exacerbated by vasoconstrictive or QT-prolonging agents",
        "Pregnancy / nursing":
            "Many drugs cross the placental barrier; FDA pregnancy categories must be reviewed",
        "Blood disorders (coagulopathy)":
            "Anticoagulant or antiplatelet interactions can cause life-threatening bleeding",
        "GI disorders (ulcers, bleeding)":
            "GI-irritant drugs (NSAIDs, corticosteroids) sharply increase perforation/bleeding risk",
        "Diabetes":
            "Some drugs alter glucose metabolism or interact with hypoglycemics",
        "Hypertension":
            "Risk of additive or antagonistic effects with antihypertensives",
        "Asthma / respiratory":
            "Beta-blockers and certain agents can trigger bronchospasm",
        "Immunocompromised":
            "Reduced immune surveillance may amplify infection-related adverse events",
    }
    for cond in comorbidities:
        w = _COMORBIDITY_WEIGHTS.get(cond, 0.3)
        factors.append((cond, w, _COMORB_JUST.get(cond, "Condition may alter drug safety profile")))
        score += w

    d_add = {"Low": -0.3, "Standard": 0.0, "High": 0.6}.get(dosage, 0.0)
    if d_add:
        just = ("Lower dose reduces exposure and adverse-event probability" if d_add < 0
                else "Higher dose increases systemic exposure and toxicity risk")
        factors.append((f"Dosage — {dosage}", d_add, just))
        score += d_add

    dur_add = {"Short-term (<2 wk)": 0.0, "Long-term (2–12 wk)": 0.4,
               "Chronic (>12 wk)": 0.7}.get(duration, 0.0)
    if dur_add:
        factors.append((f"Duration — {duration}", dur_add,
                         "Prolonged exposure increases cumulative organ toxicity and "
                         "the likelihood of delayed adverse reactions"))
        score += dur_add

    if concurrent_meds > 0:
        med_add = round(min(1.5, concurrent_meds * 0.35), 1)
        factors.append((f"{concurrent_meds} concurrent medication(s)", med_add,
                         "Each additional drug increases the chance of pharmacokinetic "
                         "or pharmacodynamic interactions"))
        score += med_add

    score = min(10.0, max(0.0, round(score, 1)))

    # ── Contextual warnings ──
    warnings = []
    sev_ix = [ix for ix in interactions if ix.get("_severity") == "severe"]
    sev_rx = [rx for rx in reactions if rx.get("_severity") == "severe"]

    if any("Liver" in c for c in comorbidities):
        warnings.append("Pre-existing liver disease increases hepatotoxicity risk. "
                         "Monitor liver enzymes regularly.")
    if any("Kidney" in c for c in comorbidities):
        warnings.append("Renal impairment may reduce drug clearance. "
                         "Consider dose adjustment and monitor renal function.")
    if any("Pregnancy" in c for c in comorbidities):
        warnings.append("Verify FDA pregnancy category. Many drugs are "
                         "contraindicated or require risk-benefit assessment.")
    if any("Blood" in c for c in comorbidities) and sev_ix:
        warnings.append("Coagulopathy combined with severe drug interactions "
                         "increases bleeding risk.")
    if age_group == "Elderly (65+)":
        warnings.append("Elderly patients may need dose reduction due to "
                         "altered pharmacokinetics and polypharmacy risk.")
    if concurrent_meds >= 3:
        warnings.append(f"{concurrent_meds} concurrent medications significantly "
                         "increase the probability of drug-drug interactions.")
    if sev_ix:
        names = ", ".join(ix["drug_name"] for ix in sev_ix[:3])
        warnings.append(f"Severe interaction(s) flagged with: {names}. "
                         "Review before co-prescribing.")
    if sev_rx:
        names = ", ".join(rx["reaction"] for rx in sev_rx[:3])
        warnings.append(f"High-frequency adverse reaction(s): {names}.")

    if not warnings:
        warnings.append("No elevated-risk factors detected for this profile.")

    return score, factors, warnings


def _build_risk_gauge_html(score):
    """Return an HTML/SVG semicircle gauge for the personalized risk score."""
    frac = score / 10.0
    arc_len = 251.3
    fill = round(frac * arc_len, 1)
    if score >= 7:
        color, label = "#dc2626", "HIGH RISK"
    elif score >= 4:
        color, label = "#d97706", "MODERATE"
    else:
        color, label = "#059669", "LOW RISK"
    return f"""
    <div style="text-align:center;padding:8px 0">
      <svg viewBox="0 0 200 115" width="220" height="130">
        <path d="M 20 100 A 80 80 0 0 1 180 100"
              stroke="#e5e7eb" stroke-width="16" fill="none" stroke-linecap="round"/>
        <path d="M 20 100 A 80 80 0 0 1 180 100"
              stroke="{color}" stroke-width="16" fill="none" stroke-linecap="round"
              stroke-dasharray="{fill} {arc_len}"
              style="transition:stroke-dasharray .6s ease"/>
        <text x="100" y="80" text-anchor="middle"
              font-size="28" font-weight="800" fill="{color}"
              font-family="Times New Roman,serif">{score:.1f}</text>
        <text x="100" y="98" text-anchor="middle"
              font-size="11" fill="#6b7280"
              font-family="Times New Roman,serif">{label}</text>
      </svg>
    </div>"""


def _parse_reference_dose(ingredients):
    """Extract a numeric dose + unit from the first ingredient strength for the dosage bar."""
    import re as _re
    for ing in ingredients:
        s = ing.get("strength", "")
        m = _re.match(r"([\d.]+)\s*([A-Za-z/%]+)", s)
        if m:
            return float(m.group(1)), m.group(2), ing["ingredient"]
    return None, None, None


def _build_dosage_bar_html(dose_val, dose_unit, ingredient, selected_level):
    """HTML bar showing Low / Standard / High dose ranges with the selected level highlighted."""
    if dose_val is None:
        return ""
    low = round(dose_val * 0.5, 1)
    std = round(dose_val, 1)
    high = round(dose_val * 2, 1)

    def _fmt(v):
        return f"{v:g}"

    sel_colors = {"Low": ("#059669", 0), "Standard": ("#d97706", 1), "High": ("#dc2626", 2)}
    sel_color, sel_idx = sel_colors.get(selected_level, ("#d97706", 1))

    segments = [
        (f"Low\n≤ {_fmt(low)} {dose_unit}", "#d1fae5", "#059669", 0),
        (f"Standard\n~{_fmt(std)} {dose_unit}", "#fef3c7", "#d97706", 1),
        (f"High\n≥ {_fmt(high)} {dose_unit}", "#fee2e2", "#dc2626", 2),
    ]
    bar_html = (
        f"<div style='margin:8px 0 4px;font-size:11px;color:#6b7280'>"
        f"Dosage reference for <b>{ingredient}</b> ({_fmt(std)} {dose_unit} labeled strength)</div>"
        f"<div style='display:flex;gap:3px;margin-bottom:6px'>"
    )
    for label, bg, border, idx in segments:
        active = idx == sel_idx
        weight = "800" if active else "600"
        bdr = f"3px solid {border}" if active else f"1px solid {border}40"
        opacity = "1" if active else "0.55"
        parts = label.split("\n")
        bar_html += (
            f"<div style='flex:1;text-align:center;padding:8px 4px;border-radius:8px;"
            f"background:{bg};border:{bdr};opacity:{opacity};line-height:1.35'>"
            f"<div style='font-weight:{weight};font-size:12px;color:{border}'>{parts[0]}</div>"
            f"<div style='font-size:11px;color:#374151'>{parts[1]}</div></div>"
        )
    bar_html += "</div>"
    return bar_html


def _render_risk_calculator(enriched, drug_name):
    """Render the personalized risk assessment panel."""
    st.markdown(
        "<div class='card' style='border:2px solid #ede9fe;'>"
        "<div class='card-title' style='color:#7c3aed;'>"
        f"Personalized Risk Assessment — {drug_name.title()}</div>",
        unsafe_allow_html=True,
    )

    left, right = st.columns([1, 1.2], gap="large")

    with left:
        st.markdown("##### Patient Context")
        age_group = st.selectbox(
            "Age group",
            ["Adult (18–64)", "Pediatric (<18)", "Elderly (65+)"],
            key="risk_age",
        )
        comorbidities = st.multiselect(
            "Comorbidities & conditions",
            list(_COMORBIDITY_WEIGHTS.keys()),
            key="risk_comorb",
        )
        rc1, rc2 = st.columns(2)
        with rc1:
            dosage = st.selectbox("Dosage level", ["Standard", "Low", "High"],
                                   key="risk_dosage")
        with rc2:
            duration = st.selectbox("Duration",
                                     ["Short-term (<2 wk)", "Long-term (2–12 wk)",
                                      "Chronic (>12 wk)"],
                                     key="risk_duration")

        # Dosage reference bar
        dose_val, dose_unit, dose_ing = _parse_reference_dose(enriched["ingredients"])
        dose_bar = _build_dosage_bar_html(dose_val, dose_unit, dose_ing, dosage)
        if dose_bar:
            st.markdown(dose_bar, unsafe_allow_html=True)

        concurrent_meds = st.number_input(
            "Concurrent medications", 0, 20, 0, key="risk_meds",
            help="Number of other drugs the patient is currently taking",
        )

    p_score, factors, warns = _compute_personalized_risk(
        age_group, comorbidities, dosage, duration, concurrent_meds,
        enriched["reactions"], enriched["interactions"],
    )

    with right:
        st.markdown("##### Risk Score")
        st.markdown(_build_risk_gauge_html(p_score), unsafe_allow_html=True)

        st.markdown("**Factor Breakdown**")
        for label, val, justification in factors:
            sign = "+" if val > 0 else ""
            bar_w = min(100, max(4, abs(val) / 2 * 100))
            bar_color = "#dc2626" if val > 0.5 else ("#d97706" if val > 0 else "#059669")
            st.markdown(
                f"<div style='margin:5px 0 1px'>"
                f"<div style='display:flex;align-items:center;gap:8px;font-size:12px'>"
                f"<span style='flex:1;color:#374151;font-weight:700'>{label}</span>"
                f"<span style='width:50px;text-align:right;font-weight:800;"
                f"color:{bar_color}'>{sign}{val}</span>"
                f"<div style='width:70px;height:6px;background:#f3f4f6;border-radius:3px'>"
                f"<div style='width:{bar_w}%;height:100%;background:{bar_color};"
                f"border-radius:3px'></div></div></div>"
                f"<div style='font-size:11px;color:#9ca3af;margin:1px 0 0 4px;'>"
                f"{justification}</div></div>",
                unsafe_allow_html=True,
            )

    st.markdown("---")
    st.markdown("##### Contextual Warnings")
    for w in warns:
        icon = "&#9888;" if "risk" in w.lower() or "severe" in w.lower() else "&#9432;"
        st.markdown(
            f"<div style='padding:6px 10px;margin:4px 0;background:#fefce8;"
            f"border-left:4px solid #d97706;border-radius:6px;font-size:13px'>"
            f"{icon}&nbsp; {w}</div>",
            unsafe_allow_html=True,
        )

    st.caption("This assessment uses a heuristic model for exploratory purposes — "
               "not a substitute for clinical judgment. Factor weights are illustrative, "
               "not derived from validated pharmacological models.")
    st.markdown("</div>", unsafe_allow_html=True)


def render_kg():
    st.markdown(
        "<div class='card'><div class='card-title' style='color:#7c3aed;'>"
        "Knowledge Graph — Decision Support</div>",
        unsafe_allow_html=True,
    )
    r = st.session_state.result
    if not r:
        st.info("Run a query to see Knowledge Graph data.")
    elif not r.get("kg_available", False):
        st.warning("Knowledge Graph not available. "
                   "Build it with: `python3 scripts/build_kg.py`")
    else:
        raw_ix = r.get("kg_interactions", [])
        raw_co = r.get("kg_co_reported", [])
        raw_rx = r.get("kg_reactions", [])
        raw_ing = r.get("kg_ingredients", [])

        if not (raw_ix or raw_co or raw_rx or raw_ing):
            st.info("This drug is not in the Knowledge Graph seed list. "
                    "Try a more common drug, or rebuild with a larger seed.")
        else:
            enriched = _enrich_kg_data(raw_ing, raw_ix, raw_co, raw_rx)
            ingredients = enriched["ingredients"]
            interactions = enriched["interactions"]
            co_reported = enriched["co_reported"]
            reactions = enriched["reactions"]

            # ── Summary insight panel ──
            s1, s2, s3, s4 = st.columns(4)
            mcr = enriched["most_common_rxn"]
            msi = enriched["most_severe_ix"]

            with s1:
                st.markdown(
                    "<div class='kg-summary-card'><div class='label'>Most Common Reaction</div>"
                    f"<div class='value'>{mcr['reaction'] if mcr else '—'}</div>"
                    f"<div class='sub'>{mcr.get('report_count', 0):,} reports</div></div>"
                    if mcr else
                    "<div class='kg-summary-card'><div class='label'>Most Common Reaction</div>"
                    "<div class='value'>—</div><div class='sub'>No data</div></div>",
                    unsafe_allow_html=True)
            with s2:
                st.markdown(
                    "<div class='kg-summary-card'><div class='label'>Most Severe Interaction</div>"
                    f"<div class='value'>{msi['drug_name'] if msi else '—'}</div>"
                    f"<div class='sub'>"
                    f"<span class='kg-risk-badge {msi['_severity']}'>{msi['_severity']}</span>"
                    f"</div></div>"
                    if msi else
                    "<div class='kg-summary-card'><div class='label'>Most Severe Interaction</div>"
                    "<div class='value'>—</div><div class='sub'>No data</div></div>",
                    unsafe_allow_html=True)
            with s3:
                total_rels = len(interactions) + len(co_reported) + len(reactions) + len(ingredients)
                st.markdown(
                    "<div class='kg-summary-card'><div class='label'>Total Relationships</div>"
                    f"<div class='value'>{total_rels}</div>"
                    f"<div class='sub'>{len(interactions)} interactions · "
                    f"{len(reactions)} reactions</div></div>",
                    unsafe_allow_html=True)
            with s4:
                st.markdown(
                    "<div class='kg-summary-card' style='cursor:pointer'>"
                    "<div class='label'>Personalized Assessment</div>"
                    "<div class='value' style='font-size:15px;color:#7c3aed'>Analyze My Risk</div>"
                    "<div class='sub'>Based on your patient context</div></div>",
                    unsafe_allow_html=True)
                if st.button("Open Assessment", key="kg_risk_toggle",
                             use_container_width=True, type="primary"):
                    st.session_state["show_risk_calc"] = \
                        not st.session_state.get("show_risk_calc", False)

            # ── Personalized risk calculator (shown on toggle) ──
            if st.session_state.get("show_risk_calc", False):
                drug_name_for_calc = r.get("drug_name") or "Drug"
                _render_risk_calculator(enriched, drug_name_for_calc)

            # ── Filter controls ──
            with st.expander("Filters", expanded=False):
                fc1, fc2, fc3 = st.columns([2, 1.5, 1.5])
                with fc1:
                    show_cats = st.multiselect(
                        "Show categories",
                        ["Ingredients", "Interactions", "Co-reported", "Adverse Reactions"],
                        default=["Ingredients", "Interactions", "Co-reported", "Adverse Reactions"],
                        key="kg_cats",
                    )
                with fc2:
                    sev_filter = st.multiselect(
                        "Severity",
                        ["mild", "moderate", "severe"],
                        default=["mild", "moderate", "severe"],
                        key="kg_sev",
                    )
                with fc3:
                    all_counts = (
                        [rx.get("report_count", 0) for rx in reactions]
                        + [cr.get("report_count", 0) for cr in co_reported]
                    )
                    max_count = max(all_counts) if all_counts else 0
                    freq_thresh = st.slider(
                        "Min reports", 0, max(max_count, 1), 0, key="kg_freq",
                    ) if max_count > 0 else 0

            # Apply filters
            f_ing = ingredients if "Ingredients" in show_cats else []
            f_ix = [ix for ix in interactions
                    if "Interactions" in show_cats and ix.get("_severity", "mild") in sev_filter]
            f_co = [cr for cr in co_reported
                    if "Co-reported" in show_cats and cr.get("report_count", 0) >= freq_thresh]
            f_rx = [rx for rx in reactions
                    if "Adverse Reactions" in show_cats
                    and rx.get("_severity", "mild") in sev_filter
                    and rx.get("report_count", 0) >= freq_thresh]

            # ── Interactive network visualization ──
            drug_name = r.get("drug_name") or ""
            if not drug_name:
                import re as _re
                _stop = {"what","are","the","is","of","for","a","an","in","on","to",
                         "and","or","how","does","do","can","side","effects","warnings",
                         "interactions","dosage","dose","drug","about","with","tell","me",
                         "information","safety","adverse","reactions","risk","taking","take",
                         "should","i","my","it","its","this","that"}
                _toks = _re.findall(r"[a-zA-Z0-9\-]+", query_text or "")
                _cands = [t for t in _toks if t.lower() not in _stop and len(t) > 2]
                drug_name = _cands[0] if _cands else "Drug"
            html = _build_kg_network_html(drug_name, f_ing, f_ix, f_co, f_rx)
            components.html(html, height=560, scrolling=False)

            # ── Tabbed detail sections ──
            tab_labels, tab_data = [], []
            if f_ing:
                tab_labels.append(f"Ingredients ({len(f_ing)})")
                tab_data.append(("ing", f_ing))
            if f_ix:
                tab_labels.append(f"Interactions ({len(f_ix)})")
                tab_data.append(("ix", f_ix))
            if f_co:
                tab_labels.append(f"Co-Reported ({len(f_co)})")
                tab_data.append(("co", f_co))
            if f_rx:
                tab_labels.append(f"Adverse Reactions ({len(f_rx)})")
                tab_data.append(("rx", f_rx))

            if tab_labels:
                tabs = st.tabs(tab_labels)
                for ti, (kind, items) in enumerate(tab_data):
                    with tabs[ti]:
                        if kind == "ing":
                            pills = "".join(
                                f"<span class='kg-pill ingredient'>{i['ingredient']}"
                                f"{(' · ' + i['strength']) if i.get('strength') else ''}</span>"
                                for i in items)
                            st.markdown(pills, unsafe_allow_html=True)
                        elif kind == "ix":
                            for ix in items[:10]:
                                sev = ix.get("_severity", "mild")
                                desc = ix.get("description", "")
                                s = (desc[:120] + "...") if len(desc) > 120 else desc
                                st.markdown(
                                    f"<span class='kg-pill interaction'>{ix['drug_name']}</span> "
                                    f"<span class='kg-risk-badge {sev}'>{sev}</span>"
                                    + (f"&nbsp; {s}" if s else ""),
                                    unsafe_allow_html=True)
                        elif kind == "co":
                            import pandas as pd
                            df = pd.DataFrame([
                                {"Drug": c["drug_name"], "Reports": c.get("report_count", 0)}
                                for c in items[:10]
                            ]).sort_values("Reports", ascending=True)
                            st.bar_chart(df, x="Drug", y="Reports", horizontal=True, color="#1976d2")
                        else:
                            import pandas as pd
                            df = pd.DataFrame([
                                {"Reaction": rx["reaction"], "Reports": rx.get("report_count", 0),
                                 "Severity": rx.get("_severity", "—").title()}
                                for rx in items[:10]
                            ]).sort_values("Reports", ascending=True)
                            st.bar_chart(df, x="Reaction", y="Reports", horizontal=True, color="#c62828")

    st.markdown("</div>", unsafe_allow_html=True)


def render_metrics():
    st.markdown(
        "<div class='card'><div class='card-title metrics'>Metrics & Monitoring</div>",
        unsafe_allow_html=True,
    )
    r = st.session_state.result
    if r:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Latency", f"{r['latency_ms']:.0f} ms")
        m2.metric("Evidence Ct.", len(r["evidence"]))
        m3.metric("Confidence", f"{r['confidence']:.0%}")
        m4.metric("Records Fetched", r["num_records"])

        st.markdown(f"- **Retrieval method:** {r['method']}")
        st.markdown(f"- **LLM used:** {'Gemini 2.0 Flash' if r['llm_used'] else 'Extractive fallback'}")
        st.markdown(f"- **openFDA search:** `{r['search_query'][:120]}`")
        st.markdown(f"- **Errors / Fallbacks:** None")
    else:
        st.info("Run a query to see metrics.")
    st.markdown("</div>", unsafe_allow_html=True)


def render_logs():
    st.markdown(
        "<div class='card'><div class='card-title logs'>Logs</div>",
        unsafe_allow_html=True,
    )

    # Session logs (in-memory)
    st.markdown("**Session Log**")
    if not st.session_state.logs:
        st.write("No queries run yet this session.")
    else:
        for line in reversed(st.session_state.logs[-10:]):
            st.write(line)

    # CSV log (persistent)
    st.markdown("---")
    st.markdown("**Product Metrics CSV** (`logs/product_metrics.csv`)")
    csv_rows = read_logs(last_n=10)
    if csv_rows:
        import pandas as pd
        df = pd.DataFrame(csv_rows)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.write("No CSV log entries yet.")

    st.markdown("</div>", unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────
#  BODY-REGION HEATMAP
# ──────────────────────────────────────────────────────────────

_SYMPTOM_REGION_MAP: dict[str, str] = {}

_REGION_KEYWORDS: dict[str, list[str]] = {
    "head": [
        "headache", "migraine", "dizziness", "vertigo", "syncope", "tinnitus",
        "blurred vision", "vision", "visual", "eye", "ear", "hearing",
        "somnolence", "insomnia", "confusion", "seizure", "tremor",
        "anxiety", "depression", "hallucination", "amnesia", "coma",
        "cerebral", "encephalopathy", "meningitis", "stroke",
    ],
    "chest": [
        "chest pain", "palpitation", "tachycardia", "bradycardia", "arrhythmia",
        "dyspnoea", "dyspnea", "cough", "bronchospasm", "asthma",
        "pneumonia", "pulmonary", "respiratory", "cardiac", "myocardial",
        "heart", "angina", "hypertension", "hypotension", "oedema",
        "edema", "pleural", "wheezing",
    ],
    "abdomen": [
        "nausea", "vomiting", "diarrhoea", "diarrhea", "constipation",
        "abdominal", "stomach", "gastro", "gi ", "hepat", "liver",
        "pancreat", "intestin", "colitis", "dyspepsia", "flatulence",
        "rectal", "jaundice", "biliary", "spleen", "ascites",
    ],
    "arms": [
        "arm", "hand", "wrist", "elbow", "shoulder", "upper extremity",
        "carpal", "finger", "grip",
    ],
    "legs": [
        "leg", "foot", "feet", "ankle", "knee", "hip", "lower extremity",
        "gait", "claudication", "deep vein", "dvt", "toe",
    ],
    "skin": [
        "rash", "pruritus", "urticaria", "dermatitis", "erythema",
        "skin", "alopecia", "acne", "photosensitivity", "blister",
        "stevens-johnson", "toxic epidermal", "angioedema", "injection site",
        "swelling", "bruising", "petechiae", "purpura", "cellulitis",
    ],
    "systemic": [
        "fatigue", "fever", "pyrexia", "malaise", "weight", "anaphyla",
        "death", "multi-organ", "sepsis", "infection", "anaemia", "anemia",
        "thrombocytopenia", "leukopenia", "neutropenia", "lymph",
        "blood", "coagul", "haemorrhage", "hemorrhage", "pain",
        "arthralgia", "myalgia", "back pain", "muscle",
    ],
}

for _region, _kws in _REGION_KEYWORDS.items():
    for _kw in _kws:
        _SYMPTOM_REGION_MAP[_kw] = _region


def map_symptoms_to_regions(symptoms: list[str]) -> dict[str, int]:
    """Map symptom strings to body regions and return counts per region."""
    counts: dict[str, int] = {r: 0 for r in _REGION_KEYWORDS}
    counts["unknown"] = 0
    for sym in symptoms:
        low = sym.lower().strip()
        matched = False
        for kw, region in _SYMPTOM_REGION_MAP.items():
            if kw in low:
                counts[region] += 1
                matched = True
                break
        if not matched:
            counts["unknown"] += 1
    return counts


def _build_body_heatmap_html(region_counts: dict[str, int], symptoms: list[str]) -> str:
    """Return an SVG human body silhouette with regions colored by intensity."""
    max_count = max((v for k, v in region_counts.items() if k != "unknown"), default=1) or 1

    def _intensity(region: str) -> str:
        c = region_counts.get(region, 0)
        if c == 0:
            return "fill:#e5e7eb"
        frac = c / max_count
        if frac > 0.66:
            return "fill:#dc2626;fill-opacity:0.85"
        elif frac > 0.33:
            return "fill:#f59e0b;fill-opacity:0.75"
        else:
            return "fill:#3b82f6;fill-opacity:0.55"

    def _label(region: str) -> str:
        c = region_counts.get(region, 0)
        return f"{region.title()} ({c})" if c else ""

    total = sum(region_counts.values())
    unknown = region_counts.get("unknown", 0)

    return f"""<html><head><style>
*{{box-sizing:border-box}}
body{{margin:0;padding:0;background:transparent;font-family:"Times New Roman",serif}}
.hm-wrap{{text-align:center;padding:4px}}
.hm-title{{font-size:13px;font-weight:800;color:#374151;margin-bottom:2px}}
.hm-sub{{font-size:11px;color:#9ca3af;margin-bottom:6px}}
svg text{{font-family:"Times New Roman",serif}}
.legend{{display:flex;justify-content:center;gap:12px;margin-top:6px;font-size:10px;color:#6b7280}}
.legend span{{display:inline-flex;align-items:center;gap:3px}}
.ldot{{width:10px;height:10px;border-radius:2px;display:inline-block}}
</style></head><body>
<div class="hm-wrap">
  <div class="hm-title">Symptom Body Map</div>
  <div class="hm-sub">{total} symptom(s) mapped{f' · {unknown} unclassified' if unknown else ''}</div>
  <svg viewBox="0 0 200 420" width="180" height="380">
    <!-- Head -->
    <ellipse cx="100" cy="38" rx="26" ry="30" style="{_intensity('head')}" rx="4"/>
    <!-- Neck -->
    <rect x="90" y="66" width="20" height="14" style="{_intensity('head')}" rx="3"/>
    <!-- Chest / torso upper -->
    <rect x="60" y="80" width="80" height="75" style="{_intensity('chest')}" rx="8"/>
    <!-- Abdomen / torso lower -->
    <rect x="62" y="155" width="76" height="65" style="{_intensity('abdomen')}" rx="6"/>
    <!-- Left arm -->
    <rect x="22" y="85" width="34" height="100" style="{_intensity('arms')}" rx="10"/>
    <!-- Right arm -->
    <rect x="144" y="85" width="34" height="100" style="{_intensity('arms')}" rx="10"/>
    <!-- Left hand -->
    <ellipse cx="39" cy="200" rx="14" ry="16" style="{_intensity('arms')}"/>
    <!-- Right hand -->
    <ellipse cx="161" cy="200" rx="14" ry="16" style="{_intensity('arms')}"/>
    <!-- Left leg -->
    <rect x="64" y="222" width="32" height="130" style="{_intensity('legs')}" rx="10"/>
    <!-- Right leg -->
    <rect x="104" y="222" width="32" height="130" style="{_intensity('legs')}" rx="10"/>
    <!-- Left foot -->
    <ellipse cx="80" cy="365" rx="18" ry="12" style="{_intensity('legs')}"/>
    <!-- Right foot -->
    <ellipse cx="120" cy="365" rx="18" ry="12" style="{_intensity('legs')}"/>
    <!-- Skin overlay (outline) -->
    <rect x="18" y="28" width="164" height="355" rx="20"
          style="fill:none;stroke:{('#dc2626' if region_counts.get('skin',0)/max_count>0.66
                  else '#f59e0b' if region_counts.get('skin',0)/max_count>0.33
                  else '#3b82f6') if region_counts.get('skin',0)>0 else '#e5e7eb'};
                 stroke-width:{3 if region_counts.get('skin',0)>0 else 0};
                 stroke-dasharray:6 4;opacity:{0.7 if region_counts.get('skin',0)>0 else 0}"/>
    <!-- Region labels (only shown if count > 0) -->
    {"<text x='100' y='42' text-anchor='middle' font-size='9' font-weight='700' fill='#fff'>" + _label('head') + "</text>" if region_counts.get('head',0) else ""}
    {"<text x='100' y='122' text-anchor='middle' font-size='9' font-weight='700' fill='#fff'>" + _label('chest') + "</text>" if region_counts.get('chest',0) else ""}
    {"<text x='100' y='192' text-anchor='middle' font-size='9' font-weight='700' fill='#fff'>" + _label('abdomen') + "</text>" if region_counts.get('abdomen',0) else ""}
    {"<text x='39' y='140' text-anchor='middle' font-size='8' font-weight='700' fill='#fff'>" + _label('arms') + "</text>" if region_counts.get('arms',0) else ""}
    {"<text x='80' y='300' text-anchor='middle' font-size='8' font-weight='700' fill='#fff'>" + _label('legs') + "</text>" if region_counts.get('legs',0) else ""}
  </svg>
  <div class="legend">
    <span><span class="ldot" style="background:#3b82f6"></span> Low</span>
    <span><span class="ldot" style="background:#f59e0b"></span> Med</span>
    <span><span class="ldot" style="background:#dc2626"></span> High</span>
    {"<span>| Dashed outline = Skin (" + str(region_counts.get('skin',0)) + ")</span>" if region_counts.get('skin',0) else ""}
  </div>
</div>
</body></html>"""


def _extract_symptoms_from_result(r: dict) -> list[str]:
    """Pull symptom strings from KG reactions + evidence field names."""
    symptoms = []
    for rx in r.get("kg_reactions", []):
        name = rx.get("reaction", "")
        if name:
            symptoms.append(name)
    return symptoms


def render_body_heatmap():
    """Render the body-region heatmap card."""
    r = st.session_state.result
    if not r:
        return
    symptoms = _extract_symptoms_from_result(r)
    if not symptoms:
        return
    region_counts = map_symptoms_to_regions(symptoms)
    if sum(v for k, v in region_counts.items() if k != "unknown") == 0:
        return

    st.markdown(
        "<div class='card'><div class='card-title' style='color:#7c3aed;'>"
        "Adverse-Event Body Map</div>",
        unsafe_allow_html=True,
    )
    html = _build_body_heatmap_html(region_counts, symptoms)
    components.html(html, height=440, scrolling=False)

    # Systemic callout
    sys_count = region_counts.get("systemic", 0)
    if sys_count:
        st.markdown(
            f"<div style='text-align:center;font-size:12px;color:#6b7280;margin-top:-8px'>"
            f"<b>Systemic</b> (whole-body): {sys_count} symptom(s)</div>",
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)


def render_overall():
    left, right = st.columns([2.2, 1.2], gap="large")
    with left:
        render_response()
        render_kg()
    with right:
        render_body_heatmap()
        render_evidence()
        render_metrics()
    render_logs()


# ══════════════════════════════════════════════════════════════
#  CONDITIONAL VIEWS
# ══════════════════════════════════════════════════════════════
active = st.session_state.active_panel

if active == "ALL":
    render_overall()
elif active == "Response":
    _resp_l, _resp_r = st.columns([2, 1], gap="large")
    with _resp_l:
        render_response()
    with _resp_r:
        render_body_heatmap()
elif active == "KG":
    render_kg()
elif active == "Evidence":
    render_evidence()
elif active == "Metrics":
    render_metrics()
elif active == "Logs":
    render_logs()
