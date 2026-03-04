#!/usr/bin/env python3
"""
test_enrichment.py · Benchmark: Plain vs Graph-Enriched Retrieval
==================================================================
Runs 5 multi-hop pharma queries against two artifact sets built from
the same openFDA data — one with plain chunk text, one with graph-
enriched text — and prints a side-by-side comparison of the top-5
retrieved chunks.

Usage:
    python -m tests.test_enrichment
    python -m tests.test_enrichment --drug metformin --search 'openfda.generic_name:"metformin"'

Requires a built KG database at data/kg/trupharma_kg.db (or NEO4J_URI).
Skips gracefully if the KG is unavailable.
"""

import argparse
import os
import sys
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.ingestion.openfda_client import (
    build_artifacts,
    build_openfda_query,
    tokenize,
)

_DEFAULT_KG_PATH = str(_PROJECT_ROOT / "data" / "kg" / "trupharma_kg.db")

BENCHMARK_QUERIES = [
    "What proteins are targeted by drugs that treat Type 2 Diabetes?",
    "Which Metformin interactions are flagged in FAERS but not on the label?",
    "What adverse reactions are shared between Metformin and Warfarin?",
    "What are the active ingredients in drugs that cause lactic acidosis?",
    "Which drugs co-reported with Aspirin have cardiac reactions?",
]


# ── Retrieval helpers (mirror engine.py logic) ────────────────

def _embed_query(
    query: str,
    embedder_type: str,
    embedder_model: Optional[str],
    vectorizer: Any,
) -> Optional[np.ndarray]:
    """Embed a query string using the same method as the index."""
    if embedder_type == "sentence_transformers":
        try:
            from src.ingestion.openfda_client import _get_st_model
        except ImportError:
            return None
        name = embedder_model or "sentence-transformers/all-MiniLM-L6-v2"
        return _get_st_model(name).encode(
            [query], convert_to_numpy=True, normalize_embeddings=True,
        )
    if embedder_type == "tfidf" and vectorizer is not None:
        from sklearn.preprocessing import normalize as sk_normalize
        return sk_normalize(vectorizer.transform([query])).toarray().astype(np.float32)
    return None


def _dense(
    query: str, index: Any, corpus: list,
    e_type: str, e_model: Optional[str], vec: Any, k: int = 15,
) -> List[Tuple[float, Any]]:
    if index is None or not corpus:
        return []
    qv = _embed_query(query, e_type, e_model, vec)
    if qv is None:
        return []
    n = min(k, index.ntotal)
    scores, idxs = index.search(qv.astype(np.float32), n)
    return [
        (float(s), corpus[int(i)])
        for s, i in zip(scores[0], idxs[0])
        if int(i) >= 0
    ]


def _sparse(
    query: str, bm25: Any, corpus: list, k: int = 15,
) -> List[Tuple[float, Any]]:
    if bm25 is None or not corpus:
        return []
    scores = bm25.get_scores(tokenize(query))
    top = np.argsort(scores)[::-1][:k]
    return [(float(scores[i]), corpus[int(i)]) for i in top]


def _fuse(
    dense_res: list, sparse_res: list, alpha: float = 0.5, k: int = 15,
) -> List[Tuple[float, Any]]:
    cid = lambda it: getattr(it, "chunk_id", str(it))
    dr = {cid(it): r for r, (_, it) in enumerate(dense_res, 1)}
    sr = {cid(it): r for r, (_, it) in enumerate(sparse_res, 1)}
    bucket: Dict[str, Any] = {}
    for _, it in list(dense_res) + list(sparse_res):
        bucket.setdefault(cid(it), it)
    fused = []
    for key, obj in bucket.items():
        d = dr.get(key, len(dense_res) + 1)
        s = sr.get(key, len(sparse_res) + 1)
        fused.append((alpha / d + (1 - alpha) / s, obj))
    fused.sort(key=lambda x: x[0], reverse=True)
    return fused[:k]


def _retrieve_top5(
    query: str, arts: Dict[str, Any],
) -> List[Tuple[str, float]]:
    """Run hybrid retrieval and return [(chunk_id, score), ...]."""
    corpus = arts["record_chunks"]
    index = arts["faiss_A"]
    bm25 = arts["bm25_A"]
    emb = (arts.get("manifest", {}).get("embedder") or {})
    e_type = emb.get("type", "none")
    e_model = emb.get("model")
    vec = arts.get("vectorizer")

    pool = 20
    d = _dense(query, index, corpus, e_type, e_model, vec, pool)
    s = _sparse(query, bm25, corpus, pool)
    fused = _fuse(d, s, 0.5, 5)
    return [(it.chunk_id, round(score, 4)) for score, it in fused]


# ── Display helpers ───────────────────────────────────────────

