"""
src.kg — TruPharma Knowledge Graph package.

Public API:
    GraphBackend      (backend protocol)
    SqliteBackend     (SQLite implementation)
    Neo4jBackend      (Neo4j implementation)
    create_backend    (factory)
    KnowledgeGraph    (read-only query API)
    load_kg           (cached loader with graceful degradation)
    expand_drug_async (dynamic KG expansion — async)
    expand_drug_phase1(dynamic KG expansion — Phase 1 only)
    get_build_status  (poll dynamic build progress)
"""

from src.kg.backend import (
    GraphBackend,
    SqliteBackend,
    Neo4jBackend,
    create_backend,
)
from src.kg.loader import KnowledgeGraph, load_kg
from src.kg.dynamic_builder import (
    expand_drug_async,
    expand_drug_phase1,
    get_build_status,
)

__all__ = [
    "GraphBackend",
    "SqliteBackend",
    "Neo4jBackend",
    "create_backend",
    "KnowledgeGraph",
    "load_kg",
    "expand_drug_async",
    "expand_drug_phase1",
    "get_build_status",
]

