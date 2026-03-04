"""
faers_edges.py · Build FAERS co-reported & drug–reaction edges
================================================================
Step 4 of the KG build pipeline.
- For each Drug node, queries FAERS count endpoints.
- Creates CO_REPORTED_WITH edges (drug–drug from same adverse event reports).
- Creates Reaction nodes + DRUG_CAUSES_REACTION edges.

Public helpers (used by dynamic_builder):
    build_faers_search()     — construct a FAERS search clause
    fetch_top_reactions()    — top adverse reactions for a drug
    fetch_co_reported_drugs()— top co-reported drugs from FAERS
"""

from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from src.kg.backend import GraphBackend


# ──────────────────────────────────────────────────────────────
#  SSL / HTTP (reuse pattern)
# ──────────────────────────────────────────────────────────────

try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _SSL_CTX = ssl.create_default_context()

_FAERS_BASE = "https://api.fda.gov/drug/event.json"
_UA = "TruPharma/2.0"
_TIMEOUT = 15


def _api_get(url: str) -> dict:
    """GET JSON. Returns {} on any failure."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT, context=_SSL_CTX) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError,
            json.JSONDecodeError, OSError):
        return {}


# ──────────────────────────────────────────────────────────────
#  FAERS count queries  (public API)
# ──────────────────────────────────────────────────────────────

def build_faers_search(generic_name: str, rxcui: Optional[str] = None) -> str:
    """Build a FAERS search clause for a drug (by generic name and optional RxCUI)."""
    name = generic_name.strip().lower()
    clauses = [f'patient.drug.openfda.generic_name:"{name}"']
    if rxcui:
        clauses.append(f'patient.drug.openfda.rxcui:"{rxcui}"')
    return "+OR+".join(clauses)


def fetch_co_reported_drugs(search: str, limit: int = 20) -> List[dict]:
    """Fetch drugs most frequently co-reported with the target in FAERS.

    Parameters
    ----------
    search : str
        FAERS search clause (from :func:`build_faers_search`).
    limit : int
        Maximum number of co-reported drugs to return.

    Returns
    -------
    list[dict]
        Each dict has ``term`` (drug name) and ``count`` (report count).
    """
    url = (
        f"{_FAERS_BASE}?search={search}"
        f"&count=patient.drug.medicinalproduct.exact&limit={limit}"
    )
    data = _api_get(url)
    return [
        {"term": r.get("term", ""), "count": r.get("count", 0)}
        for r in data.get("results", [])
    ]


def fetch_top_reactions(search: str, limit: int = 25) -> List[dict]:
    """Fetch the most frequently reported adverse reactions for a drug from FAERS.

    Parameters
    ----------
    search : str
        FAERS search clause (from :func:`build_faers_search`).
    limit : int
        Maximum number of reactions to return.

    Returns
    -------
    list[dict]
        Each dict has ``term`` (MedDRA preferred term) and ``count``.
    """
    url = (
        f"{_FAERS_BASE}?search={search}"
        f"&count=patient.reaction.reactionmeddrapt.exact&limit={limit}"
    )
    data = _api_get(url)
    return [
        {"term": r.get("term", ""), "count": r.get("count", 0)}
        for r in data.get("results", [])
    ]


# Backward-compatible aliases (internal use)
_build_search = build_faers_search
_fetch_co_reported_drugs = fetch_co_reported_drugs
_fetch_top_reactions = fetch_top_reactions


# ──────────────────────────────────────────────────────────────
#  Main builder
# ──────────────────────────────────────────────────────────────

def build_faers_edges(
    backend: GraphBackend,
    drugs: List[Dict],
    sleep_s: float = 0.3,
    max_co_reported: int = 50,
    max_reactions: int = 20,
) -> None:
    """
    For each drug, query FAERS count endpoints and create:
      - CO_REPORTED_WITH edges (drug pairs from same FAERS reports)
      - Reaction nodes + DRUG_CAUSES_REACTION edges
    """
    co_reported_count = 0
    reaction_edge_count = 0
    reaction_node_count = 0
    failed = 0

    for i, drug in enumerate(drugs):
        node_id = drug["node_id"]
        generic = drug["generic_name"]
        rxcui = drug.get("rxcui")

        search = build_faers_search(generic, rxcui)

        # ── Co-reported drugs ──────────────────────────────────
        try:
            co_drugs = fetch_co_reported_drugs(search, limit=max_co_reported)
        except Exception:
            co_drugs = []
            failed += 1

        for cd in co_drugs:
            term = cd.get("term", "").strip()
            count = cd.get("count", 0)
            if not term:
                continue

            if term.lower() == generic.lower():
                continue

            target_id = backend.find_drug_node_id(term)

            if not target_id:
                stub_id = term.strip().lower()
                if stub_id == node_id or stub_id == generic.lower():
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
                co_reported_count += 1

        time.sleep(sleep_s)

        # ── Drug → Reaction edges ──────────────────────────────
        try:
            reactions = fetch_top_reactions(search, limit=max_reactions)
        except Exception:
            reactions = []
            failed += 1

        for rx in reactions:
            term = rx.get("term", "").strip()
            count = rx.get("count", 0)
            if not term:
                continue

            reaction_id = f"reaction:{term.lower()}"

            # upsert_node uses MERGE semantics (INSERT ON CONFLICT UPDATE
            # for SQLite, MERGE for Neo4j) — no need for a separate
            # node_exists() guard; shared Reaction nodes are correctly
            # reused across drugs, enabling true many-to-many Drug↔Reaction.
            backend.upsert_node(reaction_id, "Reaction", {
                "reactionmeddrapt": term,
            })
            reaction_node_count += 1

            backend.upsert_edge(node_id, reaction_id, "DRUG_CAUSES_REACTION", {
                "source": "faers",
                "report_count": count,
            })
            reaction_edge_count += 1

        time.sleep(sleep_s)

        if (i + 1) % 50 == 0:
            print(
                f"  [FAERS] Processed {i + 1}/{len(drugs)} drugs "
                f"({co_reported_count} co-reported, {reaction_edge_count} reaction edges)"
            )
            backend.commit()

    backend.commit()
    print(
        f"  [FAERS] Done. {co_reported_count} co-reported edges, "
        f"{reaction_node_count} Reaction nodes, {reaction_edge_count} reaction edges, "
        f"{failed} failed."
    )
