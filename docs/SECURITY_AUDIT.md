# TruPharma Security Audit

> Post-implementation security review of the Knowledge Graph upgrade.
> Covers credential management, API security, input validation, thread safety,
> data integrity, and dependency audit.

---

## 1. Neo4j Credential Management

### Current State

| Item | Status | Notes |
|------|--------|-------|
| `.env` in `.gitignore` | ✅ Pass | `.env` is listed in `.gitignore` |
| `.env.example` has no real secrets | ✅ Pass | Contains placeholder values only |
| Env vars over hardcoded secrets | ✅ Pass | All secrets read from `os.environ` |
| CLI args accept `--neo4j-password` | ⚠️ Note | Password may appear in process list |
| Streamlit Cloud secrets | ✅ Pass | `st.secrets` supported as alternative |

### Recommendations

1. **Prefer env vars over CLI args** for passwords in production.
2. **Rotate Neo4j password** if it was ever used in CLI commands.
3. **Use Streamlit secrets** (`~/.streamlit/secrets.toml`) for Streamlit Cloud deployments.
4. Consider adding **Neo4j role-based access control** — create a `trupharma_app` user with read-only access for the RAG pipeline, reserving write access for the build scripts.

---

## 2. API Security

### External API Calls

| API | Auth Required | Rate Limiting | TLS |
|-----|--------------|---------------|-----|
| openFDA Label API | No | Yes (40/min w/o key) | ✅ HTTPS |
| openFDA FAERS API | No | Yes (40/min w/o key) | ✅ HTTPS |
| RxNorm REST API | No | No formal limit | ✅ HTTPS |
| NDC API (openFDA) | No | Yes (40/min w/o key) | ✅ HTTPS |
| Gemini API | Yes (API key) | Yes (per-key quota) | ✅ HTTPS |

### Findings

- ✅ All HTTP calls use `urllib.request` with explicit TLS context via `certifi`.
- ✅ Gemini API key is passed via env var, not hardcoded.
- ⚠️ **No API key for openFDA** — rate-limited to 40 req/min per IP. Add `api_key` parameter for production.
- ✅ All API errors are caught and handled gracefully (empty dict returns, not crashes).

### Recommendation

- Register for a free openFDA API key to increase rate limits to 240/min.

---

## 3. Input Validation

### Drug Name Input

| Check | Status | Location |
|-------|--------|----------|
| Strip whitespace | ✅ | `_find_drug_id()`, `find_drug_node_id()` |
| Case normalization | ✅ | `.lower()` throughout |
| SQL injection prevention | ✅ | SQLite uses parameterized queries |
| Cypher injection prevention | ✅ | Neo4j uses `$param` parameters |
| Label validation | ✅ | `_validate_label()` regex in `backend.py` |
| Empty string handling | ✅ | Early returns for empty inputs |

### Reaction Term Input (new `get_drugs_causing_reaction`)

| Check | Status | Notes |
|-------|--------|-------|
| Empty string guard | ✅ | Returns `[]` immediately |
| Prefix normalization | ✅ | Handles both `"headache"` and `"reaction:headache"` |
| Node type validation | ✅ | Checks `node.get("type") == "Reaction"` |
| Deduplication | ✅ | `seen` set prevents duplicate results |

### Frontend

| Check | Status | Notes |
|-------|--------|-------|
| HTML injection in KG viz | ⚠️ | `_build_kg_network_html` uses `esc()` function |
| XSS in `st.markdown` | ⚠️ | Uses `unsafe_allow_html=True` with controlled templates |
| Query text in URLs | ✅ | Not passed to URLs directly |

### Recommendations

1. Audit all `unsafe_allow_html=True` calls — ensure user-controlled strings are escaped before insertion.
2. The `esc()` function in the vis.js HTML template is good but verify coverage.

---

## 4. Thread Safety (Dynamic Builder)

### Analysis

