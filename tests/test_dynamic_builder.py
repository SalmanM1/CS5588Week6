"""
test_dynamic_builder.py · Unit Tests for Dynamic KG Expansion
================================================================
Tests the two-phase progressive loading system in src/kg/dynamic_builder.py.

Usage:
    python -m pytest tests/test_dynamic_builder.py -v
    python -m tests.test_dynamic_builder  (standalone)
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


class TestBuildStatus(unittest.TestCase):
    """Tests for build status tracking."""

    def setUp(self):
        """Reset the build status state before each test."""
        from src.kg.dynamic_builder import _active_builds, _builds_lock
        with _builds_lock:
            _active_builds.clear()

    def test_get_build_status_not_started(self):
        from src.kg.dynamic_builder import get_build_status, STATUS_NOT_STARTED
        self.assertEqual(get_build_status("aspirin"), STATUS_NOT_STARTED)

    def test_set_and_get_status(self):
        from src.kg.dynamic_builder import (
            _set_status, get_build_status,
            STATUS_PHASE1_RUNNING, STATUS_PHASE1_COMPLETE,
        )
        _set_status("aspirin", STATUS_PHASE1_RUNNING)
        self.assertEqual(get_build_status("aspirin"), STATUS_PHASE1_RUNNING)

        _set_status("aspirin", STATUS_PHASE1_COMPLETE, node_id="12345")
        self.assertEqual(get_build_status("aspirin"), STATUS_PHASE1_COMPLETE)

    def test_case_insensitive_lookup(self):
        from src.kg.dynamic_builder import get_build_status, STATUS_NOT_STARTED
        self.assertEqual(get_build_status("Aspirin"), STATUS_NOT_STARTED)
        self.assertEqual(get_build_status("ASPIRIN"), STATUS_NOT_STARTED)

    def test_empty_string(self):
        from src.kg.dynamic_builder import get_build_status, STATUS_NOT_STARTED
        self.assertEqual(get_build_status(""), STATUS_NOT_STARTED)


class TestExpandDrugPhase1(unittest.TestCase):
    """Tests for Phase 1 expansion (mocked external APIs)."""

    def setUp(self):
        from src.kg.dynamic_builder import _active_builds, _builds_lock
        with _builds_lock:
            _active_builds.clear()

    @patch("src.kg.dynamic_builder._get_backend")
    @patch("src.kg.builders.faers_edges.fetch_top_reactions")
    @patch("src.kg.builders.faers_edges.build_faers_search")
    def test_phase1_with_valid_drug(self, mock_search, mock_reactions, mock_backend):
        """Phase 1 should create Drug node + reactions when RxNorm resolves."""
        from src.kg.dynamic_builder import expand_drug_phase1, get_build_status

        # Mock RxNorm resolution
        mock_rxnorm = {
            "rxcui": "12345",
            "generic_name": "testdrug",
            "brand_names": ["TestBrand"],
            "confidence": "exact",
        }

        # Mock backend
        backend = MagicMock()
        mock_backend.return_value = backend

        # Mock FAERS
        mock_search.return_value = "test_search"
        mock_reactions.return_value = [
            {"term": "HEADACHE", "count": 100},
            {"term": "NAUSEA", "count": 50},
        ]

        with patch("src.ingestion.rxnorm.resolve_drug_name", return_value=mock_rxnorm):
            with patch("src.ingestion.ndc.fetch_ndc_metadata", return_value=None):
                result = expand_drug_phase1("testdrug")

        self.assertEqual(result["node_id"], "12345")
        self.assertEqual(result["generic_name"], "testdrug")
        self.assertEqual(result["rxcui"], "12345")
        self.assertEqual(result["reactions_added"], 2)
        self.assertIn("elapsed_s", result)
        self.assertNotIn("error", result)

        # Status should be PHASE1_COMPLETE
        status = get_build_status("testdrug")
        self.assertEqual(status, "PHASE1_COMPLETE")

    @patch("src.kg.dynamic_builder._get_backend")
    def test_phase1_rxnorm_not_found(self, mock_backend):
        """Phase 1 should return error when drug not found in RxNorm."""
        from src.kg.dynamic_builder import expand_drug_phase1, get_build_status

        mock_rxnorm = {"confidence": "none"}

        with patch("src.ingestion.rxnorm.resolve_drug_name", return_value=mock_rxnorm):
            result = expand_drug_phase1("nonexistentdrug123")

        self.assertIn("error", result)
        self.assertEqual(get_build_status("nonexistentdrug123"), "FAILED")


class TestExpandDrugAsync(unittest.TestCase):
    """Tests for the async expansion entry point."""

    def setUp(self):
        from src.kg.dynamic_builder import _active_builds, _builds_lock
        with _builds_lock:
            _active_builds.clear()

    @patch("src.kg.dynamic_builder.expand_drug_phase2")
    @patch("src.kg.dynamic_builder.expand_drug_phase1")
    def test_async_skips_duplicates(self, mock_phase1, mock_phase2):
        """expand_drug_async should skip if build is already in progress."""
        from src.kg.dynamic_builder import (
            expand_drug_async, _set_status, STATUS_PHASE2_RUNNING,
        )

        _set_status("aspirin", STATUS_PHASE2_RUNNING)
        result = expand_drug_async("aspirin")

        self.assertTrue(result.get("skipped", False))
        mock_phase1.assert_not_called()
        mock_phase2.assert_not_called()


class TestStatusConstants(unittest.TestCase):
    """Verify status constants are consistent."""

    def test_all_statuses_are_strings(self):
        from src.kg.dynamic_builder import (
            STATUS_NOT_STARTED, STATUS_PHASE1_RUNNING,
            STATUS_PHASE1_COMPLETE, STATUS_PHASE2_RUNNING,
            STATUS_PHASE2_COMPLETE, STATUS_FAILED,
        )
        for s in [STATUS_NOT_STARTED, STATUS_PHASE1_RUNNING,
                  STATUS_PHASE1_COMPLETE, STATUS_PHASE2_RUNNING,
                  STATUS_PHASE2_COMPLETE, STATUS_FAILED]:
            self.assertIsInstance(s, str)
            self.assertTrue(len(s) > 0)


if __name__ == "__main__":
    unittest.main()
