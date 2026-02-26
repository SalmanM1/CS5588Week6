"""
backend.py · TruPharma Knowledge Graph — Backend Abstraction
=============================================================
Defines a GraphBackend protocol and two implementations:
  - SqliteBackend  (local file, default)
  - Neo4jBackend   (remote graph database with batched writes)

Usage:
    backend = create_backend()                     # auto-detect from env
    backend = create_backend("sqlite", path=...)   # explicit SQLite
    backend = create_backend("neo4j")              # explicit Neo4j (reads env)
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from typing import Any, Dict, List, Optional, Protocol, Set, runtime_checkable


# ══════════════════════════════════════════════════════════════
#  Protocol
# ══════════════════════════════════════════════════════════════

@runtime_checkable
class GraphBackend(Protocol):
    """Storage-agnostic interface for the knowledge graph."""

    # ── Write ─────────────────────────────────────────────────
    def upsert_node(
        self, node_id: str, node_type: str,
        props: Optional[Dict[str, Any]] = None,
    ) -> None: ...

    def upsert_edge(
        self, src: str, dst: str, edge_type: str,
        props: Optional[Dict[str, Any]] = None,
    ) -> None: ...

    def commit(self) -> None: ...
    def close(self) -> None: ...

    # ── Read ──────────────────────────────────────────────────
    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]: ...
    def get_nodes_by_type(self, node_type: str) -> List[Dict[str, Any]]: ...

    def get_edges(
        self, node_id: str, edge_type: str, direction: str = "outgoing",
    ) -> List[Dict[str, Any]]: ...

    def node_exists(self, node_id: str) -> bool: ...
    def count_nodes(self, node_type: Optional[str] = None) -> int: ...
    def count_edges(self, edge_type: Optional[str] = None) -> int: ...

    # ── Drug-specific helpers ─────────────────────────────────
    def get_all_drug_names(self) -> Set[str]: ...
    def resolve_alias(self, name: str) -> Optional[str]: ...
    def rebuild_aliases(self) -> int: ...
    def find_drug_node_id(self, name: str) -> Optional[str]: ...
    def get_reaction_term_map(self) -> Dict[str, str]: ...


# ══════════════════════════════════════════════════════════════
#  Shared helpers
# ══════════════════════════════════════════════════════════════

_SAFE_LABEL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_label(name: str) -> str:
    """Ensure a label/relationship-type name is safe for Cypher."""
    if not _SAFE_LABEL_RE.match(name):
        raise ValueError(f"Invalid graph label/type: {name!r}")
    return name


# ══════════════════════════════════════════════════════════════
#  SQLite Implementation
# ══════════════════════════════════════════════════════════════

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS nodes (
    id    TEXT PRIMARY KEY,
    type  TEXT NOT NULL,
    props TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS edges (
    src   TEXT NOT NULL,
    dst   TEXT NOT NULL,
    type  TEXT NOT NULL,
    props TEXT DEFAULT '{}',
    PRIMARY KEY (src, dst, type)
);

CREATE TABLE IF NOT EXISTS drug_aliases (
    alias   TEXT PRIMARY KEY,
    node_id TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_edges_src_type ON edges(src, type);
CREATE INDEX IF NOT EXISTS idx_edges_dst_type ON edges(dst, type);
"""


