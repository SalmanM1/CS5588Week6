"""
tool_schemas.py · TruPharma Agent Tool Definitions
====================================================
Declarative schemas for each agent tool. The agent runner uses these
to decide which tool(s) to invoke and how to parse arguments.

Each schema contains:
  - name:        unique tool identifier
  - description: natural-language summary (used by the LLM for selection)
  - parameters:  dict of {param_name: {type, description, required, default}}
  - returns:     description of the tool's output
"""

TOOL_SCHEMAS = [
    {
        "name": "query_drug_label",
        "description": (
            "Search FDA drug labels using RAG (Retrieval-Augmented Generation). "
            "Fetches real-time drug labeling records from the openFDA API, "
            "indexes them with hybrid retrieval (dense + sparse), and generates "
            "a grounded answer with evidence citations. Best for questions about "
            "dosage, warnings, active ingredients, drug interactions, overdosage, "
            "stop-use guidance, and other drug-label content."
        ),
        "parameters": {
            "query": {
                "type": "string",
                "description": "Natural-language drug-label question",
                "required": True,
            },
            "method": {
                "type": "string",
                "description": "Retrieval method: hybrid, dense, or sparse",
                "required": False,
                "default": "hybrid",
                "enum": ["hybrid", "dense", "sparse"],
            },
            "top_k": {
                "type": "integer",
                "description": "Number of top evidence chunks to retrieve (3-10)",
                "required": False,
                "default": 5,
            },
        },
        "returns": "Answer with evidence citations, confidence score, and latency metrics.",
    },
    {
        "name": "lookup_drug_interactions",
        "description": (
            "Look up known drug-drug interactions for a specific drug from the "
            "Knowledge Graph. Returns interaction partners, severity assessment, "
            "and clinical descriptions sourced from FDA labels. Use this when "
            "the user asks about drug interactions, contraindications, or whether "
            "two drugs can be taken together."
        ),
        "parameters": {
            "drug_name": {
                "type": "string",
                "description": "Name of the drug to look up interactions for",
                "required": True,
            },
        },
        "returns": "List of interacting drugs with severity and descriptions.",
    },
    {
        "name": "analyze_adverse_events",
        "description": (
            "Analyze adverse events (side effects) reported for a drug using "
            "FAERS (FDA Adverse Event Reporting System) data from the Knowledge "
            "Graph. Returns top reported reactions with frequency counts and "
            "severity classifications. Use this for questions about side effects, "
            "adverse reactions, safety signals, or real-world safety data."
        ),
        "parameters": {
            "drug_name": {
                "type": "string",
                "description": "Name of the drug to analyze adverse events for",
                "required": True,
            },
        },
        "returns": "Top adverse reactions with report counts, severity, and co-reported drugs.",
    },
    {
        "name": "get_drug_profile",
        "description": (
            "Build a comprehensive drug profile by combining data from multiple "
            "sources: FDA drug labels, FAERS adverse events, NDC product metadata, "
            "and the Knowledge Graph. Returns a unified view including drug "
            "identity, label sections, real-world safety data, and disparity "
            "analysis (label vs. FAERS). Best for broad questions like 'Tell me "
            "everything about X' or when multiple data sources are needed."
        ),
        "parameters": {
            "query": {
                "type": "string",
                "description": "Natural-language query mentioning the drug of interest",
                "required": True,
            },
        },
        "returns": "Unified drug profile with identity, label data, FAERS summary, NDC metadata, and KG data.",
    },
    {
        "name": "assess_patient_risk",
        "description": (
            "Compute a personalized risk assessment score for a drug based on "
            "patient context (age group, comorbidities, dosage level, treatment "
            "duration, concurrent medications). Combines drug-level data from "
            "the Knowledge Graph with patient factors to produce a 0-10 risk "
            "score with factor breakdown and contextual warnings. Use this when "
            "the user provides patient-specific information or asks about "
            "personalized risk."
        ),
        "parameters": {
            "drug_name": {
                "type": "string",
                "description": "Name of the drug to assess risk for",
                "required": True,
            },
            "age_group": {
                "type": "string",
                "description": "Patient age group",
                "required": False,
                "default": "Adult (18-64)",
                "enum": ["Pediatric (<18)", "Adult (18-64)", "Elderly (65+)"],
            },
            "comorbidities": {
                "type": "array",
                "description": "List of patient comorbidities/conditions",
                "required": False,
                "default": [],
            },
            "dosage_level": {
                "type": "string",
                "description": "Dosage level being used",
                "required": False,
                "default": "Standard",
                "enum": ["Low", "Standard", "High"],
            },
            "duration": {
                "type": "string",
                "description": "Expected treatment duration",
                "required": False,
                "default": "Short-term (<2 wk)",
                "enum": ["Short-term (<2 wk)", "Long-term (2-12 wk)", "Chronic (>12 wk)"],
            },
            "concurrent_medications": {
                "type": "integer",
                "description": "Number of other medications the patient is taking",
                "required": False,
                "default": 0,
            },
        },
        "returns": "Risk score (0-10), factor breakdown, and contextual warnings.",
    },
]


def get_tool_names() -> list:
    """Return a list of all available tool names."""
    return [t["name"] for t in TOOL_SCHEMAS]


def get_tool_schema(name: str) -> dict:
    """Return the schema for a specific tool by name."""
    for t in TOOL_SCHEMAS:
        if t["name"] == name:
            return t
    raise ValueError(f"Unknown tool: {name}")


def format_tools_for_prompt() -> str:
    """Format all tool schemas into a string suitable for an LLM prompt."""
    lines = []
    for t in TOOL_SCHEMAS:
        lines.append(f"### {t['name']}")
        lines.append(f"**Description:** {t['description']}")
        lines.append("**Parameters:**")
        for pname, pdef in t["parameters"].items():
            req = "required" if pdef.get("required") else "optional"
            default = f", default={pdef['default']}" if "default" in pdef else ""
            lines.append(f"  - `{pname}` ({pdef['type']}, {req}{default}): {pdef['description']}")
        lines.append(f"**Returns:** {t['returns']}")
        lines.append("")
    return "\n".join(lines)
