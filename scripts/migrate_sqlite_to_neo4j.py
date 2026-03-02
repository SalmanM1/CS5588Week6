#!/usr/bin/env python3
"""
migrate_sqlite_to_neo4j.py · One-Time SQLite → Neo4j Migration
================================================================
Reads all nodes and edges from the TruPharma SQLite KG database and
writes them to a Neo4j instance using the backend abstraction layer.

Usage:
    python scripts/migrate_sqlite_to_neo4j.py
    python scripts/migrate_sqlite_to_neo4j.py --sqlite data/kg/trupharma_kg.db

Prerequisites:
    - NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD environment variables set
      (or a .env file loaded beforehand)
    - The SQLite database must exist at the specified path
"""

import argparse
import json
import os
import sqlite3
import sys
import time

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.kg.backend import create_backend


def _parse_props(raw: str) -> dict:
    """Parse a JSON props string from the SQLite database."""
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def main():
    parser = argparse.ArgumentParser(
        description="Migrate TruPharma KG from SQLite to Neo4j"
    )
    parser.add_argument(
        "--sqlite", "-s",
        default="data/kg/trupharma_kg.db",
        help="Path to the SQLite database (default: data/kg/trupharma_kg.db)",
    )
    parser.add_argument(
        "--neo4j-uri",
        default=None,
        help="Neo4j connection URI (default: from NEO4J_URI env var)",
    )
    parser.add_argument(
        "--neo4j-user",
        default=None,
        help="Neo4j username (default: from NEO4J_USER env var)",
    )
    parser.add_argument(
        "--neo4j-password",
        default=None,
        help="Neo4j password (default: from NEO4J_PASSWORD env var)",
    )
    parser.add_argument(
        "--neo4j-database",
        default="neo4j",
        help="Neo4j database name (default: neo4j)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count nodes/edges without writing to Neo4j",
    )
    args = parser.parse_args()

    # ── Validate source ──────────────────────────────────────────
    if not os.path.exists(args.sqlite):
        print(f"ERROR: SQLite database not found: {args.sqlite}")
        sys.exit(1)

    # ── Validate Neo4j env vars ──────────────────────────────────
    neo4j_uri = args.neo4j_uri or os.environ.get("NEO4J_URI")
    if not neo4j_uri and not args.dry_run:
        print("ERROR: NEO4J_URI environment variable not set.")
        print("Set it or pass --neo4j-uri, or use --dry-run to preview.")
        sys.exit(1)

    # ── Connect to SQLite ────────────────────────────────────────
    print("=" * 60)
    print("  TruPharma KG Migration: SQLite → Neo4j")
    print("=" * 60)
    print(f"  Source: {args.sqlite}")
    if not args.dry_run:
        print(f"  Target: {neo4j_uri}")
    else:
        print("  Mode:   DRY RUN (no writes)")
    print()

    conn = sqlite3.connect(args.sqlite)

    # ── Count source data ────────────────────────────────────────
    node_count = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    edge_count = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]

    # Count by type
    type_counts = conn.execute(
        "SELECT type, COUNT(*) FROM nodes GROUP BY type ORDER BY COUNT(*) DESC"
    ).fetchall()
    edge_type_counts = conn.execute(
        "SELECT type, COUNT(*) FROM edges GROUP BY type ORDER BY COUNT(*) DESC"
    ).fetchall()

    print(f"  Source nodes: {node_count:,}")
    for ntype, cnt in type_counts:
        print(f"    - {ntype}: {cnt:,}")
    print(f"  Source edges: {edge_count:,}")
    for etype, cnt in edge_type_counts:
        print(f"    - {etype}: {cnt:,}")
    print()

    if args.dry_run:
        print("  DRY RUN complete. No data was written.")
        conn.close()
        return

    # ── Connect to Neo4j ─────────────────────────────────────────
    print("[Step 1] Connecting to Neo4j...")
    t0 = time.time()
    neo4j = create_backend(
        "neo4j",
        neo4j_uri=args.neo4j_uri,
        neo4j_user=args.neo4j_user,
        neo4j_password=args.neo4j_password,
        neo4j_database=args.neo4j_database,
    )
    print(f"  Connected in {time.time() - t0:.1f}s\n")

    # ── Migrate nodes ────────────────────────────────────────────
    print("[Step 2] Migrating nodes...")
    t1 = time.time()
    rows = conn.execute("SELECT id, type, props FROM nodes").fetchall()
    for i, (node_id, node_type, props_json) in enumerate(rows):
        props = _parse_props(props_json)
        neo4j.upsert_node(node_id, node_type, props)
        if (i + 1) % 500 == 0:
            neo4j.commit()
            print(f"  Migrated {i + 1:,}/{node_count:,} nodes...")
    neo4j.commit()
    print(f"  → {node_count:,} nodes migrated in {time.time() - t1:.1f}s\n")

    # ── Migrate edges ────────────────────────────────────────────
    print("[Step 3] Migrating edges...")
    t2 = time.time()
    rows = conn.execute("SELECT src, dst, type, props FROM edges").fetchall()
    for i, (src, dst, edge_type, props_json) in enumerate(rows):
        props = _parse_props(props_json)
        neo4j.upsert_edge(src, dst, edge_type, props)
        if (i + 1) % 500 == 0:
            neo4j.commit()
            print(f"  Migrated {i + 1:,}/{edge_count:,} edges...")
    neo4j.commit()
    print(f"  → {edge_count:,} edges migrated in {time.time() - t2:.1f}s\n")

    # ── Rebuild aliases ──────────────────────────────────────────
    print("[Step 4] Rebuilding alias table in Neo4j...")
    alias_count = neo4j.rebuild_aliases()
    print(f"  → {alias_count} aliases indexed\n")

    # ── Verify ───────────────────────────────────────────────────
    print("[Step 5] Verifying migration integrity...")
    neo4j_nodes = neo4j.count_nodes()
    neo4j_edges = neo4j.count_edges()

    print(f"  SQLite nodes: {node_count:,}  |  Neo4j nodes: {neo4j_nodes:,}")
    print(f"  SQLite edges: {edge_count:,}  |  Neo4j edges: {neo4j_edges:,}")

    if neo4j_nodes == node_count and neo4j_edges == edge_count:
        print("  ✅ Migration integrity check PASSED\n")
    else:
        print("  ⚠️  Counts differ — this may be expected if Neo4j had existing data")
        print("      (MERGE semantics deduplicate overlapping nodes/edges)\n")

    # ── Capacity check ───────────────────────────────────────────
    if hasattr(neo4j, "get_capacity_usage"):
        usage = neo4j.get_capacity_usage()
        print("[Step 6] Neo4j Aura capacity usage:")
        print(f"  Nodes: {usage['nodes']:,} / {usage['node_limit']:,} ({usage['node_pct']:.1f}%)")
        print(f"  Edges: {usage['edges']:,} / {usage['edge_limit']:,} ({usage['edge_pct']:.1f}%)")
        print(f"  Within limits: {'✅ Yes' if usage['within_limits'] else '❌ No'}\n")

    # ── Cleanup ──────────────────────────────────────────────────
    neo4j.close()
    conn.close()

    elapsed = time.time() - t0
    print("=" * 60)
    print("  MIGRATION COMPLETE")
    print("=" * 60)
    print(f"  Elapsed: {elapsed:.1f}s")
    print(f"  Nodes:   {neo4j_nodes:,}")
    print(f"  Edges:   {neo4j_edges:,}")
    print(f"  Aliases: {alias_count}")
    print("=" * 60)


if __name__ == "__main__":
    main()
