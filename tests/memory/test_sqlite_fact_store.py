"""Tests for the SQLite + FTS5 structured-fact store (MEMORY v1).

All fixture facts are invented.
"""

from __future__ import annotations

import sqlite3
import time

import pytest

from openjarvis.memory.sqlite_facts import (
    SCOPE_GLOBAL,
    STATUS_ACTIVE,
    STATUS_SUPERSEDED,
    SqliteFactStore,
)
from openjarvis.memory.store import TRUST_UNTRUSTED, create_fact_store


def test_remember_and_get(tmp_path):
    store = SqliteFactStore(tmp_path / "facts.db")
    fact = store.remember(
        "Mira Chen prefers tea over coffee",
        source="chat",
        provenance="turn-1",
        scope="global",
    )
    assert fact.text == "Mira Chen prefers tea over coffee"
    assert fact.source == "chat"
    assert fact.provenance == "turn-1"
    assert fact.scope == SCOPE_GLOBAL
    assert fact.status == STATUS_ACTIVE
    assert store.get(fact.id) == fact
    assert store.count() == 1
    store.close()


def test_add_returns_true_only_for_new_facts(tmp_path):
    store = SqliteFactStore(tmp_path / "facts.db")
    assert store.add("Mira Chen prefers tea over coffee") is True
    assert store.add("Mira Chen prefers tea over coffee") is False
    assert store.add("  ") is False
    assert store.add("") is False
    store.close()


def test_dedupe_is_case_and_whitespace_insensitive(tmp_path):
    store = SqliteFactStore(tmp_path / "facts.db")
    first = store.remember("Mira Chen prefers tea")
    second = store.remember("  mira   chen PREFERS tea ")
    assert second.id == first.id
    assert store.count() == 1
    store.close()


def test_dedupe_is_per_scope(tmp_path):
    store = SqliteFactStore(tmp_path / "facts.db")
    a = store.remember("Atlas launch date is June twelfth", scope="global")
    b = store.remember("Atlas launch date is June twelfth", scope="project:atlas")
    assert a.id != b.id
    assert store.count() == 2
    store.close()


def test_remember_rejects_blank_text(tmp_path):
    store = SqliteFactStore(tmp_path / "facts.db")
    with pytest.raises(ValueError):
        store.remember("   ")
    store.close()


def test_list_oldest_first_and_scope_filter(tmp_path):
    store = SqliteFactStore(tmp_path / "facts.db")
    now = time.time()
    store.remember("first fact", created_at=now - 10)
    store.remember("second fact", scope="project:atlas", created_at=now - 5)
    store.remember("third fact", created_at=now)
    texts = [f.text for f in store.list()]
    assert texts == ["first fact", "second fact", "third fact"]
    assert [f.text for f in store.list(scope="project:atlas")] == ["second fact"]
    store.close()


def test_correct_supersedes_old_fact(tmp_path):
    store = SqliteFactStore(tmp_path / "facts.db")
    old = store.remember("The office printer is on the third floor")
    new = store.correct(old.id, "The office printer is on the fourth floor")
    assert new.text == "The office printer is on the fourth floor"
    assert new.id != old.id
    stored_old = store.get(old.id)
    assert stored_old.status == STATUS_SUPERSEDED
    assert stored_old.superseded_by == new.id
    # Superseded facts are never returned by retrieval or list().
    assert [f.text for f in store.list()] == [new.text]
    assert [h.fact.text for h in store.retrieve("printer third floor")] == []
    assert [h.fact.text for h in store.retrieve("printer fourth floor")] == [new.text]
    # ...but remain visible with include_superseded for audit.
    assert len(store.list(include_superseded=True)) == 2
    store.close()


def test_correct_to_existing_duplicate_supersedes_without_copy(tmp_path):
    store = SqliteFactStore(tmp_path / "facts.db")
    old = store.remember("The office printer is on the third floor")
    existing = store.remember("The office printer is on the fourth floor")
    replacement = store.correct(old.id, "The office printer is on the fourth floor")
    assert replacement.id == existing.id
    assert store.count() == 1
    store.close()


