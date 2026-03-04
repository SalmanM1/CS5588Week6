"""
test_neo4j_backend.py · Integration Tests for Neo4j Backend
=============================================================
Tests Neo4j-specific backend functionality including capacity usage
monitoring and migration verification.

These tests require a running Neo4j instance or are skipped if unavailable.

Usage:
    python -m pytest tests/test_neo4j_backend.py -v
    NEO4J_URI=bolt://localhost:7687 python -m pytest tests/test_neo4j_backend.py -v
"""

import os
import sys
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def _neo4j_available() -> bool:
    """Check if Neo4j is available for integration tests."""
    return bool(os.environ.get("NEO4J_URI"))


@unittest.skipUnless(_neo4j_available(), "NEO4J_URI not set — skipping Neo4j tests")
class TestNeo4jBackend(unittest.TestCase):
    """Integration tests for Neo4jBackend."""

    @classmethod
    def setUpClass(cls):
        from src.kg.backend import create_backend
        cls.backend = create_backend("neo4j")

    @classmethod
    def tearDownClass(cls):
        cls.backend.close()

    def test_upsert_and_read_node(self):
        """Nodes should be creatable and readable."""
        self.backend.upsert_node("test:123", "Drug", {
            "generic_name": "testdrug",
            "brand_names": ["TestBrand"],
        })
        self.backend.commit()

        node = self.backend.get_node("test:123")
        self.assertIsNotNone(node)
        self.assertEqual(node["type"], "Drug")
        self.assertEqual(node["generic_name"], "testdrug")

    def test_upsert_and_read_edge(self):
        """Edges should be creatable and readable."""
        self.backend.upsert_node("test:src", "Drug", {"generic_name": "srcDrug"})
        self.backend.upsert_node("test:dst", "Drug", {"generic_name": "dstDrug"})
        self.backend.upsert_edge("test:src", "test:dst", "INTERACTS_WITH", {
            "source": "test",
        })
        self.backend.commit()

        edges = self.backend.get_edges("test:src", "INTERACTS_WITH", "outgoing")
        self.assertTrue(any(e["dst"] == "test:dst" for e in edges))

    def test_capacity_usage(self):
        """get_capacity_usage() should return valid usage data."""
        usage = self.backend.get_capacity_usage()

        self.assertIn("nodes", usage)
        self.assertIn("edges", usage)
        self.assertIn("node_limit", usage)
        self.assertIn("edge_limit", usage)
        self.assertIn("node_pct", usage)
        self.assertIn("edge_pct", usage)
        self.assertIn("within_limits", usage)

        self.assertEqual(usage["node_limit"], 200_000)
        self.assertEqual(usage["edge_limit"], 400_000)
        self.assertIsInstance(usage["within_limits"], bool)
        self.assertGreaterEqual(usage["node_pct"], 0)
        self.assertGreaterEqual(usage["edge_pct"], 0)

    def test_count_nodes(self):
        """count_nodes() should return a non-negative integer."""
        count = self.backend.count_nodes()
        self.assertIsInstance(count, int)
        self.assertGreaterEqual(count, 0)

    def test_count_edges(self):
        """count_edges() should return a non-negative integer."""
        count = self.backend.count_edges()
        self.assertIsInstance(count, int)
        self.assertGreaterEqual(count, 0)

    def test_count_edges_by_type(self):
        """count_edges(type) should return a non-negative integer."""
        count = self.backend.count_edges("INTERACTS_WITH")
        self.assertIsInstance(count, int)
        self.assertGreaterEqual(count, 0)


class TestSqliteBackendCapacity(unittest.TestCase):
    """Verify SqliteBackend doesn't have get_capacity_usage (not needed)."""

    def test_sqlite_no_capacity(self):
        """SqliteBackend should NOT have get_capacity_usage()."""
        from src.kg.backend import SqliteBackend
        self.assertFalse(hasattr(SqliteBackend, "get_capacity_usage"))


if __name__ == "__main__":
    unittest.main()
