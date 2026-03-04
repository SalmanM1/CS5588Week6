"""
agent_runner.py · TruPharma AI Agent Runner
=============================================
Core reasoning engine that:
  1. Interprets user requests (intent classification)
  2. Selects appropriate tool(s) from the registry
  3. Executes single or multi-step workflows
  4. Synthesizes results into evidence-grounded explanations

Supports two modes:
  - **LLM mode** (Gemini): Full natural-language reasoning with tool-call planning
  - **Rule-based mode** (fallback): Keyword-based intent detection and tool routing
"""

import json
import re
import sys
import time
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agent.tools import TOOL_REGISTRY, execute_tool
from agent.tool_schemas import TOOL_SCHEMAS, format_tools_for_prompt


# ══════════════════════════════════════════════════════════════
#  SYSTEM PROMPT
# ══════════════════════════════════════════════════════════════

_SYSTEM_PROMPT = """\
You are TruPharma Agent, an AI clinical decision-support assistant specializing in drug safety.

You have access to the following tools:

{tools}

## Instructions

1. Analyze the user's question to determine which tool(s) are needed.
2. Return a JSON object with your reasoning and tool calls.
3. For multi-drug or comparative questions, call tools multiple times as needed.
4. Always ground your answers in tool outputs — never fabricate data.
5. If the question is out of scope (not drug-related), say so clearly.

## Response Format

Return ONLY a JSON object with this structure (no markdown fences):
{{
  "reasoning": "Brief explanation of your approach",
  "tool_calls": [
    {{
      "tool": "tool_name",
      "arguments": {{ "param": "value" }}
    }}
  ]
}}

If no tools are needed (e.g., greeting or out-of-scope), return:
{{
  "reasoning": "Explanation",
  "tool_calls": [],
  "direct_response": "Your response text"
}}
"""

_SYNTHESIS_PROMPT = """\
You are TruPharma Agent. Based on the tool results below, provide a clear, concise answer to the user's question.

**User Question:** {question}

**Tool Results:**
{results}

## Instructions
- Synthesize the results into a coherent answer (3-8 sentences).
- Cite specific data points (e.g., report counts, severity levels, confidence scores).
- If results indicate insufficient evidence, say so clearly.
- Include relevant warnings or safety considerations.
- Do NOT fabricate information beyond what the tools returned.
"""


# ══════════════════════════════════════════════════════════════
#  RULE-BASED INTENT DETECTION (Fallback)
# ══════════════════════════════════════════════════════════════

_INTERACTION_KEYWORDS = {
    "interaction", "interactions", "interact", "contraindicated",
    "contraindication", "taken together", "combine", "combined",
    "co-prescribe", "coprescribe", "taken with",
}

_ADVERSE_EVENT_KEYWORDS = {
    "side effect", "side effects", "adverse", "reaction", "reactions",
    "safety signal", "faers", "reported", "reports",
}

_RISK_KEYWORDS = {
    "risk", "personalized", "patient", "elderly", "pediatric",
    "comorbidity", "comorbidities", "liver disease", "kidney",
    "concurrent", "assess",
}

_PROFILE_KEYWORDS = {
    "profile", "everything", "comprehensive", "all about",
    "overview", "summary", "tell me about", "full information",
}

_DRUG_NAME_STOP = frozenset(
    "what are the is of for a an in on to and or how does do can "
    "side effects warnings interactions dosage dose drug about with "
    "tell me information safety adverse reactions risk taking take "
    "should i my it this that please help".split()
)


def _extract_drug_names(query: str) -> List[str]:
    """Extract potential drug names from a query using simple heuristics."""
    tokens = re.findall(r"[a-zA-Z0-9\-]+", query)
    candidates = [t for t in tokens if t.lower() not in _DRUG_NAME_STOP and len(t) > 2]
    return candidates[:3]


