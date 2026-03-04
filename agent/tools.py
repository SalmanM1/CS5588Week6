"""
tools.py · TruPharma Agent Tool Implementations
=================================================
Each function wraps an existing project component into a callable tool
with a standardized signature: takes keyword args, returns a dict.

Tools:
  1. query_drug_label     — RAG pipeline over openFDA drug labels
  2. lookup_drug_interactions — KG-based drug interaction lookup
  3. analyze_adverse_events   — FAERS adverse-event analysis via KG
  4. get_drug_profile     — Unified multi-source drug profile
  5. assess_patient_risk  — Personalized risk scoring
"""

import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.rag.engine import run_rag_query, read_logs
from src.rag.drug_profile import _extract_drug_name, build_unified_profile
from src.kg.loader import load_kg


# ══════════════════════════════════════════════════════════════
#  Tool 1: Drug Label RAG Query
# ══════════════════════════════════════════════════════════════

def query_drug_label(
    query: str,
    method: str = "hybrid",
    top_k: int = 5,
    gemini_key: str = "",
) -> Dict[str, Any]:
    """
    Run the full RAG pipeline: fetch FDA drug labels, index, retrieve,
    and generate a grounded answer with evidence citations.
    """
    t0 = time.time()
    result = run_rag_query(
        query,
        gemini_key=gemini_key,
        method=method,
        top_k=top_k,
        use_rerank=False,
    )
    elapsed = round((time.time() - t0) * 1000, 1)

    evidence_summary = []
    for ev in result.get("evidence", []):
        evidence_summary.append({
            "citation": ev.get("cite", ""),
            "field": ev.get("field", ""),
            "content_preview": (ev.get("content", ""))[:300],
        })

    return {
        "tool": "query_drug_label",
        "answer": result.get("answer", ""),
        "confidence": result.get("confidence", 0.0),
        "evidence": evidence_summary,
        "num_evidence": len(evidence_summary),
        "num_records": result.get("num_records", 0),
        "latency_ms": elapsed,
        "method": result.get("method", method),
        "llm_used": result.get("llm_used", False),
        "drug_name": result.get("drug_name", ""),
        "search_query": result.get("search_query", ""),
    }


# ══════════════════════════════════════════════════════════════
#  Tool 2: Drug Interaction Lookup
# ══════════════════════════════════════════════════════════════

def lookup_drug_interactions(drug_name: str) -> Dict[str, Any]:
    """
    Query the Knowledge Graph for known drug-drug interactions.
    Returns interaction partners with severity and descriptions.
    """
    t0 = time.time()
    kg = load_kg()

    if not kg:
        return {
            "tool": "lookup_drug_interactions",
            "drug_name": drug_name,
            "interactions": [],
            "error": "Knowledge Graph not available",
            "latency_ms": round((time.time() - t0) * 1000, 1),
        }

    identity = kg.get_drug_identity(drug_name)
    interactions = kg.get_interactions(drug_name)

    enriched = []
    for ix in interactions:
        desc = (ix.get("description") or "").lower()
        if any(w in desc for w in ("contraindicated", "severe", "fatal", "death", "serious")):
            severity = "severe"
        elif any(w in desc for w in ("caution", "monitor", "moderate", "avoid", "careful")):
            severity = "moderate"
        else:
            severity = "mild"
        enriched.append({
            "drug_name": ix.get("drug_name", ""),
            "severity": severity,
            "description": ix.get("description", ""),
            "source": ix.get("source", "unknown"),
        })

    return {
        "tool": "lookup_drug_interactions",
        "drug_name": drug_name,
        "resolved_name": (identity or {}).get("generic_name", drug_name),
        "interaction_count": len(enriched),
        "interactions": enriched,
        "latency_ms": round((time.time() - t0) * 1000, 1),
    }


# ══════════════════════════════════════════════════════════════
#  Tool 3: Adverse Event Analysis
# ══════════════════════════════════════════════════════════════

