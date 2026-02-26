"""
label_reaction_edges.py · Extract adverse reactions from label text
====================================================================
Step 5 of the KG build pipeline.
- For each Drug node, fetches label records.
- Extracts adverse reaction terms from the `adverse_reactions` field.
- Matches against existing Reaction nodes in the KG (from FAERS step).
- Creates LABEL_WARNS_REACTION edges (Drug → Reaction, source: "label").

This enables disparity analysis:
  - Reactions with DRUG_CAUSES_REACTION but no LABEL_WARNS_REACTION = emerging signals
  - Reactions with both = confirmed risks
"""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING, Dict, List, Set

if TYPE_CHECKING:
    from src.kg.backend import GraphBackend


def _extract_reactions_from_text(
    text: str,
    known_reactions: Dict[str, str],
) -> Set[str]:
    """
    Match known reaction terms against label adverse_reactions text.
    Returns set of matched reaction node IDs.
    """
    if not text or not known_reactions:
        return set()

    text_lower = text.lower()
    matched_ids = set()

    for term, node_id in sorted(
        known_reactions.items(), key=lambda x: len(x[0]), reverse=True
    ):
        if len(term) < 4:
            continue
        pattern = r'\b' + re.escape(term) + r'\b'
        if re.search(pattern, text_lower):
            matched_ids.add(node_id)

    return matched_ids


def build_label_reaction_edges(
    backend: GraphBackend,
    drugs: List[Dict],
    sleep_s: float = 0.25,
) -> None:
    """
    For each drug, fetch label records and extract adverse reaction terms.
    Creates LABEL_WARNS_REACTION edges linking drugs to the same Reaction
    nodes used by FAERS (DRUG_CAUSES_REACTION), enabling disparity analysis.
    """
    from src.ingestion.openfda_client import fetch_openfda_records

    known_reactions = backend.get_reaction_term_map()
    if not known_reactions:
        print("  [LabelRx] WARNING: No Reaction nodes found. Run FAERS step first.")
        return

    print(f"  [LabelRx] Matching against {len(known_reactions)} known reaction terms")

    edge_count = 0
    drugs_with_matches = 0
    failed = 0

    for i, drug in enumerate(drugs):
        node_id = drug["node_id"]
        generic = drug["generic_name"]
        rxcui = drug.get("rxcui")

        try:
            search = f'openfda.generic_name:"{generic}"'
            records = fetch_openfda_records(search=search, limit=3)
            if not records and rxcui:
                search = f'openfda.rxcui:"{rxcui}"'
                records = fetch_openfda_records(search=search, limit=3)
        except Exception as e:
            print(f"  [LabelRx] Error fetching labels for '{generic}': {e}")
            failed += 1
            time.sleep(sleep_s)
            continue

        if not records:
            time.sleep(sleep_s)
            continue

        all_matched: Set[str] = set()
        for rec in records:
            for field in ("adverse_reactions", "warnings", "warnings_and_cautions",
                          "boxed_warning", "contraindications"):
                text = rec.get(field)
                if text:
                    if isinstance(text, list):
                        text = " ".join(text)
                    matched = _extract_reactions_from_text(text, known_reactions)
                    all_matched.update(matched)

        for reaction_id in all_matched:
            backend.upsert_edge(node_id, reaction_id, "LABEL_WARNS_REACTION", {
                "source": "label",
            })
            edge_count += 1

        if all_matched:
            drugs_with_matches += 1

        if (i + 1) % 50 == 0:
            print(f"  [LabelRx] Processed {i + 1}/{len(drugs)} drugs ({edge_count} edges)")
            backend.commit()

        time.sleep(sleep_s)

    backend.commit()
    print(
        f"  [LabelRx] Done. {edge_count} LABEL_WARNS_REACTION edges, "
        f"{drugs_with_matches}/{len(drugs)} drugs had matches, {failed} failed."
    )
