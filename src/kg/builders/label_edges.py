"""
label_edges.py · Build drug–drug interaction edges from openFDA labels
=======================================================================
Step 3 of the KG build pipeline.
- For each Drug node, fetches label records.
- Extracts interacting drugs from drug_interactions_table (structured)
  or drug_interactions (prose via Gemini API, with regex fallback).
- Creates INTERACTS_WITH edges with source: "label".
"""

from __future__ import annotations

import json
import os
import re
import time
import warnings
from typing import TYPE_CHECKING, Dict, List, Optional, Set

if TYPE_CHECKING:
    from src.kg.backend import GraphBackend


# ──────────────────────────────────────────────────────────────
#  Gemini-based interaction extraction (primary for prose)
# ──────────────────────────────────────────────────────────────

_GEMINI_PROMPT_TEMPLATE = """You are a pharmacology expert. Extract ALL drug names mentioned as interacting with the target drug from the following drug interaction text.

Target drug: {drug_name}

Drug interaction text:
\"\"\"
{text}
\"\"\"

Return ONLY a JSON array of drug names (generic names preferred). Example: ["warfarin", "aspirin", "methotrexate"]
If no interacting drugs are found, return an empty array: []
Do NOT include the target drug itself. Do NOT include drug classes (like "NSAIDs") — only specific drug names."""


def _extract_via_gemini(
    text: str,
    drug_name: str,
    api_key: str,
) -> List[str]:
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")

        prompt = _GEMINI_PROMPT_TEMPLATE.format(
            drug_name=drug_name,
            text=text[:3000],
        )
        resp = model.generate_content(prompt)
        if not resp or not resp.text:
            return []

        raw = resp.text.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)

        names = json.loads(raw)
        if isinstance(names, list):
            return [n.strip().lower() for n in names if isinstance(n, str) and n.strip()]
    except Exception as e:
        warnings.warn(f"Gemini extraction failed: {e}")

    return []


# ──────────────────────────────────────────────────────────────
#  Regex fallback (for when Gemini is unavailable)
# ──────────────────────────────────────────────────────────────

def _extract_drug_names_from_prose(
    text: str,
    known_drugs: Set[str],
) -> List[str]:
    if not text or not known_drugs:
        return []

    text_lower = text.lower()
    found = []

    for drug_name in sorted(known_drugs, key=len, reverse=True):
        if len(drug_name) < 3:
            continue
        pattern = r'\b' + re.escape(drug_name) + r'\b'
        if re.search(pattern, text_lower):
            found.append(drug_name)

    return found


def _extract_from_interaction_table(
    table_data: list,
    known_drugs: Set[str],
) -> List[str]:
    found = []
    if not table_data:
        return found

    for entry in table_data:
        if isinstance(entry, dict):
            for val in entry.values():
                if isinstance(val, str):
                    names = _extract_drug_names_from_prose(val, known_drugs)
                    found.extend(names)
                elif isinstance(val, list):
                    for item in val:
                        if isinstance(item, str):
                            names = _extract_drug_names_from_prose(item, known_drugs)
                            found.extend(names)
        elif isinstance(entry, str):
            names = _extract_drug_names_from_prose(entry, known_drugs)
            found.extend(names)

    return list(set(found))


# ──────────────────────────────────────────────────────────────
#  Main builder
# ──────────────────────────────────────────────────────────────

def build_label_interaction_edges(
    backend: GraphBackend,
    drugs: List[Dict],
    sleep_s: float = 0.25,
    gemini_api_key: Optional[str] = None,
) -> None:
    """
    For each drug, fetch openFDA label records and extract drug–drug
    interactions.  Creates INTERACTS_WITH edges with source: "label".
    """
    from src.ingestion.openfda_client import fetch_openfda_records

    api_key = gemini_api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
    use_gemini = bool(api_key)

    known_drugs = backend.get_all_drug_names()

    if use_gemini:
        print(f"  [Labels] Using Gemini API for interaction extraction (drug dict: {len(known_drugs)} names)")
    else:
        print(f"  [Labels] No Gemini API key found — using regex fallback (drug dict: {len(known_drugs)} names)")
        print(f"  [Labels] Set GEMINI_API_KEY env var for better extraction recall")

    edge_count = 0
    failed = 0
    gemini_calls = 0

    for i, drug in enumerate(drugs):
        node_id = drug["node_id"]
        generic = drug["generic_name"]
        rxcui = drug.get("rxcui")

        self_names = {generic.lower()}
        for bn in drug.get("brand_names", []):
            if bn:
                self_names.add(bn.lower())
        if rxcui:
            self_names.add(rxcui)

        try:
            search = f'openfda.generic_name:"{generic}"'
            records = fetch_openfda_records(search=search, limit=3)

            if not records and rxcui:
                search = f'openfda.rxcui:"{rxcui}"'
                records = fetch_openfda_records(search=search, limit=3)
        except Exception as e:
            print(f"  [Labels] Error fetching labels for '{generic}': {e}")
            failed += 1
            time.sleep(sleep_s)
            continue

        if not records:
            time.sleep(sleep_s)
            continue

        interacting_names: Set[str] = set()

        for rec in records:
            table = rec.get("drug_interactions_table")
            if table and isinstance(table, list):
                names = _extract_from_interaction_table(table, known_drugs)
                interacting_names.update(names)

            prose = rec.get("drug_interactions")
            if prose:
                if isinstance(prose, list):
                    prose = " ".join(prose)

                if use_gemini and len(prose) > 50:
                    gemini_names = _extract_via_gemini(prose, generic, api_key)
                    interacting_names.update(gemini_names)
                    gemini_calls += 1
                    regex_names = _extract_drug_names_from_prose(prose, known_drugs)
                    interacting_names.update(regex_names)
                else:
                    names = _extract_drug_names_from_prose(prose, known_drugs)
                    interacting_names.update(names)

        interacting_names -= self_names

        for int_name in interacting_names:
            target_id = backend.find_drug_node_id(int_name)
            if target_id and target_id != node_id:
                backend.upsert_edge(node_id, target_id, "INTERACTS_WITH", {
                    "source": "label",
                })
                backend.upsert_edge(target_id, node_id, "INTERACTS_WITH", {
                    "source": "label",
                })
                edge_count += 1

        if (i + 1) % 50 == 0:
            print(f"  [Labels] Processed {i + 1}/{len(drugs)} drugs ({edge_count} interaction pairs, {gemini_calls} Gemini calls)")
            backend.commit()

        time.sleep(sleep_s)

    backend.commit()
    print(f"  [Labels] Done. {edge_count} interaction pairs, {gemini_calls} Gemini calls, {failed} failed.")
