"""SQLite + FTS5 structured-fact store (MEMORY v1).

Complements the JSONL :class:`~openjarvis.memory.store.LocalFactStore`
(automatic, extractor-produced facts) with an explicit, structured store for
facts the user (or an agent acting for them) records deliberately:

* one row per fact with source/provenance, timestamps, scope, status, trust;
* an FTS5 index kept in sync by triggers, so a fact removed from ``facts``
  is removed from the FTS index in the same transaction;
* dedupe within a scope, supersede-on-correct, hard delete on forget;
* ranked retrieval combining FTS5 text match, recency decay, and scope;
* bounded retention: a configurable cap prunes the oldest active facts and
  records each pruning in ``prune_log`` (fact id only, never the text).

All fixture/user content in tests for this module is invented.
"""

from __future__ import annotations

import math
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from openjarvis.core.paths import get_config_dir
from openjarvis.core.registry import FactStoreRegistry
from openjarvis.memory.store import (
    RECALLABLE_TRUST_TIERS,
    TRUST_AUTO,
    TRUST_TRUSTED,
    TRUST_UNTRUSTED,
    FactStore,
)

# Fact lifecycle states. Superseded facts are retained (not retrievable) so a
# correction keeps its history; forgotten facts are hard-deleted everywhere.
STATUS_ACTIVE = "active"
STATUS_SUPERSEDED = "superseded"

# Scope that applies to every query. A query scoped to ``project:atlas``
# sees facts scoped ``project:atlas`` plus ``global`` facts, never facts
# scoped to another project.
SCOPE_GLOBAL = "global"

# Retrieval scoring: text match dominates, recency breaks near-ties, and an
# exact scope match gets a small bonus. Weights sum to 1.0 at most.
TEXT_WEIGHT = 0.6
RECENCY_WEIGHT = 0.3
SCOPE_BONUS = 0.1
RECENCY_HALF_LIFE_DAYS = 30.0

_KNOWN_TRUST_TIERS = {TRUST_AUTO, TRUST_TRUSTED, TRUST_UNTRUSTED}


def _default_sqlite_facts_path() -> Path:
    return get_config_dir() / "memory_facts.db"


def _normalize_text(text: str) -> str:
    return " ".join((text or "").lower().split())


def _normalize_scope(scope: str | None) -> str:
    scope = (scope or "").strip()
    return scope or SCOPE_GLOBAL


def _fts_query(query: str) -> str:
    """Convert free text into a safe FTS5 MATCH expression.

    Every token is double-quoted (internal quotes doubled), so FTS5 syntax
    characters in the query can never change the query structure. Tokens
    are ANDed: a fact must contain every token to match.
    """
    tokens = []
    for raw in (query or "").split():
        token = raw.strip('*"^()').strip()
        if not token:
            continue
        tokens.append('"' + token.replace('"', '""') + '"')
    return " ".join(tokens)


@dataclass(slots=True)
class StructuredFact:
    """One structured memory fact."""

    id: str
    text: str
    source: str = ""
    provenance: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0
    scope: str = SCOPE_GLOBAL
    status: str = STATUS_ACTIVE
    superseded_by: str | None = None
    trust: str = ""

    @property
    def trusted_for_recall(self) -> bool:
        return (self.trust or "").strip().lower() in RECALLABLE_TRUST_TIERS

    @property
    def is_active(self) -> bool:
        return self.status == STATUS_ACTIVE


@dataclass(slots=True)
class ScoredFact:
    """A fact with its retrieval score (higher = more relevant)."""

    fact: StructuredFact
    score: float


_SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    rowid INTEGER PRIMARY KEY,
    id TEXT NOT NULL UNIQUE,
    text TEXT NOT NULL,
    normalized TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT '',
    provenance TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    scope TEXT NOT NULL DEFAULT 'global',
    status TEXT NOT NULL DEFAULT 'active',
    superseded_by TEXT,
    trust TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS facts_dedupe_idx
    ON facts (normalized, scope, status);
CREATE INDEX IF NOT EXISTS facts_scope_idx ON facts (scope, status);
CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts
    USING fts5(text, content='facts', content_rowid='rowid');
CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN
    INSERT INTO facts_fts(rowid, text) VALUES (new.rowid, new.text);
END;
CREATE TRIGGER IF NOT EXISTS facts_ad AFTER DELETE ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, text)
        VALUES ('delete', old.rowid, old.text);
END;
CREATE TRIGGER IF NOT EXISTS facts_au AFTER UPDATE ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, text)
        VALUES ('delete', old.rowid, old.text);
    INSERT INTO facts_fts(rowid, text) VALUES (new.rowid, new.text);
END;
CREATE TABLE IF NOT EXISTS prune_log (
    fact_id TEXT NOT NULL,
    pruned_at REAL NOT NULL,
    reason TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS deletion_log (
    fact_id TEXT NOT NULL,
    deleted_at REAL NOT NULL,
    reason TEXT NOT NULL
);
"""


@FactStoreRegistry.register("sqlite-facts")
class SqliteFactStore(FactStore):
    """SQLite + FTS5 store for structured facts (MEMORY v1).

    ``path`` may be ``":memory:"`` for tests. The store is safe to call from
    multiple threads; cross-process writers are serialized by SQLite's own
    locking plus a busy timeout.
    """

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        max_facts: int = 1000,
    ) -> None:
        max_facts = int(max_facts)
        if max_facts <= 0:
            raise ValueError(f"max_facts must be a positive integer, got {max_facts}")
        self._path = (
            Path(path).expanduser()
            if path is not None
            else _default_sqlite_facts_path()
        )
        self._max_facts = max_facts
        # RLock: correct()/set_trust()/promote_reviewed() hold the lock while
        # calling get()/list(), which lock again.
        self._lock = threading.RLock()
        if str(self._path) != ":memory:":
            self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.execute("PRAGMA busy_timeout = 5000")
        self._conn.execute("PRAGMA journal_mode = WAL")
        if not self._fts5_available():
            self._conn.close()
            raise RuntimeError("SQLite build lacks FTS5; cannot open SqliteFactStore")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # -- internals --------------------------------------------------------

    def _fts5_available(self) -> bool:
        try:
            opts = self._conn.execute("PRAGMA compile_options").fetchall()
            return any("FTS5" in row[0].upper() for row in opts)
        except sqlite3.Error:
            return False

    @staticmethod
    def _row_to_fact(row: sqlite3.Row | tuple) -> StructuredFact:
        # Columns: id, text, source, provenance, created_at, updated_at,
        # scope, status, superseded_by, trust.
        return StructuredFact(
            id=row[0],
            text=row[1],
            source=row[2],
            provenance=row[3],
            created_at=float(row[4]),
            updated_at=float(row[5]),
            scope=row[6],
            status=row[7],
            superseded_by=row[8],
            trust=row[9],
        )

    # Qualified so the retrieve() JOIN against facts_fts (which also has a
    # `text` column) never hits "ambiguous column name".
    _COLUMNS = (
        "facts.id, facts.text, facts.source, facts.provenance, "
        "facts.created_at, facts.updated_at, facts.scope, facts.status, "
        "facts.superseded_by, facts.trust"
    )

    def _find_active_dedupe(
        self, normalized: str, scope: str, *, exclude_id: str | None = None
    ) -> StructuredFact | None:
        sql = (
            f"SELECT {self._COLUMNS} FROM facts "
            "WHERE normalized = ? AND scope = ? AND status = ?"
        )
        params: list[Any] = [normalized, scope, STATUS_ACTIVE]
        if exclude_id is not None:
            sql += " AND id != ?"
            params.append(exclude_id)
        row = self._conn.execute(sql, params).fetchone()
        return self._row_to_fact(row) if row else None

    def _insert_row(
        self,
        fact: StructuredFact,
    ) -> None:
        self._conn.execute(
            "INSERT INTO facts (id, text, normalized, source, provenance,"
            " created_at, updated_at, scope, status, superseded_by, trust)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                fact.id,
                fact.text,
                _normalize_text(fact.text),
                fact.source,
                fact.provenance,
                fact.created_at,
                fact.updated_at,
                fact.scope,
                fact.status,
                fact.superseded_by,
                fact.trust,
            ),
        )

    def _enforce_cap_locked(self, now: float) -> None:
        """Prune oldest active facts past the cap, logging each pruning."""
        over = self._active_count_locked() - self._max_facts
        if over <= 0:
            return
        rows = self._conn.execute(
            "SELECT id FROM facts WHERE status = ?"
            " ORDER BY created_at ASC, rowid ASC LIMIT ?",
            (STATUS_ACTIVE, over),
        ).fetchall()
        for (fact_id,) in rows:
            self._conn.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
            self._conn.execute(
                "INSERT INTO prune_log (fact_id, pruned_at, reason) VALUES (?, ?, ?)",
                (fact_id, now, "retention-cap"),
            )

    def _active_count_locked(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM facts WHERE status = ?", (STATUS_ACTIVE,)
        ).fetchone()
        return int(row[0]) if row else 0

    # -- FactStore API ------------------------------------------------------

    def add(self, text: str, source: str = "", trust: str = "") -> bool:
        try:
            _, is_new = self._remember_impl(text, source=source, trust=trust)
        except ValueError:
            return False
        return is_new

    def remember(
        self,
        text: str,
        *,
        source: str = "",
        provenance: str = "",
        scope: str | None = None,
        trust: str = "",
        created_at: float | None = None,
    ) -> StructuredFact:
        """Store *text* as a fact, or return the existing duplicate.

        Dedupe is per (normalized text, scope) among active facts. A later
        untrusted derivation quarantines an older recallable duplicate
        (mirroring :class:`LocalFactStore`); promotion needs human review.
        """
        fact, _ = self._remember_impl(
            text,
            source=source,
            provenance=provenance,
            scope=scope,
            trust=trust,
            created_at=created_at,
        )
        return fact

    def _remember_impl(
        self,
        text: str,
        *,
        source: str = "",
        provenance: str = "",
        scope: str | None = None,
        trust: str = "",
        created_at: float | None = None,
    ) -> tuple[StructuredFact, bool]:
        """Shared remember/add core. Returns (fact, True) iff newly stored."""
        text = (text or "").strip()
        if not text:
            raise ValueError("cannot remember an empty fact")
        scope = _normalize_scope(scope)
        trust = (trust or "").strip().lower()
        now = time.time()
        with self._lock:
            existing = self._find_active_dedupe(_normalize_text(text), scope)
            if existing is not None:
                if trust not in RECALLABLE_TRUST_TIERS and existing.trusted_for_recall:
                    self._conn.execute(
                        "UPDATE facts SET trust = ?, updated_at = ? WHERE id = ?",
                        (trust or TRUST_UNTRUSTED, now, existing.id),
                    )
                    self._conn.commit()
                    existing.trust = trust or TRUST_UNTRUSTED
                    existing.updated_at = now
                return existing, False
            fact = StructuredFact(
                id=uuid.uuid4().hex,
                text=text,
                source=source,
                provenance=provenance,
                created_at=created_at if created_at is not None else now,
                updated_at=now,
                scope=scope,
                status=STATUS_ACTIVE,
                trust=trust,
            )
            self._insert_row(fact)
            self._enforce_cap_locked(now)
            self._conn.commit()
            return fact, True

    def add_with_trust(self, text: str, source: str = "", trust: str = "") -> bool:
        return self.add(text, source=source, trust=trust)

    def correct(
        self,
        fact_id: str,
        new_text: str,
        *,
        source: str = "",
        provenance: str = "",
        scope: str | None = None,
        trust: str = "",
    ) -> StructuredFact:
        """Replace fact *fact_id* with a new fact carrying *new_text*.

        The old fact is marked superseded (never returned by retrieval) and
        points at its replacement via ``superseded_by``. If *new_text*
        duplicates another active fact, the old fact is superseded in favour
        of that existing fact instead of creating a second copy.
        """
        new_text = (new_text or "").strip()
        if not new_text:
            raise ValueError("correction text must not be empty")
        now = time.time()
        with self._lock:
            old = self.get(fact_id)
            if old is None:
                raise KeyError(f"no fact with id {fact_id!r}")
            if old.status != STATUS_ACTIVE:
                raise ValueError(f"fact {fact_id!r} is {old.status}, not active")
            target_scope = _normalize_scope(scope) if scope else old.scope
            duplicate = self._find_active_dedupe(
                _normalize_text(new_text), target_scope, exclude_id=old.id
            )
            if duplicate is not None:
                replacement = duplicate
            else:
                replacement = StructuredFact(
                    id=uuid.uuid4().hex,
                    text=new_text,
                    source=source or old.source,
                    provenance=provenance or old.provenance,
                    created_at=now,
                    updated_at=now,
                    scope=target_scope,
                    status=STATUS_ACTIVE,
                    trust=(trust or "").strip().lower(),
                )
                self._insert_row(replacement)
            self._conn.execute(
                "UPDATE facts SET status = ?, superseded_by = ?,"
                " updated_at = ? WHERE id = ?",
                (STATUS_SUPERSEDED, replacement.id, now, old.id),
            )
            self._enforce_cap_locked(now)
            self._conn.commit()
            return replacement

    def forget(self, fact_id: str, *, reason: str = "forget") -> bool:
        """Hard-delete fact *fact_id* from facts AND the FTS index.

        The FTS5 delete trigger fires in the same transaction. Only the fact
        id (never its text) is kept in ``deletion_log`` for audit.
        """
        now = time.time()
        with self._lock:
            cur = self._conn.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
            if cur.rowcount == 0:
                return False
            self._conn.execute(
                "INSERT INTO deletion_log (fact_id, deleted_at, reason)"
                " VALUES (?, ?, ?)",
                (fact_id, now, reason),
            )
            self._conn.commit()
            return True

    def get(self, fact_id: str) -> StructuredFact | None:
        with self._lock:
            row = self._conn.execute(
                f"SELECT {self._COLUMNS} FROM facts WHERE id = ?", (fact_id,)
            ).fetchone()
            return self._row_to_fact(row) if row else None

    def list(
        self, scope: str | None = None, *, include_superseded: bool = False
    ) -> List[StructuredFact]:
        """Return facts oldest first, active only unless *include_superseded*."""
        with self._lock:
            sql = f"SELECT {self._COLUMNS} FROM facts"
            params: list[Any] = []
            clauses = []
            if scope is not None:
                clauses.append("scope = ?")
                params.append(_normalize_scope(scope))
            if not include_superseded:
                clauses.append("status = ?")
                params.append(STATUS_ACTIVE)
            if clauses:
                sql += " WHERE " + " AND ".join(clauses)
            sql += " ORDER BY created_at ASC, rowid ASC"
            return [
                self._row_to_fact(row)
                for row in self._conn.execute(sql, params).fetchall()
            ]

    def retrieve(
        self,
        query: str,
        *,
        scope: str | None = None,
        top_k: int = 5,
    ) -> List[ScoredFact]:
        """Ranked retrieval over active, recallable facts.

        score = 0.6 * text + 0.3 * recency + 0.1 * exact-scope bonus, where
        text is a sigmoid of the FTS5 BM25 rank and recency is exponential
        decay with a 30-day half-life. A scoped query also sees global facts.
        """
        match = _fts_query(query)
        if not match:
            return []
        now = time.time()
        half_life = RECENCY_HALF_LIFE_DAYS * 86400.0
        requested_scope = _normalize_scope(scope) if scope else None
        with self._lock:
            sql = (
                f"SELECT {self._COLUMNS}, bm25(facts_fts) AS rank"
                " FROM facts JOIN facts_fts ON facts_fts.rowid = facts.rowid"
                " WHERE facts_fts MATCH ? AND facts.status = ?"
            )
            params: list[Any] = [match, STATUS_ACTIVE]
            if requested_scope is not None:
                sql += " AND (facts.scope = ? OR facts.scope = ?)"
                params.extend([requested_scope, SCOPE_GLOBAL])
            # Trust is stored raw; filter in Python against the recallable
            # set so legacy "" rows stay recallable (as in LocalFactStore).
            rows = self._conn.execute(sql, params).fetchall()
        scored: List[ScoredFact] = []
        for row in rows:
            fact = self._row_to_fact(row)
            if not fact.trusted_for_recall:
                continue
            rank = float(row[-1])
            text_score = 1.0 / (1.0 + math.exp(rank))
            age = max(0.0, now - fact.created_at)
            recency = 0.5 ** (age / half_life)
            scope_bonus = (
                SCOPE_BONUS
                if requested_scope is not None
                and requested_scope != SCOPE_GLOBAL
                and fact.scope == requested_scope
                else 0.0
            )
            score = TEXT_WEIGHT * text_score + RECENCY_WEIGHT * recency + scope_bonus
            scored.append(ScoredFact(fact=fact, score=score))
        scored.sort(key=lambda hit: (-hit.score, hit.fact.created_at))
        return scored[: max(0, top_k)]

    def summaries_by_source(self) -> List[Dict[str, Any]]:
        """Per-source summaries: active count + latest fact, source-linked."""
        summaries: Dict[str, Dict[str, Any]] = {}
        for fact in self.list():
            entry = summaries.get(fact.source)
            if entry is None or fact.created_at >= float(entry["latest_at"]):
                summaries[fact.source] = {
                    "source": fact.source,
                    "count": int(entry["count"]) + 1 if entry else 1,
                    "latest_text": fact.text,
                    "latest_at": fact.created_at,
                }
            else:
                entry["count"] = int(entry["count"]) + 1
        return sorted(
            summaries.values(), key=lambda e: (-int(e["count"]), str(e["source"]))
        )

    def prune_log(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                {"fact_id": fid, "pruned_at": ts, "reason": reason}
                for fid, ts, reason in self._conn.execute(
                    "SELECT fact_id, pruned_at, reason FROM prune_log"
                    " ORDER BY pruned_at ASC"
                ).fetchall()
            ]

    def deletion_log(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                {"fact_id": fid, "deleted_at": ts, "reason": reason}
                for fid, ts, reason in self._conn.execute(
                    "SELECT fact_id, deleted_at, reason FROM deletion_log"
                    " ORDER BY deleted_at ASC"
                ).fetchall()
            ]

    def set_trust(self, index: int, trust: str) -> bool:
        trust = (trust or "").strip().lower()
        if trust not in _KNOWN_TRUST_TIERS:
            raise ValueError(f"Unknown fact trust tier: {trust!r}")
        with self._lock:
            facts = self.list()
            if not 0 <= index < len(facts):
                return False
            self._conn.execute(
                "UPDATE facts SET trust = ?, updated_at = ? WHERE id = ?",
                (trust, time.time(), facts[index].id),
            )
            self._conn.commit()
        return True

    def promote_reviewed(self, index: int, expected_text: str) -> bool:
        with self._lock:
            facts = self.list()
            if not 0 <= index < len(facts):
                return False
            fact = facts[index]
            if fact.text != expected_text or fact.trusted_for_recall:
                return False
            self._conn.execute(
                "UPDATE facts SET trust = ?, updated_at = ? WHERE id = ?",
                (TRUST_TRUSTED, time.time(), fact.id),
            )
            self._conn.commit()
        return True

    def clear(self) -> int:
        with self._lock:
            removed = self._conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
            self._conn.execute("DELETE FROM facts")
            self._conn.execute("DELETE FROM prune_log")
            self._conn.execute("DELETE FROM deletion_log")
            self._conn.commit()
            return int(removed)

    def count(self) -> int:
        with self._lock:
            return self._active_count_locked()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @property
    def path(self) -> Path:
        """Filesystem location of the SQLite database."""
        return self._path


__all__ = [
    "RECENCY_HALF_LIFE_DAYS",
    "SCOPE_BONUS",
    "SCOPE_GLOBAL",
    "STATUS_ACTIVE",
    "STATUS_SUPERSEDED",
    "ScoredFact",
    "SqliteFactStore",
    "StructuredFact",
]
