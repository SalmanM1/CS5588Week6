# TruPharma Knowledge Graph Upgrade

> Comprehensive upgrade of the KG subsystem: many-to-many relationships,
> dynamic on-demand expansion (progressive loading), Neo4j Aura Free migration,
> and enhanced LLM graph context.

---

## Table of Contents

1. [Architecture Decisions](#architecture-decisions)
2. [Data Model — Before & After](#data-model)
3. [Many-to-Many Relationships](#many-to-many-relationships)
4. [Neo4j Aura Free Setup](#neo4j-aura-free-setup)
5. [Migration Runbook (SQLite → Neo4j)](#migration-runbook)
6. [Dynamic Builder API](#dynamic-builder-api)
7. [Progressive Loading UI](#progressive-loading-ui)
8. [LLM Data Preparation](#llm-data-preparation)
9. [Environment Variable Reference](#environment-variable-reference)

---

## Architecture Decisions

### Why Neo4j Aura Free?

| Criteria | SQLite | Neo4j Aura Free |
|----------|--------|-----------------|
| **Graph traversal** | Manual SQL JOINs | Native Cypher queries |
| **Scalability** | Single file, single node | Cloud-hosted, multi-tenant |
| **Cost** | Free | Free (200K nodes, 400K edges) |
| **Many-to-many** | Supported via junction tables | Native relationship model |
| **Deployment** | Zero config, local only | Managed cloud, auto-backup |
| **Concurrent access** | Limited (file locking) | Full ACID, multi-user |

**Decision:** Neo4j Aura Free provides a production-ready graph database at zero cost.
Our current KG (~9K nodes, ~18K edges) is well within the free tier limits.
The `create_backend()` factory auto-detects Neo4j when `NEO4J_URI` is set,
falling back to SQLite for local development.

### Why Progressive Loading?

The original architecture returned "Not enough evidence" when a drug wasn't in the
pre-built 200-drug seed list. This was a poor user experience for ~95%+ of drugs.

**Decision:** Two-phase progressive loading:
- **Phase 1 (2-5s, synchronous):** RxNorm → Drug node + NDC ingredients + top 10 FAERS reactions
- **Phase 2 (20-60s, background thread):** Full FAERS co-reported drugs + label interactions + label reaction warnings

This means the user sees basic drug data within seconds, and the full profile
builds transparently in the background.

---

## Data Model

### Node Types

| Type | Description | ID Format | Key Properties |
|------|-------------|-----------|----------------|
| **Drug** | Pharmaceutical compound | RxCUI or `generic_name.lower()` | `generic_name`, `brand_names`, `rxcui`, `confidence` |
| **Ingredient** | Active ingredient | `ingredient_name.lower()` | `name` |
| **Reaction** | Adverse event term (MedDRA) | `reaction:term.lower()` | `reactionmeddrapt` |
| **Product** | Commercial product (NDC) | `product:{drug_id}` | `drug_id`, `generic_name` |
| **DrugAlias** | Lookup alias for drug resolution | N/A | `alias`, `node_id` |

### Relationship Types

| Relationship | From → To | Source | Key Properties |
|-------------|-----------|--------|----------------|
| **HAS_ACTIVE_INGREDIENT** | Drug → Ingredient | NDC API | `strength`, `source` |
| **INTERACTS_WITH** | Drug → Drug | FDA Labels / Gemini | `source`, `description` |
| **CO_REPORTED_WITH** | Drug → Drug | FAERS | `report_count`, `source` |
| **DRUG_CAUSES_REACTION** | Drug → Reaction | FAERS | `report_count`, `source` |
| **LABEL_WARNS_REACTION** | Drug → Reaction | FDA Labels | `source` |
| **HAS_PRODUCT** | Drug → Product | NDC API | `dosage_forms`, `routes`, `manufacturer` |

### Many-to-Many Semantics

```
Drug A ──DRUG_CAUSES_REACTION──→ Reaction X ←──DRUG_CAUSES_REACTION── Drug B
Drug A ──HAS_ACTIVE_INGREDIENT──→ Ingredient Y ←──HAS_ACTIVE_INGREDIENT── Drug C
```

**Shared nodes** (Reactions, Ingredients) are correctly reused across drugs via
MERGE semantics (`INSERT ON CONFLICT UPDATE` in SQLite, `MERGE` in Neo4j).
The `get_drugs_causing_reaction()` method enables reverse lookups.

---

## Many-to-Many Relationships

### Changes Made

1. **`faers_edges.py`** — Removed redundant `node_exists()` guard before `upsert_node()`.
   The upsert already handles MERGE semantics, so shared Reaction nodes are correctly
   reused across drugs without the extra database round-trip.

2. **`loader.py`** — Added `get_drugs_causing_reaction(reaction_term)` method for
   reverse lookups (Reaction → all Drugs). This completes the many-to-many Drug↔Reaction
   query path, enabling queries like "which drugs cause headache?"

3. **Public API exports** (`faers_edges.py`):
   - `build_faers_search()` — construct a FAERS search clause
   - `fetch_top_reactions()` — top adverse reactions for a drug
   - `fetch_co_reported_drugs()` — top co-reported drugs from FAERS
   
   These are used by the `dynamic_builder.py` module for on-demand expansion.

---

## Neo4j Aura Free Setup

### Step-by-Step

1. **Create a free Neo4j Aura instance:**
   - Go to [console.neo4j.io](https://console.neo4j.io)
   - Sign up (GitHub/Google SSO supported)
   - Click "New Instance" → select "Free" tier
   - Region: choose closest to your deployment
   - Save the auto-generated password immediately

2. **Copy connection credentials to `.env`:**
   ```bash
   cp .env.example .env
   # Edit .env with your Aura credentials:
   # NEO4J_URI=neo4j+s://xxxxxxxx.databases.neo4j.io
   # NEO4J_USER=neo4j
   # NEO4J_PASSWORD=your-password-here
   # NEO4J_DATABASE=neo4j
   ```

3. **Migrate existing SQLite data:**
   ```bash
   python scripts/migrate_sqlite_to_neo4j.py
   ```

4. **Verify with capacity check:**
   ```python
   from src.kg.backend import create_backend
   backend = create_backend("neo4j")
   print(backend.get_capacity_usage())
   # Expected: ~9K nodes, ~18K edges → well within limits
   ```

### Aura Free Limits

| Resource | Limit | Current Usage |
|----------|-------|---------------|
| Nodes | 200,000 | ~9,000 (4.5%) |
| Relationships | 400,000 | ~18,000 (4.5%) |
| Storage | 256 MB | ~10 MB |

---

## Migration Runbook

### SQLite → Neo4j

```bash
# 1. Ensure Neo4j credentials are set
export NEO4J_URI="neo4j+s://xxx.databases.neo4j.io"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="your-password"

# 2. Dry run (preview what will be migrated)
python scripts/migrate_sqlite_to_neo4j.py --dry-run

# 3. Run migration
python scripts/migrate_sqlite_to_neo4j.py

# 4. Verify
python -c "
from src.kg.backend import create_backend
b = create_backend('neo4j')
print(f'Nodes: {b.count_nodes()}, Edges: {b.count_edges()}')
print(b.get_capacity_usage())
b.close()
"
```

The migration script:
- Reads all nodes and edges from SQLite
- Writes to Neo4j via `upsert_node()` / `upsert_edge()` (MERGE semantics)
- Rebuilds the alias table in Neo4j
- Validates node/edge counts match
- Reports Aura Free capacity usage

---

## Dynamic Builder API

### `src/kg/dynamic_builder.py`

#### `expand_drug_phase1(drug_name) → dict`

Lightweight synchronous expansion (~2-5 seconds):
- RxNorm resolution → Drug node
- NDC ingredient lookup → Ingredient nodes + edges
- FAERS top 10 reactions → Reaction nodes + edges

Returns: `{"node_id", "generic_name", "rxcui", "brand_names", "ingredients_added", "reactions_added", "elapsed_s"}`

#### `expand_drug_phase2(drug_name) → None`

Full build (synchronous, designed for background thread):
- Full FAERS co-reported drugs (50 max)
- Label interaction edges (Gemini AI or regex fallback)
- Label reaction warnings (for disparity analysis)

#### `expand_drug_async(drug_name) → dict`

Runs Phase 1 synchronously, kicks off Phase 2 in a daemon thread.
Returns Phase 1 result dict with `phase2_thread=True`.
Deduplicates: skips if a build is already in progress.

#### `get_build_status(drug_name) → str`

Returns current build phase:
- `NOT_STARTED` → `PHASE1_RUNNING` → `PHASE1_COMPLETE`
- → `PHASE2_RUNNING` → `PHASE2_COMPLETE`
- (or `FAILED` on error)

### CLI Usage

```bash
# Build KG for a single drug
python scripts/build_kg.py --drug "gabapentin"

# Build full KG (200 drugs)
python scripts/build_kg.py --max-drugs 200
```

---

## Progressive Loading UI

### Frontend Flow (`primary_demo.py`)

1. User queries an unknown drug
2. `_drug_is_known()` → RxNorm confirms drug → `expand_drug_async()` triggered
3. Phase 1 completes → basic KG data available immediately
4. Frontend shows info banner: "🔄 Building full drug profile..."
5. Auto-polls via `st.rerun()` every 5s (up to 5 times)
6. When Phase 2 completes: success banner "✅ Full drug profile built!"
7. "⏳ Partial KG Data" badge on KG visualization panel while incomplete

### Session State Keys

| Key | Type | Purpose |
|-----|------|---------|
| `kg_poll_count` | int | Tracks auto-poll iterations (max 5) |
| `result.kg_dynamic` | bool | Whether drug was dynamically built |
| `result.kg_build_status` | str | Current build phase |
| `result.kg_build_phase1_time` | float | Phase 1 elapsed seconds |

---

## LLM Data Preparation

### Enhanced `[GRAPH CONTEXT]` Block

The `graph_enrichment.py` module now produces richer context for LLM consumption:

```
[GRAPH CONTEXT]
Drug: metformin | RxCUI: 6809 | Also known as: Glucophage, Fortamet
Ingredients: metformin hydrochloride
Known interactions (12 total): warfarin, aspirin, lisinopril, ...
Adverse reactions (FAERS, 25 total): nausea, diarrhea, vomiting, ...
Co-reported drugs (18 total): insulin, sitagliptin, ...
Disparity score: 0.45 | Emerging signals: 8
Emerging risks (FAERS not on label): [EMERGING RISK] lactic acidosis, ...
[END GRAPH CONTEXT]
```

**Changes:**
- Added relationship counts (e.g., "Known interactions (12 total)")
- Added disparity score and emerging signal count
- Added `[END GRAPH CONTEXT]` delimiter for clearer LLM parsing
- Full relationship lists queried (counts are total), top 5 shown by name

---

## Environment Variable Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `NEO4J_URI` | No | — | Neo4j connection URI (auto-detects Neo4j backend) |
| `NEO4J_USER` | No | `neo4j` | Neo4j username |
| `NEO4J_PASSWORD` | No | — | Neo4j password |
| `NEO4J_DATABASE` | No | `neo4j` | Neo4j database name |
| `GEMINI_API_KEY` | No | — | Google Gemini API key for LLM features |
| `GOOGLE_API_KEY` | No | — | Fallback for Gemini API key |

See `.env.example` for a complete template.