def analyze_adverse_events(drug_name: str) -> Dict[str, Any]:
    """
    Analyze adverse events (side effects) from the Knowledge Graph
    using FAERS data. Returns reactions, co-reported drugs, and severity.
    """
    t0 = time.time()
    kg = load_kg()

    if not kg:
        return {
            "tool": "analyze_adverse_events",
            "drug_name": drug_name,
            "reactions": [],
            "error": "Knowledge Graph not available",
            "latency_ms": round((time.time() - t0) * 1000, 1),
        }

    identity = kg.get_drug_identity(drug_name)
    reactions = kg.get_drug_reactions(drug_name)
    co_reported = kg.get_co_reported(drug_name)
    ingredients = kg.get_ingredients(drug_name)

    max_count = max((r.get("report_count", 0) for r in reactions), default=1) or 1
    enriched_reactions = []
    for rx in reactions[:15]:
        cnt = rx.get("report_count", 0)
        pct = cnt / max_count
        severity = "severe" if pct > 0.66 else ("moderate" if pct > 0.33 else "mild")
        enriched_reactions.append({
            "reaction": rx.get("reaction", ""),
            "report_count": cnt,
            "relative_frequency": f"{pct * 100:.1f}%",
            "severity": severity,
        })

    co_reported_summary = [
        {"drug_name": cr.get("drug_name", ""), "report_count": cr.get("report_count", 0)}
        for cr in co_reported[:10]
    ]

    return {
        "tool": "analyze_adverse_events",
        "drug_name": drug_name,
        "resolved_name": (identity or {}).get("generic_name", drug_name),
        "reaction_count": len(reactions),
        "top_reactions": enriched_reactions,
        "co_reported_drugs": co_reported_summary,
        "ingredients": [ing.get("ingredient", "") for ing in ingredients],
        "latency_ms": round((time.time() - t0) * 1000, 1),
    }


# ══════════════════════════════════════════════════════════════
#  Tool 4: Comprehensive Drug Profile
# ══════════════════════════════════════════════════════════════

def get_drug_profile(query: str) -> Dict[str, Any]:
    """
    Build a comprehensive drug profile from all available sources:
    FDA labels, FAERS, NDC metadata, and the Knowledge Graph.
    """
    t0 = time.time()

    try:
        profile = build_unified_profile(query)
    except Exception as exc:
        return {
            "tool": "get_drug_profile",
            "query": query,
            "error": f"Failed to build profile: {exc}",
            "latency_ms": round((time.time() - t0) * 1000, 1),
        }

    identity = profile.get("drug_identity", {})
    label_data = profile.get("label_data", {})
    faers = profile.get("faers_summary", {})
    ndc = profile.get("ndc_metadata", {})
    disparity = profile.get("disparity_analysis", {})

    label_summary = {field: text[:300] for field, text in label_data.items()}

    faers_summary = {
        "total_reports": faers.get("total_reports", 0),
        "top_reactions": [
            {"term": r.get("term", ""), "count": r.get("count", 0)}
            for r in faers.get("top_reactions", [])[:10]
        ],
        "seriousness": faers.get("seriousness", {}),
    }

    return {
        "tool": "get_drug_profile",
        "drug_identity": identity,
        "label_fields": list(label_data.keys()),
        "label_summary": label_summary,
        "faers_summary": faers_summary,
        "ndc_brand_names": ndc.get("brand_names", []),
        "disparity_score": disparity.get("disparity_score", 0.0),
        "emerging_signals": [
            r.get("term", "") for r in disparity.get("reactions_in_faers_not_on_label", [])[:5]
        ],
        "kg_interactions": [
            ix.get("drug_name", "") for ix in profile.get("kg_interactions", [])[:5]
        ],
        "kg_reactions": [
            rx.get("reaction", "") for rx in profile.get("kg_reactions", [])[:5]
        ],
        "text_section_count": len(profile.get("text_sections", [])),
        "latency_ms": round((time.time() - t0) * 1000, 1),
    }


# ══════════════════════════════════════════════════════════════
#  Tool 5: Personalized Risk Assessment
# ══════════════════════════════════════════════════════════════

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