def _detect_intent(query: str) -> List[Dict[str, Any]]:
    """
    Rule-based intent detection: analyze the query and return a list
    of tool calls to execute.
    """
    q_lower = query.lower()
    tool_calls = []
    drug_names = _extract_drug_names(query)
    primary_drug = drug_names[0] if drug_names else query.strip()

    has_interaction = any(kw in q_lower for kw in _INTERACTION_KEYWORDS)
    has_adverse = any(kw in q_lower for kw in _ADVERSE_EVENT_KEYWORDS)
    has_risk = any(kw in q_lower for kw in _RISK_KEYWORDS)
    has_profile = any(kw in q_lower for kw in _PROFILE_KEYWORDS)

    if has_profile:
        tool_calls.append({
            "tool": "get_drug_profile",
            "arguments": {"query": query},
        })
    elif has_interaction and has_adverse:
        tool_calls.append({
            "tool": "lookup_drug_interactions",
            "arguments": {"drug_name": primary_drug},
        })
        tool_calls.append({
            "tool": "analyze_adverse_events",
            "arguments": {"drug_name": primary_drug},
        })
    elif has_interaction:
        tool_calls.append({
            "tool": "lookup_drug_interactions",
            "arguments": {"drug_name": primary_drug},
        })
        if len(drug_names) > 1:
            for dn in drug_names[1:]:
                tool_calls.append({
                    "tool": "lookup_drug_interactions",
                    "arguments": {"drug_name": dn},
                })
    elif has_adverse:
        tool_calls.append({
            "tool": "analyze_adverse_events",
            "arguments": {"drug_name": primary_drug},
        })
    elif has_risk:
        tool_calls.append({
            "tool": "assess_patient_risk",
            "arguments": {"drug_name": primary_drug},
        })
    else:
        tool_calls.append({
            "tool": "query_drug_label",
            "arguments": {"query": query},
        })

    return tool_calls


# ══════════════════════════════════════════════════════════════
#  LLM-BASED PLANNING (Gemini)
# ══════════════════════════════════════════════════════════════

def _plan_with_gemini(query: str, api_key: str, history: List[Dict] = None) -> Dict[str, Any]:
    """Use Gemini to plan which tools to call."""
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)

        tools_text = format_tools_for_prompt()
        system = _SYSTEM_PROMPT.format(tools=tools_text)

        messages = []
        if history:
            for msg in history[-6:]:
                role = "user" if msg["role"] == "user" else "model"
                messages.append({"role": role, "parts": [msg["content"]]})
        messages.append({"role": "user", "parts": [query]})

        model = genai.GenerativeModel(
            "gemini-2.0-flash",
            system_instruction=system,
        )
        resp = model.generate_content(messages)

        if resp and resp.text:
            text = resp.text.strip()
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
            return json.loads(text)
    except json.JSONDecodeError:
        pass
    except Exception as exc:
        warnings.warn(f"Gemini planning error: {exc}")

    return None


def _synthesize_with_gemini(
    question: str,
    tool_results: List[Dict],
    api_key: str,
) -> str:
    """Use Gemini to synthesize tool results into a final answer."""
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)

        results_text = json.dumps(tool_results, indent=2, default=str)[:8000]
        prompt = _SYNTHESIS_PROMPT.format(question=question, results=results_text)

        model = genai.GenerativeModel("gemini-2.0-flash")
        resp = model.generate_content(prompt)
        if resp and resp.text:
            return resp.text.strip()
    except Exception as exc:
        warnings.warn(f"Gemini synthesis error: {exc}")
    return None


# ══════════════════════════════════════════════════════════════
#  RULE-BASED SYNTHESIS (Fallback)
# ══════════════════════════════════════════════════════════════

def _synthesize_rule_based(question: str, tool_results: List[Dict]) -> str:
    """Create a structured summary from tool results without an LLM."""
    if not tool_results:
        return "I wasn't able to find relevant information for your question."

    parts = []
    for result in tool_results:
        tool_name = result.get("tool", "unknown")

        if result.get("error"):
            parts.append(f"**{tool_name}:** Error — {result['error']}")
            continue

        if tool_name == "query_drug_label":
            answer = result.get("answer", "")
            conf = result.get("confidence", 0)
            n_ev = result.get("num_evidence", 0)
            parts.append(f"**Drug Label Evidence** (confidence: {conf:.0%}, {n_ev} evidence chunks):")
            parts.append(answer)

        elif tool_name == "lookup_drug_interactions":
            drug = result.get("resolved_name", result.get("drug_name", ""))
            ixs = result.get("interactions", [])
            parts.append(f"**Drug Interactions for {drug}** ({len(ixs)} found):")
            for ix in ixs[:8]:
                sev = ix.get("severity", "unknown")
                desc = ix.get("description", "")
                desc_preview = (f" — {desc[:120]}..." if len(desc) > 120 else f" — {desc}") if desc else ""
                parts.append(f"  - **{ix['drug_name']}** [{sev}]{desc_preview}")

        elif tool_name == "analyze_adverse_events":
            drug = result.get("resolved_name", result.get("drug_name", ""))
            rxs = result.get("top_reactions", [])
            parts.append(f"**Adverse Events for {drug}** ({result.get('reaction_count', 0)} total):")
            for rx in rxs[:8]:
                parts.append(
                    f"  - {rx['reaction']} — {rx['report_count']:,} reports "
                    f"({rx['relative_frequency']}) [{rx['severity']}]"
                )
            co = result.get("co_reported_drugs", [])
            if co:
                co_str = ", ".join(c["drug_name"] for c in co[:5])
                parts.append(f"  Co-reported drugs: {co_str}")

        elif tool_name == "get_drug_profile":
            identity = result.get("drug_identity", {})
            name = identity.get("resolved_name", "")
            brands = identity.get("brand_names", [])
            parts.append(f"**Drug Profile: {name}**")
            if brands:
                parts.append(f"  Brand names: {', '.join(brands[:5])}")
            parts.append(f"  Label fields: {', '.join(result.get('label_fields', []))}")
            faers = result.get("faers_summary", {})
            parts.append(f"  FAERS total reports: {faers.get('total_reports', 0):,}")
            disp = result.get("disparity_score", 0)
            if disp:
                parts.append(f"  Label-vs-FAERS disparity score: {disp:.2f}")

        elif tool_name == "assess_patient_risk":
            drug = result.get("drug_name", "")
            score = result.get("risk_score", 0)
            level = result.get("risk_level", "")
            parts.append(f"**Risk Assessment for {drug}:** {score}/10 ({level})")
            for f in result.get("factors", []):
                sign = "+" if f["value"] > 0 else ""
                parts.append(f"  - {f['factor']}: {sign}{f['value']}")
            for w in result.get("warnings", []):
                parts.append(f"  ⚠ {w}")

    return "\n\n".join(parts)