| Component | Thread-Safe | Mechanism |
|-----------|------------|-----------|
| `_active_builds` dict | ✅ | `threading.Lock()` (`_builds_lock`) |
| `_set_status()` | ✅ | Acquires `_builds_lock` |
| `get_build_status()` | ✅ | Acquires `_builds_lock` |
| Phase 2 background thread | ✅ | Daemon thread, own backend instance |
| SQLite writes | ⚠️ | SQLite file locking may block concurrent writes |
| Neo4j writes | ✅ | Neo4j handles concurrent transactions natively |
| Module-level `_dynamic_build_result` | ⚠️ | Global dict in `engine.py` — safe for single-threaded Streamlit |

### Notes

- The `_dynamic_build_result` global in `engine.py` is acceptable because Streamlit runs each user request sequentially.
- **If deploying behind a WSGI server with multiple workers**, each worker has its own process, so the global dict is isolated per-process.
- The dynamic builder creates a **new backend instance per phase**, avoiding shared connection state across threads.

### Recommendations

1. For multi-worker deployments, consider using a shared cache (Redis) for build status instead of in-process dict.
2. SQLite concurrent writes may cause `database is locked` errors if Phase 2 and a user query write simultaneously. Neo4j does not have this issue.

---

## 5. Data Integrity

### Migration Script (`migrate_sqlite_to_neo4j.py`)

| Check | Status |
|-------|--------|
| Source validation | ✅ — Checks file exists before proceeding |
| Count verification | ✅ — Compares source vs. target node/edge counts |
| MERGE semantics | ✅ — Upserts prevent duplicate nodes/edges |
| Alias rebuild | ✅ — Rebuilds aliases in Neo4j after migration |
| Error handling | ✅ — Graceful error messages |
| Dry run mode | ✅ — `--dry-run` flag previews without writing |

### MERGE Semantics (Node Upsert)

- **SQLite:** `INSERT OR REPLACE INTO nodes (id, type, props) VALUES (?, ?, ?)`
- **Neo4j:** `MERGE (n:{label} {id: $id}) SET n += $props`
- Both guarantee idempotent writes — running the migration twice produces the same result.

### Many-to-Many Integrity

- Shared Reaction nodes are now created via `upsert_node()` without the `node_exists()` guard.
- The upsert handles all cases (new node → INSERT, existing node → UPDATE).
- This ensures Drug A and Drug B can both link to the same Reaction X.

---

## 6. Dependency Audit

### `requirements.txt` Analysis

| Package | Pinning | Known Vulnerabilities | Notes |
|---------|---------|----------------------|-------|
| `streamlit` | Latest | None critical | Pin to `>=1.30` for stability |
| `neo4j>=5.0.0` | Floor only | None known | Consider `>=5.14` for latest fixes |
| `numpy` | Latest | None critical | Transitive dependency |
| `scikit-learn` | Latest | None critical | Used for embeddings |
| `faiss-cpu` | Latest | None critical | FAISS vector search |
| `rank-bm25` | Latest | None critical | Sparse retrieval |
| `google-generativeai` | Latest | None critical | Gemini SDK |
| `pandas` | Latest | None critical | Data processing |
| `reportlab` | Latest | None critical | PDF generation |
| `certifi` | Latest | None critical | TLS certificate bundle |

### Recommendations

1. **Pin major versions** in production: `streamlit>=1.30,<2.0`.
2. Run `pip audit` periodically to check for new CVEs.
3. Add a `requirements-dev.txt` for test dependencies (`pytest`, `pytest-mock`).

---

## Summary

| Area | Rating | Priority |
|------|--------|----------|
| Credential management | ✅ Good | — |
| API security | ✅ Good | Low — add openFDA API key |
| Input validation | ✅ Good | Low — audit `unsafe_allow_html` calls |
| Thread safety | ✅ Good | Low — consider Redis for multi-worker |
| Data integrity | ✅ Good | — |
| Dependencies | ⚠️ Acceptable | Medium — pin versions, add `pip audit` |

**Overall Assessment:** The codebase follows security best practices for a clinical intelligence application. 
No critical vulnerabilities identified. All recommended improvements are preventive hardening measures.

---

*Audit conducted: February 2026*
*Scope: KG upgrade (Phases 1–8) including dynamic builder, Neo4j migration, and frontend changes*
