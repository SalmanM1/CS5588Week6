#!/usr/bin/env python3
"""
build_kg.py · TruPharma Knowledge Graph Build Script
======================================================
Orchestrates the KG build pipeline:
    1. RxNorm  → Drug nodes
    2. NDC     → Ingredient nodes + edges
    3. Labels  → INTERACTS_WITH edges
    4. FAERS   → CO_REPORTED_WITH + DRUG_CAUSES_REACTION edges
    5. Labels  → LABEL_WARNS_REACTION edges (disparity)

Usage:
    python scripts/build_kg.py
    python scripts/build_kg.py --max-drugs 50
    python scripts/build_kg.py --backend neo4j --neo4j-uri bolt://localhost:7687
    python scripts/build_kg.py --output data/kg/trupharma_kg.db --max-drugs 200

Run from the project root directory.
"""

import argparse
import os
import sys
import time

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.kg.backend import create_backend
from src.kg.builders.rxnorm_nodes import build_drug_nodes
from src.kg.builders.ndc_edges import build_ndc_edges
from src.kg.builders.label_edges import build_label_interaction_edges
from src.kg.builders.faers_edges import build_faers_edges
from src.kg.builders.label_reaction_edges import build_label_reaction_edges


def main():
    parser = argparse.ArgumentParser(
        description="Build the TruPharma Knowledge Graph"
    )
    parser.add_argument(
        "--output", "-o",
        default="data/kg/trupharma_kg.db",
        help="Output SQLite database path (default: data/kg/trupharma_kg.db)",
    )
    parser.add_argument(
        "--max-drugs", "-n",
        type=int,
        default=200,
        help="Maximum number of drugs in the seed list (default: 200)",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.2,
        help="Sleep between API calls in seconds (default: 0.2)",
    )
    parser.add_argument(
        "--skip-ndc",
        action="store_true",
        help="Skip NDC edge building",
    )
    parser.add_argument(
        "--skip-labels",
        action="store_true",
        help="Skip Label interaction edge building",
    )
    parser.add_argument(
        "--skip-faers",
        action="store_true",
        help="Skip FAERS edge building",
    )
    parser.add_argument(
        "--gemini-key",
        default=None,
        help="Gemini API key for interaction extraction (or set GEMINI_API_KEY env var)",
    )
    parser.add_argument(
        "--skip-label-reactions",
        action="store_true",
        help="Skip Label reaction edge building (disparity analysis)",
    )

    # ── Backend selection ──────────────────────────────────────
    parser.add_argument(
        "--backend",
        choices=["sqlite", "neo4j"],
        default=None,
        help="Graph backend: 'sqlite' (default) or 'neo4j'. "
             "Auto-detects from NEO4J_URI env var when omitted.",
    )
    parser.add_argument(
        "--neo4j-uri",
        default=None,
        help="Neo4j connection URI (or set NEO4J_URI env var)",
    )
    parser.add_argument(
        "--neo4j-user",
        default=None,
        help="Neo4j username (or set NEO4J_USER env var, default: neo4j)",
    )
    parser.add_argument(
        "--neo4j-password",
        default=None,
        help="Neo4j password (or set NEO4J_PASSWORD env var)",
    )
    parser.add_argument(
        "--neo4j-database",
        default="neo4j",
        help="Neo4j database name (default: neo4j)",
    )

    args = parser.parse_args()

    gemini_key = args.gemini_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")

    # ── Resolve backend kind ──────────────────────────────────
    backend_kind = args.backend
    if backend_kind is None:
        if args.neo4j_uri or os.environ.get("NEO4J_URI"):
            backend_kind = "neo4j"
        else:
            backend_kind = "sqlite"

    print("=" * 60)
    print("  TruPharma Knowledge Graph Builder")
    print("=" * 60)
    print(f"  Backend:   {backend_kind}")
    if backend_kind == "sqlite":
        print(f"  Output:    {args.output}")
    else:
        uri = args.neo4j_uri or os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        print(f"  Neo4j URI: {uri}")
    print(f"  Max drugs: {args.max_drugs}")
    print(f"  Sleep:     {args.sleep}s")
    print(f"  Gemini:    {'available' if gemini_key else 'not configured (regex fallback)'}")
    print("=" * 60)
    print()

    t0 = time.time()

    # ── Step 0: Initialize backend ─────────────────────────────
    print(f"[Step 0] Initializing {backend_kind} backend...")
    backend = create_backend(
        backend_kind,
        sqlite_path=args.output,
        neo4j_uri=args.neo4j_uri,
        neo4j_user=args.neo4j_user,
        neo4j_password=args.neo4j_password,
        neo4j_database=args.neo4j_database,
    )
    print(f"  Backend ready.\n")

    # ── Step 1: Drug nodes (RxNorm) ────────────────────────────
    print("[Step 1] Building Drug nodes (openFDA + RxNorm)...")
    drugs = build_drug_nodes(backend, max_drugs=args.max_drugs, sleep_s=args.sleep)
    print(f"  → {backend.count_nodes('Drug')} Drug nodes in DB\n")

    if not drugs:
        print("ERROR: No drugs created. Cannot proceed. Check API connectivity.")
        backend.close()
        sys.exit(1)

    # ── Step 2: NDC edges ──────────────────────────────────────
    if not args.skip_ndc:
        print("[Step 2] Building NDC edges (ingredients + products)...")
        build_ndc_edges(backend, drugs, sleep_s=args.sleep)
        print(f"  → {backend.count_nodes('Ingredient')} Ingredient nodes")
        print(f"  → {backend.count_edges('HAS_ACTIVE_INGREDIENT')} HAS_ACTIVE_INGREDIENT edges")
        print(f"  → {backend.count_edges('HAS_PRODUCT')} HAS_PRODUCT edges\n")
    else:
        print("[Step 2] Skipping NDC edges (--skip-ndc)\n")

    # ── Step 3: Label interaction edges ────────────────────────
    if not args.skip_labels:
        print("[Step 3] Building Label interaction edges...")
        build_label_interaction_edges(backend, drugs, sleep_s=args.sleep, gemini_api_key=gemini_key)
        print(f"  → {backend.count_edges('INTERACTS_WITH')} INTERACTS_WITH edges\n")
    else:
        print("[Step 3] Skipping Label edges (--skip-labels)\n")

    # ── Step 4: FAERS edges ────────────────────────────────────
    if not args.skip_faers:
        print("[Step 4] Building FAERS edges (co-reported + reactions)...")
        build_faers_edges(backend, drugs, sleep_s=args.sleep)
        print(f"  → {backend.count_nodes('Reaction')} Reaction nodes")
        print(f"  → {backend.count_edges('CO_REPORTED_WITH')} CO_REPORTED_WITH edges")
        print(f"  → {backend.count_edges('DRUG_CAUSES_REACTION')} DRUG_CAUSES_REACTION edges\n")
    else:
        print("[Step 4] Skipping FAERS edges (--skip-faers)\n")

    # ── Step 5: Label reaction edges (disparity) ──────────────
    if not args.skip_label_reactions:
        print("[Step 5] Building Label reaction edges (for disparity analysis)...")
        build_label_reaction_edges(backend, drugs, sleep_s=args.sleep)
        print(f"  → {backend.count_edges('LABEL_WARNS_REACTION')} LABEL_WARNS_REACTION edges\n")
    else:
        print("[Step 5] Skipping Label reaction edges (--skip-label-reactions)\n")

    # ── Final: Rebuild alias table (includes FAERS stubs) ─────
    print("[Final] Rebuilding alias lookup table...")
    alias_count = backend.rebuild_aliases()
    print(f"  → {alias_count} aliases indexed\n")

    # ── Summary ────────────────────────────────────────────────
    elapsed = time.time() - t0
    total_nodes = backend.count_nodes()
    total_edges = backend.count_edges()
    backend.close()

    print("=" * 60)
    print("  BUILD COMPLETE")
    print("=" * 60)
    print(f"  Backend:     {backend_kind}")
    print(f"  Total nodes: {total_nodes}")
    print(f"  Total edges: {total_edges}")
    if backend_kind == "sqlite":
        print(f"  Output file: {args.output}")
        file_size = os.path.getsize(args.output) if os.path.exists(args.output) else 0
        print(f"  File size:   {file_size / 1024:.1f} KB")
    print(f"  Elapsed:     {elapsed:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
