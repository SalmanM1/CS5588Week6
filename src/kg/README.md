# Knowledge Graph (`src/kg`)

The KG package stores drug, reaction, ingredient, and product data as a property graph (nodes + typed edges) and exposes structured queries for the RAG pipeline. It serves three roles at runtime:

1. **Drug name resolution** — maps natural-language tokens (brand names, generics, RxCUI codes) to canonical Drug nodes via an O(1) alias table.
2. **Scope validation** — gates out-of-scope queries before they hit the openFDA API, preventing irrelevant results from being surfaced to the user.
3. **Structured enrichment** — injects drug interactions, adverse reactions, co-reported drugs, ingredients, and disparity analysis into the RAG answer and the frontend visualization.

## Architecture

```
src/kg/
├── backend.py          # GraphBackend protocol + SqliteBackend + Neo4jBackend
├── loader.py           # KnowledgeGraph read-only query API + load_kg()
├── dynamic_builder.py  # On-demand KG expansion (progressive loading)
├── schema.py           # Backward-compat shim (delegates to backend.py)
├── __init__.py
└── builders/
    ├── rxnorm_nodes.py          # Step 1: Drug nodes from openFDA + RxNorm
    ├── ndc_edges.py             # Step 2: Ingredient nodes + HAS_ACTIVE_INGREDIENT edges
    ├── label_edges.py           # Step 3: INTERACTS_WITH edges from label text
    ├── faers_edges.py           # Step 4: CO_REPORTED_WITH + DRUG_CAUSES_REACTION edges
    └── label_reaction_edges.py  # Step 5: LABEL_WARNS_REACTION edges (disparity analysis)

src/rag/
└── graph_enrichment.py  # Prepends KG context to chunks before embedding (ingestion-time)

scripts/
├── build_kg.py                  # Full KG build pipeline (+ --drug for single-drug)
└── migrate_sqlite_to_neo4j.py   # One-time SQLite → Neo4j migration

tests/
├── test_enrichment.py           # Benchmark: plain vs graph-enriched retrieval
├── test_dynamic_builder.py      # Dynamic expansion unit tests
├── test_neo4j_backend.py        # Neo4j backend integration tests
└── test_reverse_lookups.py      # Reverse lookup tests
```

## Backend Abstraction

All KG reads and writes go through the `GraphBackend` protocol defined in `backend.py`. Two implementations are provided:

| | **SqliteBackend** | **Neo4jBackend** |
|---|---|---|
| Storage | Local `.db` file | Remote Neo4j server |
| Config | Zero — just a file path | URI + credentials (env vars or CLI) |
| Write strategy | Immediate per-row INSERT/UPDATE | Buffered batch MERGE (flushes at 500 ops or on `commit()`) |
| Best for | Local dev, small datasets, CI | Production, large graphs, multi-hop traversals |

### Backend selection

The active backend is chosen automatically:

1. If the `NEO4J_URI` environment variable is set, Neo4j is used.
2. Otherwise, SQLite is used (file at `data/kg/trupharma_kg.db`).

You can also force it explicitly:

```python
from src.kg.backend import create_backend

backend = create_backend("sqlite", sqlite_path="data/kg/trupharma_kg.db")
backend = create_backend("neo4j")  # reads NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD from env
```

### Falling back to SQLite

If Neo4j is unavailable or you don't set any `NEO4J_*` env vars, everything falls back to SQLite automatically. The existing `data/kg/trupharma_kg.db` file continues to work with zero changes.

## Build Pipeline

The KG is constructed by `scripts/build_kg.py`, which runs five steps in sequence. Each step reads from external APIs and writes nodes/edges through the active backend.

### Step 1 — Drug nodes (`rxnorm_nodes.py`)

Discovers the top drugs by label count from the openFDA `/drug/label.json?count=openfda.generic_name.exact` endpoint, then resolves each through the RxNorm REST API (exact match → `/drugs` concept lookup → approximate/fuzzy match → spelling correction). Each resolved drug becomes a `Drug` node with `generic_name`, `brand_names`, and `rxcui` properties. At the end, `rebuild_aliases()` populates the alias lookup table.

