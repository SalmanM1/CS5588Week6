"""
loader.py · TruPharma Knowledge Graph — Read-Only Query API
=============================================================
Loads the KG (SQLite or Neo4j) and provides structured query methods.
Used by the RAG pipeline / drug profile builder at runtime.

Graceful degradation: if the backend is unavailable, load_kg() returns
None and the app continues without KG data.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.kg.backend import GraphBackend, create_backend

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_KG_PATH = str(_PROJECT_ROOT / "data" / "kg" / "trupharma_kg.db")


class KnowledgeGraph:
    """
    Read-only wrapper around a :class:`GraphBackend`.
    Provides structured queries for drug identity, interactions,
    co-reported drugs, reactions, and ingredients.
    """

    def __init__(self, backend: GraphBackend):
        self._b = backend

    def close(self) -> None:
        self._b.close()

    # ──────────────────────────────────────────────────────────
    #  Internal helpers
    # ──────────────────────────────────────────────────────────

    def _find_drug_id(self, name_or_rxcui: str) -> Optional[str]:
        q = name_or_rxcui.strip()
        if not q:
            return None

        # Fast path: alias table
        result = self._b.resolve_alias(q)
        if result:
            return result

        # Direct id lookup
        node = self._b.get_node(q.lower())
        if node and node.get("type") == "Drug":
            return node["id"]
        node = self._b.get_node(q)
        if node and node.get("type") == "Drug":
            return node["id"]

        # Name / brand / rxcui search
        return self._b.find_drug_node_id(q)

    # ──────────────────────────────────────────────────────────
    #  Public query methods
    # ──────────────────────────────────────────────────────────

    def get_drug_identity(self, name_or_rxcui: str) -> Optional[Dict[str, Any]]:
        drug_id = self._find_drug_id(name_or_rxcui)
        if not drug_id:
            return None
        return self._b.get_node(drug_id)

    def get_interactions(self, name_or_rxcui: str) -> List[Dict[str, Any]]:
        drug_id = self._find_drug_id(name_or_rxcui)
        if not drug_id:
            return []
        edges = self._b.get_edges(drug_id, "INTERACTS_WITH", "outgoing")
        results = []
        for e in edges:
            target = self._b.get_node(e["dst"])
            results.append({
                "drug_id": e["dst"],
                "drug_name": (target or {}).get("generic_name", e["dst"]),
                "source": e.get("source", "unknown"),
                "description": e.get("description", ""),
            })
        return results

    def get_co_reported(self, name_or_rxcui: str) -> List[Dict[str, Any]]:
        drug_id = self._find_drug_id(name_or_rxcui)
        if not drug_id:
            return []
        edges = self._b.get_edges(drug_id, "CO_REPORTED_WITH", "outgoing")
        results = []
        for e in edges:
            target = self._b.get_node(e["dst"])
            results.append({
                "drug_id": e["dst"],
                "drug_name": (target or {}).get("generic_name", e["dst"]),
                "report_count": e.get("report_count", 0),
                "source": e.get("source", "faers"),
            })
        results.sort(key=lambda x: x.get("report_count", 0), reverse=True)
        return results

    def get_drug_reactions(self, name_or_rxcui: str) -> List[Dict[str, Any]]:
        drug_id = self._find_drug_id(name_or_rxcui)
        if not drug_id:
            return []
        edges = self._b.get_edges(drug_id, "DRUG_CAUSES_REACTION", "outgoing")
        results = []
        for e in edges:
            target = self._b.get_node(e["dst"])
            results.append({
                "reaction": (target or {}).get("reactionmeddrapt", e["dst"]),
                "report_count": e.get("report_count", 0),
                "source": e.get("source", "faers"),
            })
        results.sort(key=lambda x: x.get("report_count", 0), reverse=True)
        return results

    def get_ingredients(self, name_or_rxcui: str) -> List[Dict[str, Any]]:
        drug_id = self._find_drug_id(name_or_rxcui)
        if not drug_id:
            return []
        edges = self._b.get_edges(drug_id, "HAS_ACTIVE_INGREDIENT", "outgoing")
        results = []
        for e in edges:
            target = self._b.get_node(e["dst"])
            results.append({
                "ingredient": (target or {}).get("name", e["dst"]),
                "strength": e.get("strength", ""),
                "source": e.get("source", "ndc"),
            })
        return results

    def get_ingredient_drugs(self, ingredient_name: str) -> List[Dict[str, Any]]:
        """If *ingredient_name* matches an Ingredient node, return the
        Drug nodes that contain it (via incoming HAS_ACTIVE_INGREDIENT)."""
        node = self._b.get_node(ingredient_name.strip().lower())
        if not node or node.get("type") != "Ingredient":
            return []
        edges = self._b.get_edges(node["id"], "HAS_ACTIVE_INGREDIENT", "incoming")
        seen, results = set(), []
        for e in edges:
            if e["src"] in seen:
                continue
            seen.add(e["src"])
            drug = self._b.get_node(e["src"])
            if drug:
                results.append({
                    "drug_id": drug["id"],
                    "generic_name": drug.get("generic_name", drug["id"]),
                    "brand_names": drug.get("brand_names", []),
                    "strength": e.get("strength", ""),
                })
        return results

    def get_label_reactions(self, name_or_rxcui: str) -> List[Dict[str, Any]]:
        drug_id = self._find_drug_id(name_or_rxcui)
        if not drug_id:
            return []
        edges = self._b.get_edges(drug_id, "LABEL_WARNS_REACTION", "outgoing")
        results = []
        for e in edges:
            target = self._b.get_node(e["dst"])
            results.append({
                "reaction": (target or {}).get("reactionmeddrapt", e["dst"]),
                "source": "label",
            })
        return results

    def get_disparity_analysis(self, name_or_rxcui: str) -> Optional[Dict[str, Any]]:
        drug_id = self._find_drug_id(name_or_rxcui)
        if not drug_id:
            return None

        faers_reactions = self.get_drug_reactions(name_or_rxcui)
        label_reactions = self.get_label_reactions(name_or_rxcui)

        if not faers_reactions and not label_reactions:
            return None

        faers_terms = {r["reaction"].lower() for r in faers_reactions}
        label_terms = {r["reaction"].lower() for r in label_reactions}

        confirmed = faers_terms & label_terms
        emerging = faers_terms - label_terms
        unconfirmed = label_terms - faers_terms

        faers_lookup = {r["reaction"].lower(): r for r in faers_reactions}

        return {
            "confirmed_risks": [
                {
                    "reaction": t,
                    "report_count": faers_lookup.get(t, {}).get("report_count", 0),
                }
                for t in sorted(confirmed)
            ],
            "emerging_signals": [
                {
                    "reaction": t,
                    "report_count": faers_lookup.get(t, {}).get("report_count", 0),
                }
                for t in sorted(
                    emerging,
                    key=lambda x: faers_lookup.get(x, {}).get("report_count", 0),
                    reverse=True,
                )
            ],
            "unconfirmed_warnings": [{"reaction": t} for t in sorted(unconfirmed)],
            "disparity_score": len(emerging) / max(len(faers_terms), 1),
        }

    def get_summary(self, name_or_rxcui: str) -> Optional[Dict[str, Any]]:
        identity = self.get_drug_identity(name_or_rxcui)
        if not identity:
            return None
        return {
            "identity": identity,
            "interactions": self.get_interactions(name_or_rxcui),
            "co_reported": self.get_co_reported(name_or_rxcui),
            "reactions": self.get_drug_reactions(name_or_rxcui),
            "label_reactions": self.get_label_reactions(name_or_rxcui),
            "ingredients": self.get_ingredients(name_or_rxcui),
            "disparity": self.get_disparity_analysis(name_or_rxcui),
        }


# ──────────────────────────────────────────────────────────────
#  Module-level loader (with graceful degradation)
# ──────────────────────────────────────────────────────────────

_KG_INSTANCE: Optional[KnowledgeGraph] = None
_KG_LOADED: bool = False


def load_kg(path: str = _DEFAULT_KG_PATH) -> Optional[KnowledgeGraph]:
    """
    Load the Knowledge Graph from the configured backend.

    - If ``NEO4J_URI`` env-var is set → Neo4j backend.
    - Otherwise → SQLite file at *path* (must exist).

    Returns ``None`` when the backend is unavailable (graceful degradation).
    The result is cached: subsequent calls return the same instance.
    """
    global _KG_INSTANCE, _KG_LOADED

    if _KG_LOADED:
        return _KG_INSTANCE

    _KG_LOADED = True

    try:
        if os.environ.get("NEO4J_URI"):
            backend = create_backend("neo4j")
        elif os.path.exists(path):
            backend = create_backend("sqlite", sqlite_path=path, readonly=True)
        else:
            _KG_INSTANCE = None
            return None
        _KG_INSTANCE = KnowledgeGraph(backend)
    except Exception:
        _KG_INSTANCE = None

    return _KG_INSTANCE
