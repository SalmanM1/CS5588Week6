"""
dynamic_builder.py · On-Demand KG Expansion for Unknown Drugs
================================================================
When a user queries a drug not yet in the Knowledge Graph, this module
dynamically builds KG data using a two-phase progressive loading strategy:

Phase 1 (Lightweight, 2-5 s synchronous):
    - RxNorm resolution → Drug node
    - NDC ingredient lookup → Ingredient nodes + edges
    - FAERS top 10 reactions → Reaction nodes + edges
    Result: basic drug profile is immediately available for the RAG pipeline.

Phase 2 (Full build, background thread):
    - Full FAERS co-reported drugs
    - Label interaction edges (via Gemini or regex fallback)
    - Label reaction warnings (for disparity analysis)
    Result: complete drug profile, KG visualization fully populated.

Public API:
    expand_drug_phase1(drug_name)   → dict   (synchronous, ~2-5s)
    expand_drug_phase2(drug_name)   → None   (synchronous, ~20-60s)
    expand_drug_async(drug_name)    → dict   (Phase 1 sync + Phase 2 in daemon thread)
    get_build_status(drug_name)     → str    (poll for current build phase)

Thread Safety:
    Uses a module-level ``_active_builds`` dict guarded by ``threading.Lock``.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Dict, List, Optional

from src.kg.backend import GraphBackend, create_backend

# ──────────────────────────────────────────────────────────────
#  Build status tracking
# ──────────────────────────────────────────────────────────────

STATUS_NOT_STARTED = "NOT_STARTED"
STATUS_PHASE1_RUNNING = "PHASE1_RUNNING"
STATUS_PHASE1_COMPLETE = "PHASE1_COMPLETE"
STATUS_PHASE2_RUNNING = "PHASE2_RUNNING"
STATUS_PHASE2_COMPLETE = "PHASE2_COMPLETE"
STATUS_FAILED = "FAILED"

_active_builds: Dict[str, Dict[str, Any]] = {}
_builds_lock = threading.Lock()


def get_build_status(drug_name: str) -> str:
    """Return the current build phase for a drug.

    Returns one of:
        ``NOT_STARTED``, ``PHASE1_RUNNING``, ``PHASE1_COMPLETE``,
        ``PHASE2_RUNNING``, ``PHASE2_COMPLETE``, ``FAILED``.
    """
    key = drug_name.strip().lower()
    with _builds_lock:
        entry = _active_builds.get(key)
        if entry is None:
            return STATUS_NOT_STARTED
        return entry.get("status", STATUS_NOT_STARTED)


def _set_status(drug_key: str, status: str, **extra: Any) -> None:
    """Update the build status for a drug (internal use)."""
    with _builds_lock:
        if drug_key not in _active_builds:
            _active_builds[drug_key] = {}
        _active_builds[drug_key]["status"] = status
        _active_builds[drug_key].update(extra)


# ──────────────────────────────────────────────────────────────
#  Backend helper
# ──────────────────────────────────────────────────────────────

def _get_backend() -> GraphBackend:
    """Create a backend from the current environment (auto-detect)."""
    return create_backend()


# ──────────────────────────────────────────────────────────────
#  Phase 1: Lightweight expansion (~2-5 seconds)
# ──────────────────────────────────────────────────────────────

def expand_drug_phase1(drug_name: str) -> Dict[str, Any]:
    """Synchronous lightweight KG expansion for a single drug.

    Steps:
        1. Resolve via RxNorm → canonical name, RxCUI, brand names
        2. Create Drug node in the backend
        3. Fetch NDC ingredient metadata → Ingredient nodes + edges
        4. Fetch top 10 FAERS reactions → Reaction nodes + edges

    Parameters
    ----------
    drug_name : str
        The drug name to expand (brand, generic, or misspelled).

    Returns
    -------
    dict
        Keys: ``node_id``, ``generic_name``, ``rxcui``, ``brand_names``,
        ``ingredients_added``, ``reactions_added``, ``elapsed_s``.
        Returns ``{"error": ...}`` on failure.
    """
    key = drug_name.strip().lower()
    t0 = time.time()
    _set_status(key, STATUS_PHASE1_RUNNING, started_at=t0)

    try:
        from src.ingestion.rxnorm import resolve_drug_name
        from src.kg.builders.faers_edges import build_faers_search, fetch_top_reactions

        # Step 1: RxNorm resolution
        rxnorm = resolve_drug_name(drug_name)
        rxcui = rxnorm.get("rxcui")
        generic = rxnorm.get("generic_name") or rxnorm.get("resolved_name") or drug_name
        brands = rxnorm.get("brand_names", [])
        confidence = rxnorm.get("confidence", "none")

        if confidence == "none" and not rxcui:
            _set_status(key, STATUS_FAILED, error="Drug not found in RxNorm")
            return {"error": f"Drug '{drug_name}' not found in RxNorm"}

        node_id = rxcui if rxcui else generic.lower()

        # Step 2: Create Drug node
        backend = _get_backend()
        try:
            backend.upsert_node(node_id, "Drug", {
                "generic_name": generic,
                "brand_names": brands,
                "rxcui": rxcui,
                "confidence": confidence,
                "dynamic": True,  # Flag: added by dynamic builder
            })
            backend.commit()

            # Step 3: NDC ingredients
            ingredients_added = 0
            try:
                from src.ingestion.ndc import fetch_ndc_metadata
                brand = brands[0] if brands else None
                ndc_meta = fetch_ndc_metadata(
                    generic_name=generic,
                    brand_name=brand,
                    rxcui=rxcui,
                )
                if ndc_meta and ndc_meta.get("active_ingredients"):
                    for ing in ndc_meta["active_ingredients"]:
                        ing_name = ing.get("name", "").strip()
                        if not ing_name:
                            continue
                        ing_id = ing_name.lower()
                        backend.upsert_node(ing_id, "Ingredient", {"name": ing_name})
                        backend.upsert_edge(node_id, ing_id, "HAS_ACTIVE_INGREDIENT", {
                            "source": "ndc",
                            "strength": ing.get("strength", ""),
                        })
                        ingredients_added += 1
                    backend.commit()
            except Exception:
                pass  # Non-fatal: ingredients are nice-to-have

            # Step 4: Top 10 FAERS reactions
            reactions_added = 0
            try:
                search = build_faers_search(generic, rxcui)
                reactions = fetch_top_reactions(search, limit=10)
                for rx in reactions:
                    term = rx.get("term", "").strip()
                    count = rx.get("count", 0)
                    if not term:
                        continue
                    reaction_id = f"reaction:{term.lower()}"
                    backend.upsert_node(reaction_id, "Reaction", {
                        "reactionmeddrapt": term,
                    })
                    backend.upsert_edge(node_id, reaction_id, "DRUG_CAUSES_REACTION", {
                        "source": "faers",
                        "report_count": count,
                    })
                    reactions_added += 1
                backend.commit()
            except Exception:
                pass  # Non-fatal: reactions may be unavailable

            # Rebuild aliases so the new drug is findable
            backend.rebuild_aliases()
            backend.commit()

            elapsed = round(time.time() - t0, 2)
            _set_status(key, STATUS_PHASE1_COMPLETE,
                        node_id=node_id, elapsed_phase1=elapsed)

            return {
                "node_id": node_id,
                "generic_name": generic,
                "rxcui": rxcui,
                "brand_names": brands,
                "ingredients_added": ingredients_added,
                "reactions_added": reactions_added,
                "elapsed_s": elapsed,
            }
        finally:
            backend.close()

    except Exception as exc:
        _set_status(key, STATUS_FAILED, error=str(exc))
        return {"error": str(exc)}


# ──────────────────────────────────────────────────────────────
#  Phase 2: Full build (background, ~20-60 seconds)
# ──────────────────────────────────────────────────────────────

def expand_drug_phase2(drug_name: str) -> None:
    """Full KG expansion for a single drug (synchronous, long-running).

    Steps:
        1. Full FAERS co-reported drugs
        2. Label interaction edges (Gemini or regex)
        3. Label reaction warnings (for disparity analysis)

    This is designed to run in a background thread after Phase 1.
    """
    key = drug_name.strip().lower()
    _set_status(key, STATUS_PHASE2_RUNNING)

    try:
        from src.ingestion.rxnorm import resolve_drug_name
        from src.kg.builders.faers_edges import (
            build_faers_search,
            fetch_co_reported_drugs,
        )
        from src.kg.builders.label_edges import build_label_interaction_edges
        from src.kg.builders.label_reaction_edges import build_label_reaction_edges

        # Resolve drug info again (cheap, cached in practice)
        rxnorm = resolve_drug_name(drug_name)
        rxcui = rxnorm.get("rxcui")
        generic = rxnorm.get("generic_name") or rxnorm.get("resolved_name") or drug_name
        brands = rxnorm.get("brand_names", [])
        node_id = rxcui if rxcui else generic.lower()

        backend = _get_backend()
        try:
            # Build a drug dict matching what the builders expect
            drug_dict = {
                "node_id": node_id,
                "generic_name": generic,
                "rxcui": rxcui,
                "brand_names": brands,
            }
            drugs = [drug_dict]

            # Step 1: Full FAERS co-reported drugs
            try:
                search = build_faers_search(generic, rxcui)
                co_drugs = fetch_co_reported_drugs(search, limit=50)
                for cd in co_drugs:
                    term = cd.get("term", "").strip()
                    count = cd.get("count", 0)
                    if not term or term.lower() == generic.lower():
                        continue
                    target_id = backend.find_drug_node_id(term)
                    if not target_id:
                        stub_id = term.strip().lower()
                        if stub_id == node_id:
                            continue
                        backend.upsert_node(stub_id, "Drug", {
                            "generic_name": term.strip(),
                            "stub": True,
                        })
                        target_id = stub_id
                    if target_id and target_id != node_id:
                        backend.upsert_edge(node_id, target_id, "CO_REPORTED_WITH", {
                            "source": "faers",
                            "report_count": count,
                        })
                backend.commit()
            except Exception:
                pass

            # Step 2: Label interaction edges
            gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
            try:
                build_label_interaction_edges(
                    backend, drugs, sleep_s=0.3, gemini_api_key=gemini_key,
                )
            except Exception:
                pass

            # Step 3: Label reaction warnings
            try:
                build_label_reaction_edges(backend, drugs, sleep_s=0.3)
            except Exception:
                pass

            # Rebuild aliases to include any new stub drugs
            backend.rebuild_aliases()
            backend.commit()

            _set_status(key, STATUS_PHASE2_COMPLETE)

        finally:
            backend.close()

    except Exception as exc:
        _set_status(key, STATUS_FAILED, error=str(exc))


# ──────────────────────────────────────────────────────────────
#  Async expansion (public entry point)
# ──────────────────────────────────────────────────────────────

def expand_drug_async(drug_name: str) -> Dict[str, Any]:
    """Run Phase 1 synchronously, then kick off Phase 2 in a background thread.

    Parameters
    ----------
    drug_name : str
        The drug name to expand.

    Returns
    -------
    dict
        Phase 1 result dict (immediately usable by the RAG pipeline).
        Includes ``phase2_thread`` key indicating background work is running.
    """
    key = drug_name.strip().lower()

    # Skip if already built or in progress
    current_status = get_build_status(drug_name)
    if current_status in (
        STATUS_PHASE1_RUNNING,
        STATUS_PHASE2_RUNNING,
        STATUS_PHASE2_COMPLETE,
    ):
        with _builds_lock:
            entry = _active_builds.get(key, {})
        return {
            "node_id": entry.get("node_id", key),
            "status": current_status,
            "skipped": True,
        }

    # Phase 1: synchronous
    phase1_result = expand_drug_phase1(drug_name)

    if "error" in phase1_result:
        return phase1_result

    # Phase 2: background thread
    t = threading.Thread(
        target=expand_drug_phase2,
        args=(drug_name,),
        daemon=True,
        name=f"kg-expand-{key}",
    )
    t.start()

    phase1_result["phase2_thread"] = True
    return phase1_result