### Step 2 — Ingredient edges (`ndc_edges.py`)

For each Drug node, fetches NDC (National Drug Code) product metadata via `src/ingestion/ndc`. Creates `Ingredient` nodes and `HAS_ACTIVE_INGREDIENT` edges with strength data, plus `Product` nodes and `HAS_PRODUCT` edges with dosage form, route, and manufacturer info.

### Step 3 — Interaction edges (`label_edges.py`)

Fetches openFDA label records for each drug and extracts interacting drug names from two sources:
- **Structured**: the `drug_interactions_table` field (tabular data in the label).
- **Prose**: the `drug_interactions` free-text field, parsed by Gemini 2.0 Flash (when a `GEMINI_API_KEY` is available) with a regex-based fallback that matches against the known drug name dictionary.

Creates bidirectional `INTERACTS_WITH` edges with `source: "label"`.

### Step 4 — FAERS edges (`faers_edges.py`)

Queries the openFDA FAERS (FDA Adverse Event Reporting System) count endpoints for each drug:
- `count=patient.drug.medicinalproduct.exact` → `CO_REPORTED_WITH` edges (drugs frequently appearing in the same adverse-event reports).
- `count=patient.reaction.reactionmeddrapt.exact` → `Reaction` nodes + `DRUG_CAUSES_REACTION` edges with `report_count`.

Co-reported drugs that don't yet exist in the graph are inserted as stub `Drug` nodes so edges are never dangling.

### Step 5 — Label reaction edges (`label_reaction_edges.py`)

Re-fetches label records and extracts adverse reaction terms from `adverse_reactions`, `warnings`, `warnings_and_cautions`, `boxed_warning`, and `contraindications` fields. Matches each extracted term against the Reaction nodes created in Step 4 using longest-match-first regex. Creates `LABEL_WARNS_REACTION` edges, which enable **disparity analysis**: comparing what the label warns about vs. what the real world reports.

### Final — Alias rebuild

After all steps, `rebuild_aliases()` is called one more time to index any stub Drug nodes created during Step 4. This ensures every known name variant (generic, brand, RxCUI) resolves in O(1) at query time.

### Running the build

```bash
# Default (200 drugs, SQLite)
python scripts/build_kg.py

# Custom seed size
python scripts/build_kg.py --max-drugs 50

# With Gemini for better interaction extraction
GEMINI_API_KEY=your_key python scripts/build_kg.py --max-drugs 200

# Skip specific steps
python scripts/build_kg.py --skip-ndc --skip-faers

# Neo4j backend
python scripts/build_kg.py \
  --backend neo4j \
  --neo4j-uri bolt://localhost:7687 \
  --neo4j-user neo4j \
  --neo4j-password your_password \
  --max-drugs 200

# Single-drug build (uses dynamic_builder)
python scripts/build_kg.py --drug gabapentin
```

## Data Model

The SQLite tables map directly to a labeled property graph:

### Node labels

| Label | Key properties | Example |
|---|---|---|
| `Drug` | `id`, `generic_name`, `brand_names`, `rxcui` | `(:Drug {id: "315266", generic_name: "aspirin"})` |
| `Reaction` | `id`, `reactionmeddrapt` | `(:Reaction {id: "reaction:headache"})` |
| `Ingredient` | `id`, `name` | `(:Ingredient {id: "aspirin", name: "ASPIRIN"})` |
| `Product` | `id`, `drug_id`, `generic_name` | `(:Product {id: "product:315266"})` |
| `DrugAlias` | `alias`, `node_id` | `(:DrugAlias {alias: "advil", node_id: "206878"})` |

### Relationship types

| Type | Direction | Meaning | Source |
|---|---|---|---|
| `INTERACTS_WITH` | Drug → Drug | Drug-drug interaction | FDA label text |
| `CO_REPORTED_WITH` | Drug → Drug | Co-reported in same adverse event report | FAERS |
| `DRUG_CAUSES_REACTION` | Drug → Reaction | Adverse reaction with report count | FAERS |
| `LABEL_WARNS_REACTION` | Drug → Reaction | Adverse reaction warned on official label | FDA label |
| `HAS_ACTIVE_INGREDIENT` | Drug → Ingredient | Active ingredient with strength | NDC |
| `HAS_PRODUCT` | Drug → Product | Product metadata (form, route, manufacturer) | NDC |