class SqliteBackend:
    """SQLite-backed knowledge graph (local file, zero config)."""

    def __init__(
        self,
        path: str = "data/kg/trupharma_kg.db",
        *,
        readonly: bool = False,
    ):
        self._path = path
        if readonly:
            uri = f"file:{path}?mode=ro"
            self._conn = sqlite3.connect(uri, uri=True)
        else:
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            self._conn = sqlite3.connect(path)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=OFF")
            self._conn.executescript(_SCHEMA_SQL)
            self._conn.commit()

    def __enter__(self) -> SqliteBackend:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ── Write ─────────────────────────────────────────────────

    def upsert_node(
        self, node_id: str, node_type: str,
        props: Optional[Dict[str, Any]] = None,
    ) -> None:
        props_json = json.dumps(props or {}, ensure_ascii=False)
        self._conn.execute(
            "INSERT INTO nodes (id, type, props) VALUES (?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET type=excluded.type, props=excluded.props",
            (node_id, node_type, props_json),
        )

    def upsert_edge(
        self, src: str, dst: str, edge_type: str,
        props: Optional[Dict[str, Any]] = None,
    ) -> None:
        props_json = json.dumps(props or {}, ensure_ascii=False)
        self._conn.execute(
            "INSERT INTO edges (src, dst, type, props) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(src, dst, type) DO UPDATE SET props=excluded.props",
            (src, dst, edge_type, props_json),
        )

    def commit(self) -> None:
        self._conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None  # type: ignore[assignment]

    # ── Read ──────────────────────────────────────────────────

    def _parse_props(self, raw: Optional[str]) -> dict:
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}

    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        row = self._conn.execute(
            "SELECT id, type, props FROM nodes WHERE id = ?", (node_id,)
        ).fetchone()
        if not row:
            return None
        return {"id": row[0], "type": row[1], **self._parse_props(row[2])}

    def get_nodes_by_type(self, node_type: str) -> List[Dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT id, type, props FROM nodes WHERE type = ?", (node_type,)
        ).fetchall()
        return [
            {"id": r[0], "type": r[1], **self._parse_props(r[2])} for r in rows
        ]

    def get_edges(
        self, node_id: str, edge_type: str, direction: str = "outgoing",
    ) -> List[Dict[str, Any]]:
        if direction == "outgoing":
            rows = self._conn.execute(
                "SELECT src, dst, props FROM edges WHERE src = ? AND type = ?",
                (node_id, edge_type),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT src, dst, props FROM edges WHERE dst = ? AND type = ?",
                (node_id, edge_type),
            ).fetchall()
        return [
            {"src": r[0], "dst": r[1], **self._parse_props(r[2])} for r in rows
        ]

    def node_exists(self, node_id: str) -> bool:
        return self._conn.execute(
            "SELECT 1 FROM nodes WHERE id = ?", (node_id,)
        ).fetchone() is not None

    def count_nodes(self, node_type: Optional[str] = None) -> int:
        if node_type:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM nodes WHERE type = ?", (node_type,)
            ).fetchone()
        else:
            row = self._conn.execute("SELECT COUNT(*) FROM nodes").fetchone()
        return row[0] if row else 0

    def count_edges(self, edge_type: Optional[str] = None) -> int:
        if edge_type:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM edges WHERE type = ?", (edge_type,)
            ).fetchone()
        else:
            row = self._conn.execute("SELECT COUNT(*) FROM edges").fetchone()
        return row[0] if row else 0

    # ── Drug helpers ──────────────────────────────────────────

    def get_all_drug_names(self) -> Set[str]:
        names: Set[str] = set()
        rows = self._conn.execute(
            "SELECT id, props FROM nodes WHERE type = 'Drug'"
        ).fetchall()
        for row in rows:
            names.add(row[0].lower())
            props = self._parse_props(row[1])
            gn = props.get("generic_name", "")
            if gn:
                names.add(gn.lower())
            for bn in props.get("brand_names", []):
                if bn:
                    names.add(bn.lower())
        return names

    def resolve_alias(self, name: str) -> Optional[str]:
        try:
            row = self._conn.execute(
                "SELECT node_id FROM drug_aliases WHERE alias = ?",
                (name.strip().lower(),),
            ).fetchone()
            return row[0] if row else None
        except Exception:
            return None

    def rebuild_aliases(self) -> int:
        self._conn.execute("DELETE FROM drug_aliases")
        self._conn.commit()
        rows = self._conn.execute(
            "SELECT id, props FROM nodes WHERE type = 'Drug'"
        ).fetchall()
        count = 0
        for row in rows:
            node_id = row[0]
            props = self._parse_props(row[1])
            aliases: Set[str] = {node_id.lower()}
            gn = props.get("generic_name", "")
            if gn:
                aliases.add(gn.lower())
            rxcui = props.get("rxcui", "")
            if rxcui:
                aliases.add(str(rxcui))
            for bn in props.get("brand_names", []):
                if bn:
                    aliases.add(bn.lower())
            for alias in aliases:
                self._conn.execute(
                    "INSERT OR IGNORE INTO drug_aliases (alias, node_id) "
                    "VALUES (?, ?)",
                    (alias, node_id),
                )
                count += 1
        self._conn.commit()
        return count

    def find_drug_node_id(self, name: str) -> Optional[str]:
        q = name.strip()
        q_lower = q.lower()
        if not q_lower:
            return None
        row = self._conn.execute(
            "SELECT id FROM nodes WHERE type='Drug' AND id = ?", (q_lower,)
        ).fetchone()
        if row:
            return row[0]
        rows = self._conn.execute(
            "SELECT id, props FROM nodes WHERE type='Drug'"
        ).fetchall()
        for r in rows:
            props = self._parse_props(r[1])
            if props.get("rxcui") == q:
                return r[0]
            gn = (props.get("generic_name") or "").lower()
            if gn == q_lower:
                return r[0]
            brands = [b.lower() for b in props.get("brand_names", []) if b]
            if q_lower in brands:
                return r[0]
        return None

    def get_reaction_term_map(self) -> Dict[str, str]:
        rows = self._conn.execute(
            "SELECT id FROM nodes WHERE type = 'Reaction'"
        ).fetchall()
        terms: Dict[str, str] = {}
        for row in rows:
            node_id: str = row[0]
            if node_id.startswith("reaction:"):
                term = node_id[len("reaction:"):]
                terms[term.lower()] = node_id
        return terms