# ══════════════════════════════════════════════════════════════
#  MAIN AGENT RUNNER
# ══════════════════════════════════════════════════════════════

class AgentRunner:
    """
    TruPharma AI Agent: interprets user requests, selects tools,
    executes workflows, and returns evidence-grounded explanations.
    """

    def __init__(self, gemini_key: str = ""):
        self.gemini_key = gemini_key
        self.history: List[Dict[str, str]] = []

    def run(self, user_query: str) -> Dict[str, Any]:
        """
        Process a user query end-to-end:
          1. Plan (select tools)
          2. Execute (run tools)
          3. Synthesize (generate answer)

        Returns a dict with: answer, reasoning, tool_calls, tool_results,
        latency_ms, and mode (llm or rule_based).
        """
        t0 = time.time()
        self.history.append({"role": "user", "content": user_query})

        # ── Step 1: Plan ──
        plan = None
        mode = "rule_based"

        if self.gemini_key:
            plan = _plan_with_gemini(user_query, self.gemini_key, self.history)
            if plan:
                mode = "llm"

        if plan and plan.get("direct_response"):
            answer = plan["direct_response"]
            result = {
                "answer": answer,
                "reasoning": plan.get("reasoning", ""),
                "tool_calls": [],
                "tool_results": [],
                "latency_ms": round((time.time() - t0) * 1000, 1),
                "mode": mode,
            }
            self.history.append({"role": "assistant", "content": answer})
            return result

        if plan and plan.get("tool_calls"):
            tool_calls = plan["tool_calls"]
            reasoning = plan.get("reasoning", "")
        else:
            tool_calls = _detect_intent(user_query)
            reasoning = f"Rule-based routing: detected intent and selected {len(tool_calls)} tool(s)"

        # ── Step 2: Execute ──
        tool_results = []
        for tc in tool_calls:
            tool_name = tc.get("tool", "")
            args = tc.get("arguments", {})
            if self.gemini_key and tool_name == "query_drug_label":
                args["gemini_key"] = self.gemini_key
            result = execute_tool(tool_name, **args)
            tool_results.append(result)

        # ── Step 3: Synthesize ──
        answer = None
        if self.gemini_key:
            answer = _synthesize_with_gemini(user_query, tool_results, self.gemini_key)

        if not answer:
            answer = _synthesize_rule_based(user_query, tool_results)

        self.history.append({"role": "assistant", "content": answer})

        return {
            "answer": answer,
            "reasoning": reasoning,
            "tool_calls": tool_calls,
            "tool_results": tool_results,
            "latency_ms": round((time.time() - t0) * 1000, 1),
            "mode": mode,
        }

    def reset(self):
        """Clear conversation history."""
        self.history.clear()


# ══════════════════════════════════════════════════════════════
#  CLI Interface
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import os

    api_key = os.environ.get("GEMINI_API_KEY", "")
    agent = AgentRunner(gemini_key=api_key)

    print("TruPharma Agent CLI")
    print("=" * 50)
    print("Type your drug-safety question (or 'quit' to exit):\n")

    while True:
        try:
            query = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not query or query.lower() in ("quit", "exit", "q"):
            break

        result = agent.run(query)
        print(f"\n[Mode: {result['mode']} | Latency: {result['latency_ms']}ms]")
        print(f"[Reasoning: {result['reasoning']}]")
        print(f"[Tools called: {[tc.get('tool') for tc in result['tool_calls']]}]")
        print(f"\nAgent: {result['answer']}\n")