def _print_comparison(
    query: str,
    plain_results: List[Tuple[str, float]],
    enriched_results: List[Tuple[str, float]],
) -> int:
    """Print side-by-side results. Returns count of new discoveries."""
    plain_ids = {cid for cid, _ in plain_results}
    enriched_ids = {cid for cid, _ in enriched_results}
    new_discoveries = enriched_ids - plain_ids

    print(f"\n{'='*80}")
    print(f"QUERY: {query}")
    print(f"{'='*80}")

    header = f"{'Rank':<5} {'Plain (chunk_id)':<38} {'Score':<8} {'Enriched (chunk_id)':<38} {'Score':<8} {'New?'}"
    print(header)
    print("-" * len(header))

    max_rows = max(len(plain_results), len(enriched_results))
    for i in range(max_rows):
        p_id = plain_results[i][0] if i < len(plain_results) else ""
        p_sc = f"{plain_results[i][1]:.4f}" if i < len(plain_results) else ""
        e_id = enriched_results[i][0] if i < len(enriched_results) else ""
        e_sc = f"{enriched_results[i][1]:.4f}" if i < len(enriched_results) else ""
        flag = " ** NEW" if e_id in new_discoveries else ""

        p_id_short = (p_id[:35] + "...") if len(p_id) > 38 else p_id
        e_id_short = (e_id[:35] + "...") if len(e_id) > 38 else e_id
        print(f"{i+1:<5} {p_id_short:<38} {p_sc:<8} {e_id_short:<38} {e_sc:<8}{flag}")

    if new_discoveries:
        print(f"\n  >> {len(new_discoveries)} new discovery(ies) from graph enrichment:")
        for cid in sorted(new_discoveries):
            print(f"     + {cid}")
    else:
        print("\n  >> No new discoveries (same chunk IDs in both)")

    return len(new_discoveries)


# ── Main benchmark ────────────────────────────────────────────

def run_benchmark(
    api_search: str,
    kg_path: str = _DEFAULT_KG_PATH,
    queries: Optional[List[str]] = None,
) -> None:
    """Build plain + enriched artifacts and compare retrieval results."""
    queries = queries or BENCHMARK_QUERIES

    # Load KG
    from src.kg.loader import load_kg, KnowledgeGraph, _KG_LOADED
    from src.kg import backend as _backend_mod

    # Reset the cached singleton so we get a fresh load
    import src.kg.loader as _loader_mod
    _loader_mod._KG_LOADED = False
    _loader_mod._KG_INSTANCE = None

    kg = load_kg(kg_path)
    if kg is None:
        print(
            f"WARNING: KG not available at '{kg_path}' and NEO4J_URI not set.\n"
            f"Run `python scripts/build_kg.py` first to build the knowledge graph.\n"
            f"Skipping benchmark."
        )
        return

    print("=" * 80)
    print("  GRAPH ENRICHMENT BENCHMARK")
    print("=" * 80)
    print(f"  KG path:     {kg_path}")
    print(f"  API search:  {api_search}")
    print(f"  Queries:     {len(queries)}")
    print()

    # Build PLAIN artifacts (no KG)
    print("[1/2] Building PLAIN artifacts (no graph enrichment)...")
    plain_arts = build_artifacts(
        api_search=api_search,
        save=False,
        verbose=True,
        use_st=False,
        kg=None,
    )
    n_plain = len(plain_arts["record_chunks"])

    # Build ENRICHED artifacts (with KG)
    print("\n[2/2] Building ENRICHED artifacts (with graph enrichment)...")
    enriched_arts = build_artifacts(
        api_search=api_search,
        save=False,
        verbose=True,
        use_st=False,
        kg=kg,
    )
    n_enriched = sum(
        1 for c in enriched_arts["record_chunks"] if c.graph_enriched
    )

    print(f"\nPlain chunks: {n_plain}  |  Enriched: {n_enriched}/{n_plain}")
    print("\nRunning retrieval comparison...\n")

    total_discoveries = 0
    for query in queries:
        plain_top5 = _retrieve_top5(query, plain_arts)
        enriched_top5 = _retrieve_top5(query, enriched_arts)
        total_discoveries += _print_comparison(query, plain_top5, enriched_top5)

    print(f"\n{'='*80}")
    print(f"  SUMMARY: {total_discoveries} total new discoveries across {len(queries)} queries")
    print(f"{'='*80}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark plain vs graph-enriched retrieval",
    )
    parser.add_argument(
        "--drug",
        default="metformin",
        help="Drug name for openFDA search (default: metformin)",
    )
    parser.add_argument(
        "--search",
        default=None,
        help="Explicit openFDA search query (overrides --drug)",
    )
    parser.add_argument(
        "--kg-path",
        default=_DEFAULT_KG_PATH,
        help=f"Path to KG SQLite database (default: {_DEFAULT_KG_PATH})",
    )
    args = parser.parse_args()

    api_search = args.search or f'openfda.generic_name:"{args.drug}"'
    run_benchmark(api_search=api_search, kg_path=args.kg_path)


if __name__ == "__main__":
    main()