### Constraints and indexes (Neo4j)

Created automatically on first connection:

```cypher
CREATE CONSTRAINT FOR (n:Drug)       REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT FOR (n:Reaction)   REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT FOR (n:Ingredient) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT FOR (n:Product)    REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT FOR (n:DrugAlias)  REQUIRE n.alias IS UNIQUE;
CREATE INDEX FOR (n:Drug) ON (n.generic_name);
```

## Drug Name Resolution

When a user submits a natural-language query, the system needs to extract a drug name before it can look anything up in the KG. This happens in `src/rag/drug_profile.py:_extract_drug_name()`.

### How extraction works

1. **Tokenize** the query and drop common stopwords (`what`, `the`, `recommended`, `dosage`, `warnings`, etc.).
2. **Check each remaining candidate against the KG alias table.** The alias table maps generic names, brand names, and RxCUI codes to their Drug node IDs. The first token that matches a known drug wins.
3. **Fall back** to the first non-stopword token if no KG match is found (e.g. when the KG is unavailable or the drug wasn't in the seed list).

This means both generic names (`acetaminophen`, `ibuprofen`) and brand names (`Advil`, `Tylenol`) are resolved correctly regardless of where they appear in the sentence.

### The alias table

During the KG build, `rebuild_aliases()` populates a lookup that maps every known name variant to its canonical node ID:

| Alias | Node ID |
|---|---|
| `acetaminophen` | `161` |
| `tylenol` | `161` |
| `161` (RxCUI) | `161` |
| `advil` | `206878` |
| `ibuprofen` | `206878` |

Both `SqliteBackend` and `Neo4jBackend` maintain this table (as a SQL table and as `DrugAlias` nodes, respectively). The lookup is O(1).

### When the drug is not found

If no candidate matches the KG, the frontend shows:

> *"This drug is not in the Knowledge Graph seed list. Try a more common drug, or rebuild with a larger seed."*

Fix it by rebuilding with a larger seed:

```bash
python scripts/build_kg.py --max-drugs 500
```

## Out-of-Scope Query Detection

Not every question belongs in a drug-safety system. A query like *"What is the projected cost of antimicrobial resistance to GDP in 2050?"* doesn't reference any drug, but the openFDA API will still return results because drug labels contain words like "antimicrobial" and "resistance." Without a gate, the system would surface irrelevant evidence with a falsely high confidence score.

The RAG pipeline (`src/rag/engine.py`) runs a **scope-validation gate** before calling the openFDA API:

1. `_extract_drug_name(query)` tokenizes the query, drops stopwords, and checks each candidate against the KG alias table. If no token matches, it falls back to the first non-stopword token.
2. `_drug_is_known(name)` validates the extracted name:
   - **KG alias table** (O(1), local) — checks both Drug nodes and Ingredient nodes.
   - **RxNorm exact-match + `/drugs` concept lookup** (1-2 HTTP calls) — catches drugs not in the KG seed list.
   - If RxNorm is unreachable, the query is allowed through (benefit of the doubt).
3. If neither source recognizes the name as a drug, the pipeline short-circuits immediately with `"Not enough evidence in the retrieved context."`, 0.0 confidence, and no evidence — avoiding the wasted openFDA API call entirely.

This means:
- Queries about **known drugs** (in KG) are validated instantly with zero extra latency.
- Queries about **uncommon drugs** (not in KG but in RxNorm) are validated via 1-2 fast HTTP calls and proceed normally.
- **Off-topic queries** (economics, politics, general science) are rejected in ~500ms with a clear signal.

## RAG Pipeline Integration

The KG participates in the RAG pipeline at four points:

### 1. Pre-retrieval: scope validation

As described above, `_drug_is_known()` runs before the openFDA API call. This is the cheapest possible check — a local hash lookup followed by at most 2 HTTP calls — and prevents the system from wasting 2-3 seconds fetching irrelevant FDA label text.

### 2. Ingestion-time: graph-enriched chunk embeddings

Before chunks are embedded, the `src/rag/graph_enrichment.py` module prepends structured KG context to each chunk's text so that the resulting vectors capture multi-hop relationships (interactions, reactions, ingredients, FAERS disparity signals) rather than just label prose. This happens during the offline ingestion path — the query-time pipeline is unaffected.

When `build_artifacts(kg=...)` receives a `KnowledgeGraph` instance, it calls `enrich_chunk()` for every `TextChunk` and `SubChunk`. For each chunk, the drug ID is extracted from the chunk ID (the segment before `::`) and used to query the KG. The enriched text is stored in the chunk's `enriched_text` field and a `graph_enriched` flag is set to `True`. The original `text` field is never mutated.

A `[GRAPH CONTEXT]` block is prepended in this format:

```
[GRAPH CONTEXT]
Drug: metformin | RxCUI: 6809 | Also known as: GLUCOPHAGE, FORTAMET
Ingredients: METFORMIN HYDROCHLORIDE
Interactions: insulin, glyburide, furosemide, nifedipine, cationic drugs
Adverse reactions (FAERS): Diarrhoea, Nausea, Drug ineffective, Fatigue, Vomiting
Co-reported drugs: INSULIN, LISINOPRIL, ATORVASTATIN, AMLODIPINE, METOPROLOL
Emerging risks (FAERS not on label): [EMERGING RISK] Drug ineffective, [EMERGING RISK] Fatigue

<original chunk text>
```

**Per-drug caching** — Multiple chunks sharing the same `doc_id` (i.e. the same drug) reuse a single set of KG queries via a module-level cache (`_context_cache`). The cache is cleared between ingestion batches with `clear_context_cache()`.

**Graceful degradation** — If the drug is not found in the KG, the chunk text is returned unchanged. If a KG query raises an exception, a warning is emitted and the original text is preserved.

The manifest returned by `build_artifacts()` includes a `graph_enriched_chunks` count, and `run_rag_query()` surfaces this alongside `total_chunks` in its response for observability.

### 3. Post-retrieval: structured enrichment

After the RAG retrieval + answer generation phase, `run_rag_query()` calls `load_kg()` and fetches structured data for the resolved drug:

- `get_drug_identity(name)` — canonical identity (generic name, brand names, RxCUI).
- `get_interactions(name)` — drug-drug interactions from labels.
- `get_co_reported(name)` — co-reported drugs from FAERS.
- `get_drug_reactions(name)` — adverse reactions from FAERS with report counts.
- `get_ingredients(name)` — active ingredients with strengths from NDC.

This data is returned alongside the RAG answer and rendered in the frontend's Knowledge Graph panel, network visualization, risk calculator, and body heatmap.

### 4. Drug profile builder

The `build_unified_profile()` function in `src/rag/drug_profile.py` goes further: it also adds KG-sourced text sections (interactions, co-reported drugs, reactions, ingredients) into the `text_sections` list, making them available for FAISS + BM25 retrieval alongside the FDA label text.

## Disparity Analysis

A unique feature of the KG is its ability to compare **what drug labels warn about** against **what the real world reports**. This is computed by `KnowledgeGraph.get_disparity_analysis(name)`:

| Category | Definition |
|---|---|
| **Confirmed risks** | Reactions that appear on both the drug label (`LABEL_WARNS_REACTION`) and in FAERS reports (`DRUG_CAUSES_REACTION`). |
| **Emerging signals** | Reactions reported in FAERS but **not** mentioned on the drug label. These may represent under-documented risks. |
| **Unconfirmed warnings** | Reactions mentioned on the label but **not** appearing in FAERS data. These may be over-warned or very rare. |
| **Disparity score** | `len(emerging_signals) / len(faers_reactions)` — ranges from 0 (fully aligned) to 1 (fully divergent). |

The `drug_profile.py` module also computes this independently from live openFDA/FAERS data (not just the KG snapshot) via `compute_disparity()`, so the two analyses can complement each other.

## Frontend Integration

The KG powers several frontend panels in `src/frontend/pages/primary_demo.py`:

- **Knowledge Graph panel** — interactive vis.js network visualization with Drug at center, surrounded by ingredient, interaction, co-reported, and reaction nodes. Nodes are sized by importance; edges are dashed for milder evidence. Includes search, focus, and detail-on-click.
- **Summary insight cards** — most common reaction, most severe interaction, total relationship count.
- **Tabbed detail sections** — ingredients (pill badges), interactions (with severity badges), co-reported drugs (bar chart), adverse reactions (bar chart).
- **Personalized risk calculator** — combines KG-derived interaction severity and reaction frequency with patient context (age, comorbidities, dosage, duration, concurrent meds) to produce a heuristic risk score with transparent factor breakdown.
- **Adverse-event body map** — maps KG reactions to anatomical regions and renders a body-outline heatmap with radial gradient overlays.

## Neo4j Setup

[Neo4j](https://neo4j.com/) is an open-source **graph database** designed for storing and querying data that is naturally connected — nodes and relationships rather than rows and columns. Where a relational database would need multiple JOIN operations to traverse drug → interaction → co-reported drug → reaction, Neo4j follows those links in constant time because relationships are first-class citizens stored as direct pointers on disk. This makes it well-suited for the TruPharma KG, where multi-hop queries (e.g. "which adverse reactions are shared by all drugs that interact with aspirin?") benefit from native graph traversal. Neo4j uses the **Cypher** query language, which reads like ASCII art (`(a)-[:INTERACTS_WITH]->(b)`), and provides a built-in browser UI for visual exploration.

### 1. Install the driver

```bash
pip install 'neo4j>=5.0'
```

Already included in `requirements.txt`.

### 2. Run a Neo4j instance

Docker is the fastest way to get started:

```bash
docker run -d \
  --name trupharma-neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your_password \
  neo4j:5
```

The browser UI will be at `http://localhost:7474`.

### 3. Set environment variables

```bash
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USER=neo4j
export NEO4J_PASSWORD=your_password
# optional:
export NEO4J_DATABASE=neo4j
```

### 4. Query at runtime

No code changes needed in the RAG pipeline. `load_kg()` auto-detects the backend from environment variables:

```python
from src.kg.loader import load_kg

kg = load_kg()                          # auto-detects Neo4j or SQLite
identity = kg.get_drug_identity("aspirin")
reactions = kg.get_drug_reactions("aspirin")
summary   = kg.get_summary("aspirin")
```

## Write Batching (Neo4j)

Individual Cypher `MERGE` calls carry ~2-5ms of network overhead each. For a build with 200 drugs and ~10k edges, that adds up. The `Neo4jBackend` solves this by buffering writes internally:

1. `upsert_node()` / `upsert_edge()` append to an in-memory buffer.
2. When the buffer hits 500 items (or `commit()` is called), writes are flushed as a single `UNWIND ... MERGE` batch per node label / relationship type.
3. Any read method automatically flushes pending writes first, so reads are always consistent.

This brings amortized write latency down to ~0.1ms per operation, comparable to SQLite.

## Query API Reference

The `KnowledgeGraph` class in `loader.py` provides these methods (identical API regardless of backend):

| Method | Returns |
|---|---|
| `get_drug_identity(name)` | `{id, type, generic_name, brand_names, rxcui, ...}` or `None` |
| `get_interactions(name)` | `[{drug_id, drug_name, source, description}, ...]` |
| `get_co_reported(name)` | `[{drug_id, drug_name, report_count, source}, ...]` (sorted by report count) |
| `get_drug_reactions(name)` | `[{reaction, report_count, source}, ...]` (sorted by report count) |
| `get_ingredients(name)` | `[{ingredient, strength, source}, ...]` |
| `get_drugs_causing_reaction(term)` | `[{drug_id, generic_name, report_count, source}, ...]` — reverse lookup: which drugs cause this reaction |
| `get_ingredient_drugs(name)` | `[{drug_id, generic_name, brand_names, strength}, ...]` — reverse lookup: which drugs contain this ingredient |
| `get_label_reactions(name)` | `[{reaction, source}, ...]` |
| `get_disparity_analysis(name)` | `{confirmed_risks, emerging_signals, unconfirmed_warnings, disparity_score}` |
| `get_summary(name)` | Combined dict of all the above |

The `name` parameter accepts generic names (`ibuprofen`), brand names (`Advil`), or RxCUI codes (`206878`). All lookups go through the alias table first.

## Dynamic Expansion

When a user queries a drug not in the pre-built KG, the system dynamically builds
KG data using **two-phase progressive loading** (see `src/kg/dynamic_builder.py`):

### Phase 1 — Lightweight (~2-5s, synchronous)

- RxNorm resolution → Drug node
- NDC ingredient lookup → Ingredient nodes + edges
- FAERS top 10 reactions → Reaction nodes + edges

Result: basic drug profile available immediately for RAG and frontend.

### Phase 2 — Full build (~20-60s, background thread)

- Full FAERS co-reported drugs (50 max)
- Label interaction edges (Gemini or regex)
- Label reaction warnings (for disparity analysis)

### Integration Points

1. `engine.py:_drug_is_known()` triggers `expand_drug_async()` when RxNorm confirms the drug
2. Phase 1 completes synchronously → basic KG data available for the current query
3. Phase 2 runs in a daemon thread → full data for subsequent queries
4. Frontend shows build status banners and auto-polls for completion

### Build Status

`get_build_status(drug_name)` returns one of:
`NOT_STARTED` → `PHASE1_RUNNING` → `PHASE1_COMPLETE` → `PHASE2_RUNNING` → `PHASE2_COMPLETE` (or `FAILED`)

## Graph Enrichment Benchmark

The `tests/test_enrichment.py` script provides a side-by-side comparison of retrieval quality with and without graph enrichment. It builds two sets of artifacts from the same openFDA data — one plain, one graph-enriched — and runs five multi-hop pharma queries against both, reporting which chunks are surfaced and how many "new discoveries" the enriched pipeline produces.

```bash
# Default (metformin)
python -m tests.test_enrichment

# Custom drug
python -m tests.test_enrichment --drug warfarin

# Explicit openFDA search + custom KG path
python -m tests.test_enrichment \
  --search 'openfda.generic_name:"aspirin"' \
  --kg-path data/kg/trupharma_kg.db
```

Requires a built KG database (run `python scripts/build_kg.py` first). Skips gracefully if the KG is unavailable.

## Example Queries

These queries can be entered in the **Safety Chat** sidebar (or passed to `run_rag_query()` programmatically). They exercise different parts of the KG and RAG pipeline.

### Drug interactions

- *"What are the drug interactions for ibuprofen?"*
- *"Can I take aspirin with warfarin?"*
- *"What drugs interact with metformin?"*

### Dosage and warnings

- *"What is the recommended dosage for acetaminophen and are there any warnings?"*
- *"What safety warnings exist for caffeine-containing products?"*
- *"Are there any boxed warnings for lisinopril?"*

### Adverse reactions (FAERS)

- *"What are the most commonly reported side effects of omeprazole?"*
- *"What adverse reactions are associated with atorvastatin?"*
- *"How serious are adverse events reported for metoprolol?"*

### Active ingredients

- *"What are the active ingredients in Tylenol and what are the drug interactions?"*
- *"What drugs contain acetaminophen as an active ingredient?"*

### Overdosage and patient guidance

- *"I am taking aspirin daily. What should I know about overdosage and when to stop use?"*
- *"What happens if I take too much gabapentin?"*

### Multi-drug and comparative

- *"Compare the adverse reaction profiles of ibuprofen and naproxen."*
- *"What drugs are commonly co-reported with prednisone in adverse event reports?"*

### Out-of-scope (expected to return "Not enough evidence")

- *"What is the projected cost of antimicrobial resistance to GDP in 2050?"*
- *"Who won the 2024 presidential election?"*
- *"Explain the theory of general relativity."*

These are correctly rejected by the scope-validation gate because no token in the query resolves to a known drug.
