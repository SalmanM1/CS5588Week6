"""
TruPharma GenAI Assistant  ·  Agent Chat
=========================================
Streamlit page: interactive AI agent with tool-based reasoning
for multi-step drug-safety workflows.
"""

import sys
import json
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st
import streamlit.components.v1 as components

from agent.agent_runner import AgentRunner

# ─── Page config ──────────────────────────────────────────────
st.set_page_config(
    page_title="Agent Chat | TruPharma",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Force-expand sidebar ────────────────────────────────────
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

# ─── Page styling ─────────────────────────────────────────────
st.markdown("""<style>
.agent-header {
    background: linear-gradient(90deg, #7c3aed, #4f46e5);
    color: white; padding: 12px 16px; border-radius: 10px;
    font-weight: 600; margin-bottom: 14px;
}
.msg-user {
    background: #f0f9ff; border-left: 4px solid #3b82f6;
    border-radius: 10px; padding: 12px 16px; margin: 8px 0;
}
.msg-agent {
    background: #faf5ff; border-left: 4px solid #7c3aed;
    border-radius: 10px; padding: 12px 16px; margin: 8px 0;
}
.tool-badge {
    display: inline-block; padding: 3px 10px; border-radius: 20px;
    font-size: 11px; font-weight: 700; margin: 2px 3px;
    background: #ede9fe; color: #5b21b6; border: 1px solid #c4b5fd;
}
.reasoning-box {
    background: #fffbeb; border: 1px solid #fbbf24; border-radius: 8px;
    padding: 10px 14px; font-size: 13px; color: #92400e; margin: 6px 0;
}
.metrics-bar {
    display: flex; gap: 16px; padding: 6px 0; font-size: 12px; color: #6b7280;
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
#  SESSION STATE
# ══════════════════════════════════════════════════════════════
if "agent_messages" not in st.session_state:
    st.session_state.agent_messages = []
if "agent_runner" not in st.session_state:
    st.session_state.agent_runner = None


def _get_agent() -> AgentRunner:
    """Get or create the agent runner, respecting current API key."""
    key = st.session_state.get("agent_gemini_key", "")
    if st.session_state.agent_runner is None or st.session_state.agent_runner.gemini_key != key:
        st.session_state.agent_runner = AgentRunner(gemini_key=key)
        if st.session_state.agent_messages:
            for msg in st.session_state.agent_messages:
                st.session_state.agent_runner.history.append(msg)
    return st.session_state.agent_runner


# ══════════════════════════════════════════════════════════════
#  SIDEBAR
# ══════════════════════════════════════════════════════════════
if st.sidebar.button("⬅ Return to Home", key="agent_go_home"):
    st.switch_page("app.py")

st.sidebar.title("Agent Settings")
st.sidebar.markdown(
    "<div style='padding:10px 12px;border-radius:10px;background:#ede9fe;"
    "border-left:6px solid #7c3aed;font-weight:700;margin-bottom:12px;'>"
    "🤖 Agent Chat<br><small style='font-weight:400;color:#6b7280;'>"
    "AI-powered multi-step reasoning</small></div>",
    unsafe_allow_html=True,
)

gemini_key = st.sidebar.text_input(
    "Gemini API Key (optional)",
    type="password",
    key="agent_gemini_key",
    help="Enables LLM-based planning and synthesis. Without it, the agent "
         "uses rule-based intent detection and structured output.",
)

st.sidebar.markdown("---")
st.sidebar.subheader("Example Queries")
EXAMPLES = [
    "-- Select an example --",
    "What are the drug interactions for ibuprofen?",
    "Tell me everything about metformin",
    "What are the most common side effects of atorvastatin?",
    "What is the recommended dosage for acetaminophen?",
    "Assess the risk of aspirin for an elderly patient with liver disease",
    "Compare the adverse reactions of ibuprofen and naproxen",
    "What happens if I take too much gabapentin?",
    "What drugs interact with warfarin and what are the warnings?",
]
example = st.sidebar.selectbox("Try a sample:", EXAMPLES, index=0, key="agent_example")

st.sidebar.markdown("---")
st.sidebar.subheader("Available Tools")
st.sidebar.markdown("""
- **Drug Label RAG** — FDA label evidence retrieval
- **Interaction Lookup** — KG-based drug interactions
- **Adverse Event Analysis** — FAERS safety data
- **Drug Profile** — Comprehensive multi-source profile
- **Risk Assessment** — Personalized patient risk scoring
""")

st.sidebar.markdown("---")
if st.sidebar.button("🗑 Clear Chat", key="agent_clear"):
    st.session_state.agent_messages = []
    st.session_state.agent_runner = None
    st.rerun()

if st.sidebar.button("🟢 Go to Safety Chat", key="agent_to_safety"):
    st.switch_page("pages/primary_demo.py")


# ══════════════════════════════════════════════════════════════
#  MAIN HEADER
# ══════════════════════════════════════════════════════════════
st.markdown("## TruPharma AI Agent")
st.markdown(
    "<div class='agent-header'>Agent Chat — Multi-Step Drug Safety Reasoning</div>",
    unsafe_allow_html=True,
)

# ══════════════════════════════════════════════════════════════
#  CHAT HISTORY DISPLAY
# ══════════════════════════════════════════════════════════════
for msg in st.session_state.agent_messages:
    if msg["role"] == "user":
        st.markdown(
            f"<div class='msg-user'><b>You:</b> {msg['content']}</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"<div class='msg-agent'><b>Agent:</b></div>",
            unsafe_allow_html=True,
        )
        meta = msg.get("meta", {})

        if meta.get("reasoning"):
            st.markdown(
                f"<div class='reasoning-box'>💭 <b>Reasoning:</b> {meta['reasoning']}</div>",
                unsafe_allow_html=True,
            )

        tools_used = meta.get("tool_calls", [])
        if tools_used:
            badges = " ".join(
                f"<span class='tool-badge'>{tc.get('tool', '?')}</span>"
                for tc in tools_used
            )
            st.markdown(f"**Tools used:** {badges}", unsafe_allow_html=True)

        st.markdown(msg["content"])

        latency = meta.get("latency_ms", 0)
        mode = meta.get("mode", "")
        if latency or mode:
            st.markdown(
                f"<div class='metrics-bar'>"
                f"<span>⏱ {latency:.0f}ms</span>"
                f"<span>Mode: {mode}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

        tool_results = meta.get("tool_results", [])
        if tool_results:
            with st.expander("View Tool Results", expanded=False):
                for i, tr in enumerate(tool_results):
                    tool_name = tr.get("tool", "unknown")
                    st.markdown(f"**{i+1}. {tool_name}**")
                    display = {k: v for k, v in tr.items()
                               if k not in ("tool",) and v}
                    for k, v in display.items():
                        if isinstance(v, list) and len(v) > 5:
                            st.markdown(f"  - **{k}:** {len(v)} items")
                        elif isinstance(v, dict):
                            st.json(v)
                        else:
                            st.markdown(f"  - **{k}:** {v}")
                    st.markdown("---")


# ══════════════════════════════════════════════════════════════
#  CHAT INPUT
# ══════════════════════════════════════════════════════════════
if example and example != EXAMPLES[0]:
    prefill = example
else:
    prefill = ""

user_input = st.chat_input(
    "Ask a drug-safety question...",
    key="agent_chat_input",
)

if user_input:
    st.session_state.agent_messages.append({
        "role": "user",
        "content": user_input,
    })

    agent = _get_agent()

    with st.spinner("Agent is reasoning and executing tools..."):
        result = agent.run(user_input)

    st.session_state.agent_messages.append({
        "role": "assistant",
        "content": result["answer"],
        "meta": {
            "reasoning": result.get("reasoning", ""),
            "tool_calls": result.get("tool_calls", []),
            "tool_results": result.get("tool_results", []),
            "latency_ms": result.get("latency_ms", 0),
            "mode": result.get("mode", ""),
        },
    })

    st.rerun()


# ══════════════════════════════════════════════════════════════
#  EMPTY STATE
# ══════════════════════════════════════════════════════════════
if not st.session_state.agent_messages:
    st.markdown("---")
    st.markdown(
        "<div style='text-align:center;padding:40px 20px;color:#9ca3af;'>"
        "<div style='font-size:48px;margin-bottom:12px;'>🤖</div>"
        "<div style='font-size:18px;font-weight:700;color:#374151;margin-bottom:8px;'>"
        "Welcome to TruPharma Agent</div>"
        "<div style='font-size:14px;max-width:500px;margin:0 auto;'>"
        "Ask any drug-safety question. The agent will automatically select "
        "the right tools, execute multi-step workflows, and provide "
        "evidence-grounded answers.<br><br>"
        "Try selecting an example from the sidebar, or type your own question below."
        "</div></div>",
        unsafe_allow_html=True,
    )

    st.markdown("---")
    st.markdown("### How It Works")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(
            "<div style='text-align:center;padding:16px;background:#f0f9ff;"
            "border-radius:12px;border:1px solid #bfdbfe;'>"
            "<div style='font-size:28px;margin-bottom:6px;'>1️⃣</div>"
            "<b>Interpret</b><br>"
            "<span style='font-size:13px;color:#6b7280;'>"
            "The agent analyzes your question to understand intent and extract "
            "drug names, patient context, and query type.</span></div>",
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            "<div style='text-align:center;padding:16px;background:#faf5ff;"
            "border-radius:12px;border:1px solid #ddd6fe;'>"
            "<div style='font-size:28px;margin-bottom:6px;'>2️⃣</div>"
            "<b>Execute</b><br>"
            "<span style='font-size:13px;color:#6b7280;'>"
            "Selected tools run against live FDA data, the Knowledge Graph, "
            "and FAERS adverse-event records.</span></div>",
            unsafe_allow_html=True,
        )
    with col3:
        st.markdown(
            "<div style='text-align:center;padding:16px;background:#f0fdf4;"
            "border-radius:12px;border:1px solid #bbf7d0;'>"
            "<div style='font-size:28px;margin-bottom:6px;'>3️⃣</div>"
            "<b>Synthesize</b><br>"
            "<span style='font-size:13px;color:#6b7280;'>"
            "Results are combined into a clear, evidence-grounded answer "
            "with citations, metrics, and safety warnings.</span></div>",
            unsafe_allow_html=True,
        )