# ══════════════════════════════════════════════════════════════
#  Neo4j Implementation
# ══════════════════════════════════════════════════════════════

def _clean_neo4j_props(props: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Strip None values and coerce non-primitive types for Neo4j."""
    cleaned: Dict[str, Any] = {}
    for k, v in (props or {}).items():
        if v is None:
            continue
        if isinstance(v, (str, int, float, bool)):
            cleaned[k] = v
        elif isinstance(v, list):
            cleaned[k] = [x for x in v if x is not None]
        else:
            cleaned[k] = str(v)
    return cleaned


class Neo4jBackend:
    """Neo4j-backed knowledge graph with batched writes.

    Write-buffer flushes automatically at ``_FLUSH_THRESHOLD`` items or
    on any explicit ``commit()`` / read call, ensuring reads always see
    the latest data.
    """

    _FLUSH_THRESHOLD = 500

    def __init__(
        self,
        uri: str,
        user: str,
        password: str,
        database: str = "neo4j",
    ):
        try:
            from neo4j import GraphDatabase  # noqa: F811
        except ImportError:
            raise ImportError(
                "neo4j driver not installed. Run:  pip install 'neo4j>=5.0'"
            )
        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        self._database = database
        self._node_buf: List[Dict[str, Any]] = []
        self._edge_buf: List[Dict[str, Any]] = []
        self._ensure_constraints()

    def __enter__(self) -> Neo4jBackend:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ── Schema / constraints ──────────────────────────────────

    def _ensure_constraints(self) -> None:
        stmts = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Drug) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Reaction) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Ingredient) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Product) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:DrugAlias) REQUIRE n.alias IS UNIQUE",
            "CREATE INDEX IF NOT EXISTS FOR (n:Drug) ON (n.generic_name)",
        ]
        with self._driver.session(database=self._database) as session:
            for stmt in stmts:
                try:
                    session.run(stmt)
                except Exception:
                    pass

    # ── Write (buffered) ──────────────────────────────────────

    def upsert_node(
        self, node_id: str, node_type: str,
        props: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._node_buf.append({
            "id": node_id,
            "type": _validate_label(node_type),
            "props": _clean_neo4j_props(props),
        })
        if len(self._node_buf) >= self._FLUSH_THRESHOLD:
            self._flush_nodes()

    def upsert_edge(
        self, src: str, dst: str, edge_type: str,
        props: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._edge_buf.append({
            "src": src,
            "dst": dst,
            "type": _validate_label(edge_type),
            "props": _clean_neo4j_props(props),
        })
        if len(self._edge_buf) >= self._FLUSH_THRESHOLD:
            self._flush_edges()

    def _flush_nodes(self) -> None:
        if not self._node_buf:
            return
        by_type: Dict[str, List[Dict[str, Any]]] = {}
        for n in self._node_buf:
            by_type.setdefault(n["type"], []).append(n)
        with self._driver.session(database=self._database) as session:
            for label, batch in by_type.items():
                cypher = (
                    f"UNWIND $batch AS row "
                    f"MERGE (n:{label} {{id: row.id}}) "
                    f"SET n += row.props"
                )
                session.run(
                    cypher,
                    batch=[{"id": n["id"], "props": n["props"]} for n in batch],
                )
        self._node_buf.clear()

    def _flush_edges(self) -> None:
        if not self._edge_buf:
            return
        by_type: Dict[str, List[Dict[str, Any]]] = {}
        for e in self._edge_buf:
            by_type.setdefault(e["type"], []).append(e)
        with self._driver.session(database=self._database) as session:
            for rel_type, batch in by_type.items():
                cypher = (
                    f"UNWIND $batch AS row "
                    f"MATCH (a {{id: row.src}}) "
                    f"MATCH (b {{id: row.dst}}) "
                    f"MERGE (a)-[r:{rel_type}]->(b) "
                    f"SET r += row.props"
                )
                session.run(
                    cypher,
                    batch=[
                        {"src": e["src"], "dst": e["dst"], "props": e["props"]}
                        for e in batch
                    ],
                )
        self._edge_buf.clear()

    def commit(self) -> None:
        self._flush_nodes()
        self._flush_edges()

    def close(self) -> None:
        self.commit()
        if self._driver:
            self._driver.close()
            self._driver = None  # type: ignore[assignment]

    # ── Read ──────────────────────────────────────────────────

    def _ensure_flushed(self) -> None:
        """Flush pending writes so reads see the latest state."""
        if self._node_buf or self._edge_buf:
            self.commit()

    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        self._ensure_flushed()
        with self._driver.session(database=self._database) as session:
            result = session.run(
                "MATCH (n {id: $id}) WHERE NOT n:DrugAlias "
                "RETURN n, labels(n) AS labels",
                id=node_id,
            )
            record = result.single()
            if not record:
                return None
            node = dict(record["n"])
            labels = record["labels"]
            node_type = next(
                (l for l in labels if l != "DrugAlias"), labels[0] if labels else "Unknown"
            )
            nid = node.pop("id", node_id)
            return {"id": nid, "type": node_type, **node}

    def get_nodes_by_type(self, node_type: str) -> List[Dict[str, Any]]:
        self._ensure_flushed()
        label = _validate_label(node_type)
        with self._driver.session(database=self._database) as session:
            result = session.run(f"MATCH (n:{label}) RETURN n")
            out: List[Dict[str, Any]] = []
            for record in result:
                node = dict(record["n"])
                nid = node.pop("id", "")
                out.append({"id": nid, "type": node_type, **node})
            return out

    def get_edges(
        self, node_id: str, edge_type: str, direction: str = "outgoing",
    ) -> List[Dict[str, Any]]:
        self._ensure_flushed()
        rel = _validate_label(edge_type)
        with self._driver.session(database=self._database) as session:
            if direction == "outgoing":
                cypher = (
                    f"MATCH (a {{id: $id}})-[r:{rel}]->(b) "
                    f"RETURN a.id AS src, b.id AS dst, properties(r) AS props"
                )
            else:
                cypher = (
                    f"MATCH (a)-[r:{rel}]->(b {{id: $id}}) "
                    f"RETURN a.id AS src, b.id AS dst, properties(r) AS props"
                )
            result = session.run(cypher, id=node_id)
            out: List[Dict[str, Any]] = []
            for record in result:
                props = dict(record["props"] or {})
                out.append({"src": record["src"], "dst": record["dst"], **props})
            return out

    def node_exists(self, node_id: str) -> bool:
        self._ensure_flushed()
        with self._driver.session(database=self._database) as session:
            result = session.run(
                "MATCH (n {id: $id}) RETURN count(n) AS cnt", id=node_id,
            )
            return result.single()["cnt"] > 0  # type: ignore[index]

    def count_nodes(self, node_type: Optional[str] = None) -> int:
        self._ensure_flushed()
        with self._driver.session(database=self._database) as session:
            if node_type:
                label = _validate_label(node_type)
                result = session.run(
                    f"MATCH (n:{label}) RETURN count(n) AS cnt"
                )
            else:
                result = session.run(
                    "MATCH (n) WHERE NOT n:DrugAlias RETURN count(n) AS cnt"
                )
            return result.single()["cnt"]  # type: ignore[index]

    def count_edges(self, edge_type: Optional[str] = None) -> int:
        self._ensure_flushed()
        with self._driver.session(database=self._database) as session:
            if edge_type:
                rel = _validate_label(edge_type)
                result = session.run(
                    f"MATCH ()-[r:{rel}]->() RETURN count(r) AS cnt"
                )
            else:
                result = session.run(
                    "MATCH ()-[r]->() RETURN count(r) AS cnt"
                )
            return result.single()["cnt"]  # type: ignore[index]

    # ── Drug helpers ──────────────────────────────────────────

    def get_all_drug_names(self) -> Set[str]:
        self._ensure_flushed()
        names: Set[str] = set()
        with self._driver.session(database=self._database) as session:
            result = session.run(
                "MATCH (d:Drug) "
                "RETURN d.id AS id, d.generic_name AS gn, d.brand_names AS bns"
            )
            for rec in result:
                names.add(rec["id"].lower())
                if rec["gn"]:
                    names.add(rec["gn"].lower())
                for bn in rec["bns"] or []:
                    if bn:
                        names.add(bn.lower())
        return names

    def resolve_alias(self, name: str) -> Optional[str]:
        with self._driver.session(database=self._database) as session:
            result = session.run(
                "MATCH (a:DrugAlias {alias: $alias}) RETURN a.node_id AS nid",
                alias=name.strip().lower(),
            )
            record = result.single()
            return record["nid"] if record else None

    def rebuild_aliases(self) -> int:
        self._ensure_flushed()
        with self._driver.session(database=self._database) as session:
            session.run("MATCH (a:DrugAlias) DETACH DELETE a")
            result = session.run(
                "MATCH (d:Drug) "
                "RETURN d.id AS id, d.generic_name AS gn, "
                "d.rxcui AS rxcui, d.brand_names AS bns"
            )
            batch: List[Dict[str, str]] = []
            for rec in result:
                node_id: str = rec["id"]
                aliases: Set[str] = {node_id.lower()}
                if rec["gn"]:
                    aliases.add(rec["gn"].lower())
                if rec["rxcui"]:
                    aliases.add(str(rec["rxcui"]))
                for bn in rec["bns"] or []:
                    if bn:
                        aliases.add(bn.lower())
                for a in aliases:
                    batch.append({"alias": a, "node_id": node_id})
            if batch:
                session.run(
                    "UNWIND $batch AS row "
                    "MERGE (a:DrugAlias {alias: row.alias}) "
                    "SET a.node_id = row.node_id",
                    batch=batch,
                )
            return len(batch)

    def find_drug_node_id(self, name: str) -> Optional[str]:
        self._ensure_flushed()
        q = name.strip()
        q_lower = q.lower()
        if not q_lower:
            return None
        with self._driver.session(database=self._database) as session:
            result = session.run(
                "MATCH (d:Drug) "
                "WHERE d.id = $name_lower "
                "   OR d.rxcui = $raw "
                "   OR toLower(d.generic_name) = $name_lower "
                "   OR ANY(bn IN d.brand_names WHERE toLower(bn) = $name_lower) "
                "RETURN d.id AS id LIMIT 1",
                name_lower=q_lower,
                raw=q,
            )
            record = result.single()
            return record["id"] if record else None

    def get_reaction_term_map(self) -> Dict[str, str]:
        self._ensure_flushed()
        terms: Dict[str, str] = {}
        with self._driver.session(database=self._database) as session:
            result = session.run("MATCH (r:Reaction) RETURN r.id AS id")
            for rec in result:
                node_id: str = rec["id"]
                if node_id.startswith("reaction:"):
                    term = node_id[len("reaction:"):]
                    terms[term.lower()] = node_id
        return terms


# ══════════════════════════════════════════════════════════════
#  Factory
# ══════════════════════════════════════════════════════════════

def create_backend(
    kind: Optional[str] = None,
    *,
    sqlite_path: str = "data/kg/trupharma_kg.db",
    readonly: bool = False,
    neo4j_uri: Optional[str] = None,
    neo4j_user: Optional[str] = None,
    neo4j_password: Optional[str] = None,
    neo4j_database: str = "neo4j",
) -> GraphBackend:
    """Create a knowledge-graph backend.

    Auto-detect: when *kind* is ``None``, use Neo4j if the ``NEO4J_URI``
    env-var is set; otherwise fall back to SQLite.
    """
    if kind is None:
        kind = "neo4j" if os.environ.get("NEO4J_URI") else "sqlite"

    if kind == "neo4j":
        uri = neo4j_uri or os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        user = neo4j_user or os.environ.get("NEO4J_USER", "neo4j")
        pw = neo4j_password or os.environ.get("NEO4J_PASSWORD", "")
        db = os.environ.get("NEO4J_DATABASE", neo4j_database)
        return Neo4jBackend(uri, user, pw, database=db)

    return SqliteBackend(sqlite_path, readonly=readonly)