def test_correct_unknown_or_superseded_fact_errors(tmp_path):
    store = SqliteFactStore(tmp_path / "facts.db")
    with pytest.raises(KeyError):
        store.correct("no-such-id", "something else")
    old = store.remember("first version")
    store.correct(old.id, "second version")
    with pytest.raises(ValueError):
        store.correct(old.id, "third version")
    with pytest.raises(ValueError):
        store.correct(store.list()[0].id, "   ")
    store.close()


def test_forget_hard_deletes_from_facts_and_fts(tmp_path):
    db_path = tmp_path / "facts.db"
    store = SqliteFactStore(db_path)
    fact = store.remember("The pantry stocks oat milk")
    assert store.forget(fact.id) is True
    assert store.forget(fact.id) is False  # already gone
    assert store.get(fact.id) is None
    assert store.count() == 0
    assert store.retrieve("oat milk") == []
    store.close()
    # Direct FTS check: no row for the deleted text survives in the index.
    conn = sqlite3.connect(str(db_path))
    try:
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM facts_fts WHERE facts_fts MATCH 'oat'"
            ).fetchone()[0]
            == 0
        )
    finally:
        conn.close()


def test_forget_logs_id_only(tmp_path):
    store = SqliteFactStore(tmp_path / "facts.db")
    fact = store.remember("The pantry stocks oat milk")
    store.forget(fact.id)
    log = store.deletion_log()
    assert len(log) == 1
    assert log[0]["fact_id"] == fact.id
    assert "oat milk" not in str(log)
    store.close()


def test_retrieve_empty_query_returns_nothing(tmp_path):
    store = SqliteFactStore(tmp_path / "facts.db")
    store.remember("Mira Chen prefers tea")
    assert store.retrieve("") == []
    assert store.retrieve("   ") == []
    store.close()


def test_retrieve_requires_all_terms_and_filters_untrusted(tmp_path):
    store = SqliteFactStore(tmp_path / "facts.db")
    store.remember("Mira Chen prefers tea over coffee")
    store.remember("Mira Chen owns a red bicycle")
    hits = store.retrieve("Mira bicycle")
    assert [h.fact.text for h in hits] == ["Mira Chen owns a red bicycle"]
    quarantined = store.remember("Mira Chen hides the spare key", trust=TRUST_UNTRUSTED)
    assert quarantined.trusted_for_recall is False
    assert store.retrieve("spare key") == []
    store.close()


def test_retrieve_scope_sees_global_but_not_other_scopes(tmp_path):
    store = SqliteFactStore(tmp_path / "facts.db")
    store.remember("Project Atlas launches on June twelfth", scope="project:atlas")
    store.remember("Project Beacon launches on July fourth", scope="project:beacon")
    store.remember("The office is closed on holidays", scope="global")
    atlas = [h.fact.text for h in store.retrieve("launches", scope="project:atlas")]
    assert atlas == ["Project Atlas launches on June twelfth"]
    beacon = [h.fact.text for h in store.retrieve("launches", scope="project:beacon")]
    assert beacon == ["Project Beacon launches on July fourth"]
    # Global facts are visible from any scope.
    assert store.retrieve("holidays", scope="project:atlas")
    store.close()


def test_retrieve_recency_beats_age_when_text_ties(tmp_path):
    store = SqliteFactStore(tmp_path / "facts.db")
    now = time.time()
    store.remember(
        "Zara keeps a blue notebook on her desk", created_at=now - 100 * 86400
    )
    store.remember("Zara keeps a red notebook on her desk", created_at=now)
    hits = store.retrieve("notebook")
    assert hits[0].fact.text == "Zara keeps a red notebook on her desk"
    assert hits[-1].fact.text == "Zara keeps a blue notebook on her desk"
    store.close()


