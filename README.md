# TruPharma GenAI Assistant

> **CS 5588 — Week 6 Capstone Module**
> Drug Label Evidence RAG System + AI Agent Layer

**Team:** Salman Mirza, Amy Ngo, Nithin Songala

---

## Overview

TruPharma is a Retrieval-Augmented Generation (RAG) application that answers drug-label questions using official FDA data from the [openFDA Drug Label API](https://open.fda.gov/apis/drug/label/). The system fetches real-time drug labeling records, indexes them with hybrid retrieval (dense + sparse), and generates grounded answers with evidence citations.

**Week 6** adds an **AI Agent layer** that transforms TruPharma from a single-query RAG system into an intelligent decision-support application capable of reasoning, selecting tools, and executing multi-step workflows.

### Target Users

| Persona | Example Task |
|---------|-------------|
| **Pharmacist** | "What dosage of acetaminophen is recommended and what are the warnings?" |
| **Clinician** | "What drug interactions should I know about for ibuprofen?" |
| **Patient** | "I take aspirin daily — when should I stop use?" |
| **Analyst** | "Assess the risk of metformin for an elderly patient with kidney disease" |

### Value Proposition

Provides **faster time-to-answer** with **higher trust** by returning an evidence pack (drug label sections) and a **citation-enforced grounded answer**, refusing when evidence is insufficient. The AI agent enables **multi-step reasoning** across multiple data sources.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                   Streamlit UI (Frontend)                     │
│   Safety Chat  ·  Agent Chat  ·  Signal Heatmap  ·  Logs     │
└────────────────────────┬─────────────────────────────────────┘
                         │
              ┌──────────┴──────────┐
              │                     │
              ▼                     ▼
┌─────────────────────┐  ┌──────────────────────────────────┐
│   RAG Pipeline      │  │       AI Agent Runner             │
│   (rag_engine.py)   │  │   (agent/agent_runner.py)         │
│                     │  │                                    │
│  openFDA → chunk →  │  │  1. Interpret user request         │
│  index → retrieve → │  │  2. Select tool(s) from registry   │
│  generate → log     │  │  3. Execute multi-step workflow    │
└─────────┬───────────┘  │  4. Synthesize grounded answer     │
          │              └────────────┬───────────────────────┘
          │                           │
          │              ┌────────────┴───────────────────────┐
          │              │        Agent Tools                  │
          │              │  (agent/tools.py)                   │
          │              │                                     │
          │              │  • query_drug_label (RAG)           │
          │              │  • lookup_drug_interactions (KG)    │
          │              │  • analyze_adverse_events (FAERS)   │
          │              │  • get_drug_profile (unified)       │
          │              │  • assess_patient_risk (scoring)    │
          │              └─────────────────────────────────────┘
          │
          ▼
┌─────────────────┐    ┌────────────────────┐    ┌──────────────┐
│  openFDA API    │    │  Knowledge Graph    │    │  Gemini LLM  │
│  (Drug Labels)  │    │  (SQLite/Neo4j)     │    │  (Optional)  │
└─────────────────┘    └────────────────────┘    └──────────────┘
```

### Agent Data Flow

1. User enters a drug-safety question in the Agent Chat interface
2. The agent runner interprets intent (LLM-based or rule-based)
3. Appropriate tool(s) are selected from the 5-tool registry
4. Tools execute against live FDA data, Knowledge Graph, and/or FAERS records
5. Results are synthesized into a grounded answer with citations
6. Reasoning steps, tool calls, and metrics are displayed transparently

### Agent Tools

| Tool | Wraps | Purpose |
|------|-------|---------|
| `query_drug_label` | `run_rag_query()` | FDA drug-label evidence retrieval with RAG |
| `lookup_drug_interactions` | `KnowledgeGraph.get_interactions()` | Drug-drug interaction lookup from KG |
| `analyze_adverse_events` | `KnowledgeGraph.get_drug_reactions()` | Adverse event analysis from FAERS data |
| `get_drug_profile` | `build_unified_profile()` | Comprehensive multi-source drug profile |
| `assess_patient_risk` | Risk calculator | Personalized risk scoring with patient context |

---

## Deployed Application

**Live App:** https://trupharma-clinical-intelligence-fhu8qhqrgjch9yhocjaeuz.streamlit.app/

---

## Setup & Run Locally

```bash
# 1. Clone the repo
git clone https://github.com/SalmanM1/CS5588Week6.git
cd CS5588Week6

# 2. Create a virtual environment (recommended)
python -m venv .venv
.venv\Scripts\activate       # Windows
# source .venv/bin/activate  # macOS/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Build the knowledge graph (optional but recommended)
python scripts/build_kg.py

# 5. Run the Streamlit app
streamlit run src/frontend/app.py
```

### Optional: Gemini LLM

To enable LLM-powered agent planning and answer generation:

1. Get a free API key at [Google AI Studio](https://aistudio.google.com/apikey)
2. Enter it in the Agent Chat sidebar under **Gemini API Key**
3. The agent will use Gemini for intent detection, parameter extraction, and answer synthesis

Without a Gemini key, the agent uses **rule-based intent detection** and **structured synthesis** — fully functional but less conversational.

---

## Week 6 Additions

### Task 1: IDE Setup & Reflection
- Used Cursor IDE (approved alternative to Google Antigravity)
- See [`task1_antigravity_report.md`](task1_antigravity_report.md)

### Task 2: Agent Tools
- 5 callable tools in [`agent/tools.py`](agent/tools.py)
- Tool schemas in [`agent/tool_schemas.py`](agent/tool_schemas.py)

### Task 3: AI Agent
- Agent runner in [`agent/agent_runner.py`](agent/agent_runner.py)
- Dual-mode: LLM (Gemini) + rule-based fallback
- Multi-step workflow execution with synthesis

### Task 4: Application Integration
- Agent Chat page: [`src/frontend/pages/agent_chat.py`](src/frontend/pages/agent_chat.py)
- Updated landing page with Agent Chat navigation

### Task 5: Evaluation
- 3 evaluation scenarios (simple → complex)
- See [`task4_evaluation_report.md`](task4_evaluation_report.md)
- **Demo Video (3–5 min):** https://youtu.be/EktZdNqyAYE

---

## Logging & Monitoring

All query interactions are logged to `logs/product_metrics.csv` with the following fields:

| Column | Description |
|--------|-------------|
| `timestamp` | UTC timestamp of the query |
| `query` | User's question (truncated to 200 chars) |
| `latency_ms` | End-to-end pipeline latency in milliseconds |
| `evidence_ids` | Chunk IDs of retrieved evidence |
| `confidence` | Heuristic confidence score (0–1) |
| `num_evidence` | Number of evidence items returned |
| `num_records` | Drug label records fetched from FDA API |
| `retrieval_method` | hybrid / dense / sparse |
| `llm_used` | Whether Gemini LLM was used |
| `answer_preview` | First 150 chars of the generated answer |

---

## Repository Structure

```
CS5588Week6/
├── agent/                             # Week 6: AI Agent layer
│   ├── __init__.py
│   ├── tools.py                       # 5 callable tool implementations
│   ├── tool_schemas.py                # Declarative tool definitions
│   └── agent_runner.py                # Core reasoning engine
├── data/
│   └── kg/
│       └── trupharma_kg.db            # SQLite Knowledge Graph
├── docs/                              # Documentation & diagrams
├── logs/
│   └── product_metrics.csv            # Interaction logs
├── scripts/
│   ├── build_kg.py                    # Knowledge Graph builder
│   └── ...
├── src/
│   ├── frontend/
│   │   ├── app.py                     # Landing page (updated)
│   │   ├── .streamlit/config.toml
│   │   └── pages/
│   │       ├── primary_demo.py        # Safety Chat (RAG)
│   │       ├── agent_chat.py          # Week 6: Agent Chat interface
│   │       ├── signal_heatmap.py      # Disparity dashboard
│   │       └── stress_test.py         # Stress test scenarios
│   ├── ingestion/                     # openFDA, FAERS, NDC, RxNorm clients
│   ├── kg/                            # Knowledge Graph (backend, loader, schema)
│   └── rag/                           # RAG engine, drug profiles, enrichment
├── tests/
├── task1_antigravity_report.md        # Week 6: IDE setup report
├── task4_evaluation_report.md         # Week 6: Evaluation report
├── Contribution.md                    # Individual contribution
├── requirements.txt
└── README.md
```

---

## Production Failure Scenario & Mitigation

**Scenario:** openFDA API returns 0 results for an obscure or misspelled drug name.

**Mitigation:**
- The system detects empty result sets and returns a clear "Not enough evidence" message rather than hallucinating
- The AI agent can fall back to Knowledge Graph tools when the RAG pipeline returns insufficient evidence
- Logging captures the failed query for later analysis
- Future improvement: add fuzzy drug-name matching and spell-check suggestions before querying the API

---

## Deployment & Scaling

| Aspect | Approach |
|--------|----------|
| **Hosting** | Streamlit Community Cloud (free tier) |
| **Data** | Real-time openFDA API (no local data storage needed) |
| **Scaling** | API rate limits managed via pagination; add API key for higher limits |
| **Monitoring** | CSV-based logging; extend to cloud logging (e.g., CloudWatch) for production |
| **CI/CD** | GitHub integration with Streamlit Cloud for auto-deploy on push |

---

## Impact Evaluation

- **Workflow improvement:** Reduces manual label scanning from 10–15 min to under 30 sec per question
- **Time-to-decision:** Estimated 80% reduction in time-to-answer for drug-label queries
- **Trust indicators:** Every answer includes evidence chunk IDs, source fields, and confidence scores; system refuses to answer when evidence is insufficient
- **Agent value-add:** Multi-step reasoning enables complex queries (comparisons, risk assessments) that single-query RAG cannot handle

---

*CS 5588 · Spring 2026 · Week 6 Assignment*