def assess_patient_risk(
    drug_name: str,
    age_group: str = "Adult (18-64)",
    comorbidities: Optional[List[str]] = None,
    dosage_level: str = "Standard",
    duration: str = "Short-term (<2 wk)",
    concurrent_medications: int = 0,
) -> Dict[str, Any]:
    """
    Compute a personalized risk score (0-10) combining drug data from
    the Knowledge Graph with patient-specific factors.
    """
    t0 = time.time()
    comorbidities = comorbidities or []
    kg = load_kg()

    interactions = []
    reactions = []
    resolved_name = drug_name

    if kg:
        identity = kg.get_drug_identity(drug_name)
        if identity:
            resolved_name = identity.get("generic_name", drug_name)
        interactions_raw = kg.get_interactions(drug_name)
        reactions_raw = kg.get_drug_reactions(drug_name)

        for ix in interactions_raw:
            desc = (ix.get("description") or "").lower()
            if any(w in desc for w in ("contraindicated", "severe", "fatal")):
                sev = "severe"
            elif any(w in desc for w in ("caution", "monitor", "moderate")):
                sev = "moderate"
            else:
                sev = "mild"
            interactions.append({**ix, "_severity": sev})

        max_cnt = max((r.get("report_count", 0) for r in reactions_raw), default=1) or 1
        for rx in reactions_raw:
            cnt = rx.get("report_count", 0)
            pct = cnt / max_cnt
            sev = "severe" if pct > 0.66 else ("moderate" if pct > 0.33 else "mild")
            reactions.append({**rx, "_severity": sev})

    factors = []
    score = 1.0

    n_sev_ix = sum(1 for ix in interactions if ix.get("_severity") == "severe")
    n_mod_ix = sum(1 for ix in interactions if ix.get("_severity") == "moderate")
    n_sev_rx = sum(1 for rx in reactions if rx.get("_severity") == "severe")
    n_mod_rx = sum(1 for rx in reactions if rx.get("_severity") == "moderate")

    if n_sev_ix:
        v = round(n_sev_ix * 0.8, 1)
        factors.append({"factor": f"{n_sev_ix} severe interaction(s)", "value": v})
        score += v
    if n_mod_ix:
        v = round(n_mod_ix * 0.3, 1)
        factors.append({"factor": f"{n_mod_ix} moderate interaction(s)", "value": v})
        score += v
    if n_sev_rx:
        v = round(n_sev_rx * 0.5, 1)
        factors.append({"factor": f"{n_sev_rx} high-frequency reaction(s)", "value": v})
        score += v
    if n_mod_rx:
        v = round(n_mod_rx * 0.15, 1)
        factors.append({"factor": f"{n_mod_rx} moderate-frequency reaction(s)", "value": v})
        score += v

    age_mult = {"Pediatric (<18)": 0.6, "Adult (18-64)": 0.0, "Elderly (65+)": 0.8}
    age_add = age_mult.get(age_group, 0.0)
    if age_add:
        factors.append({"factor": f"Age — {age_group}", "value": age_add})
        score += age_add

    for cond in comorbidities:
        w = _COMORBIDITY_WEIGHTS.get(cond, 0.3)
        factors.append({"factor": cond, "value": w})
        score += w

    d_add = {"Low": -0.3, "Standard": 0.0, "High": 0.6}.get(dosage_level, 0.0)
    if d_add:
        factors.append({"factor": f"Dosage — {dosage_level}", "value": d_add})
        score += d_add

    dur_add = {"Short-term (<2 wk)": 0.0, "Long-term (2-12 wk)": 0.4,
               "Chronic (>12 wk)": 0.7}.get(duration, 0.0)
    if dur_add:
        factors.append({"factor": f"Duration — {duration}", "value": dur_add})
        score += dur_add

    if concurrent_medications > 0:
        med_add = round(min(1.5, concurrent_medications * 0.35), 1)
        factors.append({"factor": f"{concurrent_medications} concurrent medication(s)", "value": med_add})
        score += med_add

    score = min(10.0, max(0.0, round(score, 1)))

    if score >= 7:
        risk_level = "HIGH"
    elif score >= 4:
        risk_level = "MODERATE"
    else:
        risk_level = "LOW"

    warnings = []
    if any("Liver" in c for c in comorbidities):
        warnings.append("Pre-existing liver disease increases hepatotoxicity risk.")
    if any("Kidney" in c for c in comorbidities):
        warnings.append("Renal impairment may reduce drug clearance — consider dose adjustment.")
    if any("Pregnancy" in c for c in comorbidities):
        warnings.append("Verify FDA pregnancy category before prescribing.")
    if age_group == "Elderly (65+)":
        warnings.append("Elderly patients may need dose reduction due to altered pharmacokinetics.")
    if concurrent_medications >= 3:
        warnings.append(f"{concurrent_medications} concurrent medications significantly increase interaction risk.")
    if n_sev_ix:
        warnings.append("Severe drug interactions detected — review before co-prescribing.")
    if not warnings:
        warnings.append("No elevated-risk factors detected for this profile.")

    return {
        "tool": "assess_patient_risk",
        "drug_name": resolved_name,
        "risk_score": score,
        "risk_level": risk_level,
        "factors": factors,
        "warnings": warnings,
        "patient_context": {
            "age_group": age_group,
            "comorbidities": comorbidities,
            "dosage_level": dosage_level,
            "duration": duration,
            "concurrent_medications": concurrent_medications,
        },
        "interaction_count": len(interactions),
        "reaction_count": len(reactions),
        "latency_ms": round((time.time() - t0) * 1000, 1),
    }


# ══════════════════════════════════════════════════════════════
#  Tool Registry
# ══════════════════════════════════════════════════════════════

TOOL_REGISTRY: Dict[str, callable] = {
    "query_drug_label": query_drug_label,
    "lookup_drug_interactions": lookup_drug_interactions,
    "analyze_adverse_events": analyze_adverse_events,
    "get_drug_profile": get_drug_profile,
    "assess_patient_risk": assess_patient_risk,
}


def execute_tool(tool_name: str, **kwargs) -> Dict[str, Any]:
    """Execute a tool by name with the given keyword arguments."""
    if tool_name not in TOOL_REGISTRY:
        return {"error": f"Unknown tool: {tool_name}"}
    try:
        return TOOL_REGISTRY[tool_name](**kwargs)
    except Exception as exc:
        return {"tool": tool_name, "error": str(exc)}
