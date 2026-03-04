# Task 1: AI-Assisted IDE Setup & Reflection

> **CS 5588 — Week 6 Hands-On Assignment**
> **Tool Used:** Cursor IDE (AI-powered code editor, approved alternative to Google Antigravity)

---

## 1. IDE Setup

### Tool Selection

For this assignment, our team used **Cursor IDE** instead of Google Antigravity IDE, as approved by the instructor. Cursor is an AI-powered code editor built on VS Code that provides intelligent code generation, refactoring suggestions, and contextual understanding of the entire project codebase.

### Connection to Repository

- Connected Cursor to the project repository at [https://github.com/SalmanM1/CS5588Week6](https://github.com/SalmanM1/CS5588Week6)
- Cursor indexed the full codebase (RAG engine, Knowledge Graph, Streamlit frontend, ingestion pipeline, tests) for context-aware code assistance
- The AI agent was able to understand the full project architecture: openFDA API integration, FAISS + BM25 hybrid retrieval, Knowledge Graph (SQLite/Neo4j), and Streamlit multi-page UI

### Environment

- **OS:** Windows 10
- **Python:** 3.11+
- **Key Dependencies:** Streamlit, FAISS, rank-bm25, google-generativeai, scikit-learn, pandas, neo4j

---

## 2. How Cursor Was Used to Improve the System

### 2a. Agent Layer Architecture Design

Cursor's AI was used to design and implement the entire **AI Agent layer** for Week 6. The agent transforms TruPharma from a single-query RAG system into an intelligent decision-support application capable of:

- **Reasoning** about multi-step drug-safety questions
- **Selecting** the right tool(s) from a registry of 5 callable tools
- **Executing** multi-step workflows (e.g., "Compare interactions of ibuprofen and aspirin" triggers two parallel tool calls and a synthesis step)
- **Producing** evidence-grounded explanations with citations

### 2b. Tool Conversion

Cursor helped convert existing project components into 5 callable agent tools:

| Tool | Wraps | Purpose |
|------|-------|---------|
| `query_drug_label` | `run_rag_query()` | FDA drug-label evidence retrieval with RAG |
| `lookup_drug_interactions` | `KnowledgeGraph.get_interactions()` | Drug-drug interaction lookup from KG |
| `analyze_adverse_events` | `KnowledgeGraph.get_drug_reactions()` | Adverse event analysis from FAERS data |
| `get_drug_profile` | `build_unified_profile()` | Comprehensive drug profile (label + FAERS + NDC + KG) |
| `assess_patient_risk` | Risk calculator logic | Personalized risk scoring based on patient context |

### 2c. Chat Interface Integration

Cursor assisted in building a new **Agent Chat** page in the Streamlit application, providing:

- Conversational chat-style interface with message history
- Real-time display of agent reasoning steps and tool selections
- Evidence panels showing which tools were called and what data was retrieved
- Seamless integration with the existing Safety Chat and Signal Heatmap pages

---

## 3. Reflection

### What Worked Well

- **Codebase Understanding:** Cursor's ability to index and understand the entire project made it extremely effective for generating code that integrates correctly with existing modules (e.g., respecting import paths, using the right API signatures from `engine.py`, `loader.py`, and `drug_profile.py`).
- **Rapid Prototyping:** The agent runner, tool schemas, and Streamlit chat page were created rapidly with Cursor suggesting architecturally consistent patterns.
- **Consistency:** Generated code followed the same patterns as the existing codebase (project-root path insertion, graceful degradation, logging conventions).

### Challenges

- **Complex Integration Points:** The agent needed to correctly interface with multiple subsystems (RAG engine, Knowledge Graph, FAERS data, risk calculator). Cursor required guidance to ensure all edge cases were handled (e.g., KG unavailable, API timeouts).
- **Streamlit State Management:** The chat interface required careful session-state management to maintain conversation history across Streamlit reruns.

### Key Learning

Building an AI agent on top of an existing RAG system requires careful **tool design** — each tool must have a clear, well-scoped responsibility with predictable inputs/outputs. The agent's effectiveness depends directly on the quality of the tool schemas and the specificity of the tool descriptions. This aligns with the broader principle that **agentic AI systems are only as good as the tools they can access**.

---

*CS 5588 · Spring 2026 · Week 6 Assignment*
