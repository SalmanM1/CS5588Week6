"""
src.kg — TruPharma Knowledge Graph package.

Public API:
    GraphBackend      (backend protocol)
    SqliteBackend     (SQLite implementation)
    Neo4jBackend      (Neo4j implementation)
    create_backend    (factory)
    KnowledgeGraph    (read-only query API)
    load_kg           (cached loader with graceful degradation)
"""

from src.kg.backend import (
    GraphBackend,
    SqliteBackend,
    Neo4jBackend,
    create_backend,
)
from src.kg.loader import KnowledgeGraph, load_kg

__all__ = [
    "GraphBackend",
    "SqliteBackend",
    "Neo4jBackend",
    "create_backend",
    "KnowledgeGraph",
    "load_kg",
]
