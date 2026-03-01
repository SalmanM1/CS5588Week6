"""
graph_enrichment.py · Graph-Enriched Chunk Context for RAG
==========================================================
Prepends structured KnowledgeGraph context to raw chunk text so that
embeddings capture multi-hop relationships (interactions, reactions,
ingredients, FAERS disparity signals) rather than just the label prose.

Used by the *offline* ingestion path (`build_artifacts(kg=...)`) —
the query-time pipeline is unaffected.
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from src.kg.loader import KnowledgeGraph


def _build_drug_context(drug_id: str, kg: KnowledgeGraph) -> Optional[str]:
    """Query the KG for a single drug and format a reusable context block.

    Returns ``None`` when the drug is not found in the graph so the
    caller can fall back to the original text.
    """
    identity = kg.get_drug_identity(drug_id)
    if not identity:
        return None

    generic = identity.get("generic_name", drug_id)
    rxcui = identity.get("rxcui", "")
    brands = identity.get("brand_names", [])
    brand_str = ", ".join(brands[:8]) if brands else "N/A"

    interactions = kg.get_interactions(drug_id)[:5]
    int_names = ", ".join(i["drug_name"] for i in interactions) or "none known"

    co_reported = kg.get_co_reported(drug_id)[:5]
    co_names = ", ".join(c["drug_name"] for c in co_reported) or "none known"

    reactions = kg.get_drug_reactions(drug_id)[:5]
    rxn_names = ", ".join(r["reaction"] for r in reactions) or "none known"

    ingredients = kg.get_ingredients(drug_id)
    ing_names = ", ".join(i["ingredient"] for i in ingredients) or "N/A"

    disparity = kg.get_disparity_analysis(drug_id)
    emerging_lines: List[str] = []
    if disparity:
        for sig in disparity.get("emerging_signals", [])[:5]:
            emerging_lines.append(f"[EMERGING RISK] {sig['reaction']}")

    emerging_str = ", ".join(emerging_lines) if emerging_lines else "none detected"

    lines = [
        "[GRAPH CONTEXT]",
        f"Drug: {generic} | RxCUI: {rxcui} | Also known as: {brand_str}",
        f"Ingredients: {ing_names}",
        f"Interactions: {int_names}",
        f"Adverse reactions (FAERS): {rxn_names}",
        f"Co-reported drugs: {co_names}",
        f"Emerging risks (FAERS not on label): {emerging_str}",
    ]
    return "\n".join(lines)


# Per-batch cache so multiple chunks sharing the same doc_id
# (= same drug) reuse a single set of KG queries.
_context_cache: Dict[str, Optional[str]] = {}


def clear_context_cache() -> None:
    """Reset the per-drug context cache between ingestion batches."""
    _context_cache.clear()


def enrich_chunk(
    chunk_id: str,
    text: str,
    kg: Any,
    *,
    _cache: Optional[Dict[str, Optional[str]]] = None,
) -> str:
    """Prepend KnowledgeGraph context to a chunk's text for embedding.

    Parameters
    ----------
    chunk_id:
        Chunk identifier in the format ``{doc_id}::{field}[::cN]``.
        The *doc_id* segment is the RxCUI or lowercased generic name
        used as the Drug node ID in the KG.
    text:
        Original chunk text (never mutated).
    kg:
        A :class:`KnowledgeGraph` instance (from ``src.kg.loader``).
        Accepts ``Any`` at the type level to avoid a hard import
        dependency from the ingestion layer into the KG package.
    _cache:
        Optional external cache dict; when ``None`` the module-level
        ``_context_cache`` is used.  Primarily for testing.

    Returns
    -------
    str
        ``"[GRAPH CONTEXT]\\n...\\n\\n{text}"`` when graph data is
        available, or the original *text* unchanged when the drug is
        not found in the KG.
    """
    cache = _cache if _cache is not None else _context_cache

    drug_id = chunk_id.split("::")[0] if "::" in chunk_id else chunk_id

    if drug_id not in cache:
        try:
            cache[drug_id] = _build_drug_context(drug_id, kg)
        except Exception as exc:
            warnings.warn(f"Graph enrichment failed for '{drug_id}': {exc}")
            cache[drug_id] = None

    context = cache.get(drug_id)
    if context is None:
        return text

    return f"{context}\n\n{text}"