def test_retrieve_scope_bonus_beats_global_twin(tmp_path):
    store = SqliteFactStore(tmp_path / "facts.db")
    now = time.time()
    store.remember("Atlas launch date is June twelfth", scope="global", created_at=now)
    store.remember(
        "Atlas launch date is June twelfth",
        scope="project:atlas",
        created_at=now,
    )
    hits = store.retrieve("Atlas launch date", scope="project:atlas")
    assert hits[0].fact.scope == "project:atlas"
    store.close()


def test_retention_cap_prunes_oldest_and_logs(tmp_path):
    store = SqliteFactStore(tmp_path / "facts.db", max_facts=2)
    now = time.time()
    old = store.remember("oldest fact", created_at=now - 30)
    store.remember("middle fact", created_at=now - 20)
    store.remember("newest fact", created_at=now - 10)
    assert store.count() == 2
    assert store.get(old.id) is None
    assert [f.text for f in store.list()] == ["middle fact", "newest fact"]
    log = store.prune_log()
    assert [entry["fact_id"] for entry in log] == [old.id]
    assert log[0]["reason"] == "retention-cap"
    assert "oldest fact" not in str(log)
    store.close()


def test_invalid_max_facts_rejected(tmp_path):
    with pytest.raises(ValueError):
        SqliteFactStore(tmp_path / "facts.db", max_facts=0)


def test_summaries_by_source(tmp_path):
    store = SqliteFactStore(tmp_path / "facts.db")
    now = time.time()
    store.remember("chat fact one", source="chat", created_at=now - 10)
    store.remember("chat fact two", source="chat", created_at=now)
    store.remember("notes fact", source="notes", created_at=now - 5)
    summaries = store.summaries_by_source()
    assert summaries[0]["source"] == "chat"
    assert summaries[0]["count"] == 2
    assert summaries[0]["latest_text"] == "chat fact two"
    assert summaries[1] == {
        "source": "notes",
        "count": 1,
        "latest_text": "notes fact",
        "latest_at": pytest.approx(now - 5),
    }
    store.close()


def test_trust_promotion_and_set_trust(tmp_path):
    store = SqliteFactStore(tmp_path / "facts.db")
    store.remember("quarantined fact", trust=TRUST_UNTRUSTED)
    assert store.retrieve("quarantined") == []
    assert store.promote_reviewed(0, "quarantined fact") is True
    assert store.retrieve("quarantined")[0].fact.trusted_for_recall is True
    assert store.promote_reviewed(0, "quarantined fact") is False  # already trusted
    assert store.promote_reviewed(0, "wrong text") is False
    assert store.set_trust(0, TRUST_UNTRUSTED) is True
    assert store.set_trust(5, TRUST_UNTRUSTED) is False
    with pytest.raises(ValueError):
        store.set_trust(0, "bogus-tier")
    store.close()


def test_clear_removes_everything(tmp_path):
    store = SqliteFactStore(tmp_path / "facts.db")
    store.remember("fact one")
    old = store.remember("fact two")
    store.correct(old.id, "fact two revised")
    store.forget(store.list()[0].id)
    assert store.clear() == 2  # one superseded + one active remain
    assert store.count() == 0
    assert store.list(include_superseded=True) == []
    assert store.retrieve("fact") == []
    store.close()


def test_persists_across_reopen(tmp_path):
    db_path = tmp_path / "facts.db"
    store = SqliteFactStore(db_path)
    fact = store.remember("Mira Chen prefers tea")
    store.close()
    reopened = SqliteFactStore(db_path)
    assert [f.text for f in reopened.list()] == ["Mira Chen prefers tea"]
    assert reopened.get(fact.id) is not None
    assert reopened.retrieve("tea")[0].fact.id == fact.id
    reopened.close()


def test_create_fact_store_sqlite_facts_backend(tmp_path):
    store = create_fact_store("sqlite-facts", path=tmp_path / "facts.db", max_facts=10)
    assert isinstance(store, SqliteFactStore)
    assert store.add("Mira Chen prefers tea") is True
    store.close()
