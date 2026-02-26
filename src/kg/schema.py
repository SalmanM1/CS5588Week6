"""
schema.py · TruPharma Knowledge Graph — Backward Compatibility Shim
====================================================================
Thin wrapper that delegates to :mod:`src.kg.backend`.

New code should use :class:`GraphBackend` directly::

    from src.kg.backend import create_backend
    backend = create_backend()
    backend.upsert_node(...)

These legacy helpers are kept so existing scripts continue to work
without modification during the migration period.
"""

from __future__ import annotations

from typing import Optional

from src.kg.backend import GraphBackend, SqliteBackend, create_backend  # noqa: F401


def init_db(path: str = "data/kg/trupharma_kg.db") -> SqliteBackend:
    """Create / open a SQLite KG and return a :class:`SqliteBackend`."""
    return SqliteBackend(path)


def count_nodes(backend: GraphBackend, node_type: Optional[str] = None) -> int:
    return backend.count_nodes(node_type)


def count_edges(backend: GraphBackend, edge_type: Optional[str] = None) -> int:
    return backend.count_edges(edge_type)


def rebuild_aliases(backend: GraphBackend) -> int:
    return backend.rebuild_aliases()
