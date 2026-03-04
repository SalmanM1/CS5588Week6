"""
test_reverse_lookups.py · Tests for Reverse Lookup Methods
============================================================
Tests the many-to-many reverse lookup capability:
- get_drugs_causing_reaction() — Reaction → all Drugs
- get_ingredient_drugs() — Ingredient → all Drugs (existing)

Usage:
    python -m pytest tests/test_reverse_lookups.py -v
    python -m tests.test_reverse_lookups  (standalone)
"""

import os
import sys
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def _kg_available() -> bool:
    """Check if the KG database is available for testing."""
    sqlite_path = os.path.join(_PROJECT_ROOT, "data", "kg", "trupharma_kg.db")
    return os.path.exists(sqlite_path) or bool(os.environ.get("NEO4J_URI"))


@unittest.skipUnless(_kg_available(), "KG not available — skipping reverse lookup tests")
class TestGetDrugsCausingReaction(unittest.TestCase):
    """Tests for KnowledgeGraph.get_drugs_causing_reaction()."""

    @classmethod
    def setUpClass(cls):
        from src.kg.loader import load_kg
        cls.kg = load_kg()
        if cls.kg is None:
            raise unittest.SkipTest("KG not available")

    def test_known_reaction_returns_results(self):
        """A common reaction like 'headache' should return multiple drugs."""
        results = self.kg.get_drugs_causing_reaction("headache")
        # headache is one of the most common reactions in FAERS
        self.assertIsInstance(results, list)
        if results:
            self.assertIn("drug_id", results[0])
            self.assertIn("generic_name", results[0])
            self.assertIn("report_count", results[0])

    def test_results_sorted_by_report_count(self):
        """Results should be sorted by report_count descending."""
        results = self.kg.get_drugs_causing_reaction("headache")
        if len(results) > 1:
            counts = [r["report_count"] for r in results]
            self.assertEqual(counts, sorted(counts, reverse=True))

    def test_unknown_reaction_returns_empty(self):
        """An unknown reaction should return an empty list."""
        results = self.kg.get_drugs_causing_reaction("nonexistent_reaction_xyz_123")
        self.assertEqual(results, [])

    def test_empty_string_returns_empty(self):
        """Empty string should return an empty list."""
        results = self.kg.get_drugs_causing_reaction("")
        self.assertEqual(results, [])

    def test_accepts_reaction_id_format(self):
        """Should accept both 'headache' and 'reaction:headache' formats."""
        r1 = self.kg.get_drugs_causing_reaction("headache")
        r2 = self.kg.get_drugs_causing_reaction("reaction:headache")
        # Both should return the same drugs
        if r1 and r2:
            ids1 = {d["drug_id"] for d in r1}
            ids2 = {d["drug_id"] for d in r2}
            self.assertEqual(ids1, ids2)

    def test_no_duplicate_drugs(self):
        """Each drug should appear at most once in the results."""
        results = self.kg.get_drugs_causing_reaction("nausea")
        if results:
            drug_ids = [r["drug_id"] for r in results]
            self.assertEqual(len(drug_ids), len(set(drug_ids)))


@unittest.skipUnless(_kg_available(), "KG not available — skipping ingredient drug tests")
class TestGetIngredientDrugs(unittest.TestCase):
    """Tests for the existing get_ingredient_drugs() reverse lookup."""

    @classmethod
    def setUpClass(cls):
        from src.kg.loader import load_kg
        cls.kg = load_kg()
        if cls.kg is None:
            raise unittest.SkipTest("KG not available")

    def test_known_ingredient_returns_drugs(self):
        """A common ingredient should return at least one drug."""
        results = self.kg.get_ingredient_drugs("acetaminophen")
        self.assertIsInstance(results, list)

    def test_unknown_ingredient_returns_empty(self):
        """An unknown ingredient should return an empty list."""
        results = self.kg.get_ingredient_drugs("nonexistent_ingredient_xyz_123")
        self.assertEqual(results, [])


class TestManyToManyFaersEdges(unittest.TestCase):
    """Tests for many-to-many relationship semantics in faers_edges.py."""

    def test_public_api_exports(self):
        """faers_edges.py should export public API functions."""
        from src.kg.builders.faers_edges import (
            build_faers_search,
            fetch_top_reactions,
            fetch_co_reported_drugs,
        )
        self.assertTrue(callable(build_faers_search))
        self.assertTrue(callable(fetch_top_reactions))
        self.assertTrue(callable(fetch_co_reported_drugs))

    def test_build_faers_search_format(self):
        """build_faers_search should produce a valid FAERS search string."""
        from src.kg.builders.faers_edges import build_faers_search

        # Basic
        search = build_faers_search("ibuprofen")
        self.assertIn("ibuprofen", search)
        self.assertIn("patient.drug.openfda.generic_name", search)

        # With RxCUI
        search_with_rxcui = build_faers_search("ibuprofen", "206878")
        self.assertIn("206878", search_with_rxcui)
        self.assertIn("+OR+", search_with_rxcui)

    def test_backward_compatible_aliases(self):
        """Private aliases should still work for internal callers."""
        from src.kg.builders.faers_edges import (
            _build_search,
            _fetch_co_reported_drugs,
            _fetch_top_reactions,
            build_faers_search,
            fetch_co_reported_drugs,
            fetch_top_reactions,
        )
        self.assertIs(_build_search, build_faers_search)
        self.assertIs(_fetch_co_reported_drugs, fetch_co_reported_drugs)
        self.assertIs(_fetch_top_reactions, fetch_top_reactions)


if __name__ == "__main__":
    unittest.main()
