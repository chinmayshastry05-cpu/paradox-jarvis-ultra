"""DEVELOPER benchmark for MEMORY v1 retrieval — NOT proof of lifelong perfect recall.

This is a small, fixed, developer-run regression check: a seeded store of
~30 invented facts plus 100 scripted queries with EXPLICIT expected answers.
It guards the semantics that matter (correction supersedes, deletion removes
from every index, scopes filter) against regressions. It says nothing about
recall over months of real conversations, thousands of facts, paraphrase, or
ambiguous queries — do not cite it as evidence of lifelong perfect recall.

All people, projects, and facts below are invented for the test.
"""

from __future__ import annotations

import sqlite3
import time

import pytest

from openjarvis.memory.sqlite_facts import SqliteFactStore

DEVELOPER_BENCHMARK_DISCLAIMER = (
    "DEVELOPER benchmark only — NOT proof of lifelong perfect recall."
)

_DAY = 86400.0

# (key, text, source, scope, age in days)
SEEDS = [
    ("F01", "Mira Chen prefers tea over coffee", "chat", "global", 40),
    ("F02", "Dev Patel is allergic to peanuts", "notes", "global", 35),
    ("F03", "Zara Lindqvist works in the Berlin office", "profile", "global", 30),
    ("F04", "Mira Chen speaks fluent Kannada and English", "profile", "global", 25),
    ("F05", "Dev Patel runs five kilometers every morning", "chat", "global", 20),
    ("F06", "Zara Lindqvist plays violin on weekends", "chat", "global", 15),
    ("F07", "Mira Chen dislikes morning meetings before nine", "chat", "global", 10),
    ("F08", "Dev Patel owns a red bicycle", "notes", "global", 5),
    ("F09", "Zara Lindqvist is learning pottery", "chat", "global", 2),
    ("F10", "Mira Chen keeps a cactus on her desk", "notes", "global", 1),
    ("A01", "Project Atlas launches on June twelfth", "doc", "project:atlas", 29),
    ("A02", "Project Atlas uses Postgres for storage", "doc", "project:atlas", 24),
    (
        "A03",
        "Project Atlas standup is at ten in the morning",
        "chat",
        "project:atlas",
        19,
    ),
    ("A04", "Project Atlas lead reviewer is Dev Patel", "doc", "project:atlas", 14),
    (
        "A05",
        "Project Atlas budget is eighty thousand credits",
        "doc",
        "project:atlas",
        9,
    ),
    ("B01", "Project Beacon launches on July fourth", "doc", "project:beacon", 31),
    ("B02", "Project Beacon uses SQLite for storage", "doc", "project:beacon", 26),
    (
        "B03",
        "Project Beacon standup is at eleven in the morning",
        "chat",
        "project:beacon",
        21,
    ),
    (
        "B04",
        "Project Beacon lead reviewer is Zara Lindqvist",
        "doc",
        "project:beacon",
        16,
    ),
    ("R01", "Zara keeps a blue notebook on her desk", "notes", "global", 100),
    ("R02", "Zara keeps a red notebook on her desk", "notes", "global", 0),
    ("R03", "Dev keeps a green notebook on his desk", "notes", "global", 50),
    ("R04", "Atlas launch date is June twelfth", "doc", "global", 10),
    ("R05", "Atlas launch date is June twelfth", "doc", "project:atlas", 10),
    ("C01", "The office printer is on the third floor", "chat", "global", 12),
    ("C02", "Team lunch is on Fridays at noon", "chat", "global", 11),
    ("C03", "The backup server is named heron", "notes", "global", 8),
    ("D01", "The pantry stocks oat milk", "chat", "global", 7),
    ("D02", "The meeting room has a whiteboard wall", "notes", "global", 6),
    ("D03", "The office dog is named Biscuit", "chat", "global", 5),
]

# Each case: id, query, scope, setup ops, expectation.
# Setup ops: ("correct", key, new_text) -> creates key + "'"; ("forget", key).
# Expectations: ("top", key) | ("absent", key) | ("contains", key) |
# ("fts_absent", term, key) — term gone from the FTS index AND key not retrieved.
CASES = [
    # -- A. Direct retrieval (30) -------------------------------------------
    {
        "id": "A01",
        "query": "tea coffee",
        "scope": None,
        "setup": [],
        "expect": ("top", "F01"),
    },
    {
        "id": "A02",
        "query": "allergic peanuts",
        "scope": None,
        "setup": [],
        "expect": ("top", "F02"),
    },
    {
        "id": "A03",
        "query": "Berlin office",
        "scope": None,
        "setup": [],
        "expect": ("top", "F03"),
    },
    {
        "id": "A04",
        "query": "fluent Kannada English",
        "scope": None,
        "setup": [],
        "expect": ("top", "F04"),
    },
    {
        "id": "A05",
        "query": "five kilometers morning",
        "scope": None,
        "setup": [],
        "expect": ("top", "F05"),
    },
    {
        "id": "A06",
        "query": "violin weekends",
        "scope": None,
        "setup": [],
        "expect": ("top", "F06"),
    },
    {
        "id": "A07",
        "query": "morning meetings nine",
        "scope": None,
        "setup": [],
        "expect": ("top", "F07"),
    },
    {
        "id": "A08",
        "query": "red bicycle",
        "scope": None,
        "setup": [],
        "expect": ("top", "F08"),
    },
    {
        "id": "A09",
        "query": "learning pottery",
        "scope": None,
        "setup": [],
        "expect": ("top", "F09"),
    },
    {
        "id": "A10",
        "query": "cactus desk",
        "scope": None,
        "setup": [],
        "expect": ("top", "F10"),
    },
    {
        "id": "A11",
        "query": "Atlas launches June",
        "scope": None,
        "setup": [],
        "expect": ("top", "A01"),
    },
    {
        "id": "A12",
        "query": "Atlas Postgres storage",
        "scope": None,
        "setup": [],
        "expect": ("top", "A02"),
    },
    {
        "id": "A13",
        "query": "Atlas standup ten",
        "scope": None,
        "setup": [],
        "expect": ("top", "A03"),
    },
    {
        "id": "A14",
        "query": "Atlas lead reviewer Dev",
        "scope": None,
        "setup": [],
        "expect": ("top", "A04"),
    },
    {
        "id": "A15",
        "query": "Atlas budget eighty thousand",
        "scope": None,
        "setup": [],
        "expect": ("top", "A05"),
    },
    {
        "id": "A16",
        "query": "Beacon launches July",
        "scope": None,
        "setup": [],
        "expect": ("top", "B01"),
    },
    {
        "id": "A17",
        "query": "Beacon SQLite storage",
        "scope": None,
        "setup": [],
        "expect": ("top", "B02"),
    },
    {
        "id": "A18",
        "query": "Beacon standup eleven",
        "scope": None,
        "setup": [],
        "expect": ("top", "B03"),
    },
    {
        "id": "A19",
        "query": "Beacon lead reviewer Zara",
        "scope": None,
        "setup": [],
        "expect": ("top", "B04"),
    },
    {
        "id": "A20",
        "query": "notebook",
        "scope": None,
        "setup": [],
        "expect": ("top", "R02"),
    },
    {
        "id": "A21",
        "query": "green notebook",
        "scope": None,
        "setup": [],
        "expect": ("top", "R03"),
    },
    {
        "id": "A22",
        "query": "Atlas launch date",
        "scope": "project:atlas",
        "setup": [],
        "expect": ("top", "R05"),
    },
    {
        "id": "A23",
        "query": "Atlas launch date",
        "scope": "global",
        "setup": [],
        "expect": ("top", "R04"),
    },
    {
        "id": "A24",
        "query": "printer third floor",
        "scope": None,
        "setup": [],
        "expect": ("top", "C01"),
    },
    {
        "id": "A25",
        "query": "lunch Fridays noon",
        "scope": None,
        "setup": [],
        "expect": ("top", "C02"),
    },
    {
        "id": "A26",
        "query": "backup server heron",
        "scope": None,
        "setup": [],
        "expect": ("top", "C03"),
    },
    {
        "id": "A27",
        "query": "pantry oat milk",
        "scope": None,
        "setup": [],
        "expect": ("top", "D01"),
    },
    {
        "id": "A28",
        "query": "whiteboard wall",
        "scope": None,
        "setup": [],
        "expect": ("top", "D02"),
    },
    {
        "id": "A29",
        "query": "dog Biscuit",
        "scope": None,
        "setup": [],
        "expect": ("top", "D03"),
    },
    {
        "id": "A30",
        "query": "desk",
        "scope": None,
        "setup": [],
        "expect": ("top", "R02"),
    },
    # -- B. Contradiction / correction (20) ---------------------------------
    {
        "id": "B01",
        "query": "printer fourth floor",
        "scope": None,
        "setup": [("correct", "C01", "The office printer is on the fourth floor")],
        "expect": ("top", "C01'"),
    },
    {
        "id": "B02",
        "query": "printer third floor",
        "scope": None,
        "setup": [("correct", "C01", "The office printer is on the fourth floor")],
        "expect": ("absent", "C01"),
    },
    {
        "id": "B03",
        "query": "printer",
        "scope": None,
        "setup": [("correct", "C01", "The office printer is on the fourth floor")],
        "expect": ("top", "C01'"),
    },
    {
        "id": "B04",
        "query": "fourth floor",
        "scope": None,
        "setup": [("correct", "C01", "The office printer is on the fourth floor")],
        "expect": ("top", "C01'"),
    },
    {
        "id": "B05",
        "query": "lunch Thursdays noon",
        "scope": None,
        "setup": [("correct", "C02", "Team lunch is on Thursdays at noon")],
        "expect": ("top", "C02'"),
    },
    {
        "id": "B06",
        "query": "lunch Fridays noon",
        "scope": None,
        "setup": [("correct", "C02", "Team lunch is on Thursdays at noon")],
        "expect": ("absent", "C02"),
    },
    {
        "id": "B07",
        "query": "lunch",
        "scope": None,
        "setup": [("correct", "C02", "Team lunch is on Thursdays at noon")],
        "expect": ("top", "C02'"),
    },
    {
        "id": "B08",
        "query": "Thursdays noon",
        "scope": None,
        "setup": [("correct", "C02", "Team lunch is on Thursdays at noon")],
        "expect": ("top", "C02'"),
    },
    {
        "id": "B09",
        "query": "backup server egret",
        "scope": None,
        "setup": [("correct", "C03", "The backup server is named egret")],
        "expect": ("top", "C03'"),
    },
    {
        "id": "B10",
        "query": "backup server heron",
        "scope": None,
        "setup": [("correct", "C03", "The backup server is named egret")],
        "expect": ("absent", "C03"),
    },
    {
        "id": "B11",
        "query": "backup server",
        "scope": None,
        "setup": [("correct", "C03", "The backup server is named egret")],
        "expect": ("top", "C03'"),
    },
    {
        "id": "B12",
        "query": "egret",
        "scope": None,
        "setup": [("correct", "C03", "The backup server is named egret")],
        "expect": ("top", "C03'"),
    },
    {
        "id": "B13",
        "query": "Mira prefers coffee",
        "scope": None,
        "setup": [("correct", "F01", "Mira Chen prefers coffee over tea")],
        "expect": ("top", "F01'"),
    },
    {
        "id": "B14",
        "query": "Mira prefers tea",
        "scope": None,
        "setup": [("correct", "F01", "Mira Chen prefers coffee over tea")],
        "expect": ("absent", "F01"),
    },
    {
        "id": "B15",
        "query": "Mira Chen prefers",
        "scope": None,
        "setup": [("correct", "F01", "Mira Chen prefers coffee over tea")],
        "expect": ("top", "F01'"),
    },
    {
        "id": "B16",
        "query": "Atlas launches twentieth",
        "scope": None,
        "setup": [("correct", "A01", "Project Atlas launches on June twentieth")],
        "expect": ("top", "A01'"),
    },
    {
        "id": "B17",
        "query": "Atlas launches twelfth",
        "scope": None,
        "setup": [("correct", "A01", "Project Atlas launches on June twentieth")],
        "expect": ("absent", "A01"),
    },
    {
        "id": "B18",
        "query": "Atlas launches",
        "scope": None,
        "setup": [("correct", "A01", "Project Atlas launches on June twentieth")],
        "expect": ("top", "A01'"),
    },
    {
        "id": "B19",
        "query": "Beacon Postgres storage",
        "scope": None,
        "setup": [("correct", "B02", "Project Beacon uses Postgres for storage")],
        "expect": ("top", "B02'"),
    },
    {
        "id": "B20",
        "query": "Beacon SQLite storage",
        "scope": None,
        "setup": [("correct", "B02", "Project Beacon uses Postgres for storage")],
        "expect": ("absent", "B02"),
    },
    # -- C. Deletion (15) ----------------------------------------------------
    {
        "id": "C01",
        "query": "pantry oat milk",
        "scope": None,
        "setup": [("forget", "D01")],
        "expect": ("absent", "D01"),
    },
    {
        "id": "C02",
        "query": "oat milk",
        "scope": None,
        "setup": [("forget", "D01")],
        "expect": ("absent", "D01"),
    },
    {
        "id": "C03",
        "query": "whiteboard wall",
        "scope": None,
        "setup": [("forget", "D02")],
        "expect": ("absent", "D02"),
    },
    {
        "id": "C04",
        "query": "meeting room",
        "scope": None,
        "setup": [("forget", "D02")],
        "expect": ("absent", "D02"),
    },
    {
        "id": "C05",
        "query": "dog Biscuit",
        "scope": None,
        "setup": [("forget", "D03")],
        "expect": ("absent", "D03"),
    },
    {
        "id": "C06",
        "query": "Biscuit",
        "scope": None,
        "setup": [("forget", "D03")],
        "expect": ("absent", "D03"),
    },
    {
        "id": "C07",
        "query": "cactus desk",
        "scope": None,
        "setup": [("forget", "F10")],
        "expect": ("absent", "F10"),
    },
    {
        "id": "C08",
        "query": "cactus",
        "scope": None,
        "setup": [("forget", "F10")],
        "expect": ("absent", "F10"),
    },
    {
        "id": "C09",
        "query": "Atlas budget",
        "scope": None,
        "setup": [("forget", "A05")],
        "expect": ("absent", "A05"),
    },
    {
        "id": "C10",
        "query": "eighty thousand",
        "scope": None,
        "setup": [("forget", "A05")],
        "expect": ("absent", "A05"),
    },
    {
        "id": "C11",
        "query": "Beacon lead reviewer",
        "scope": None,
        "setup": [("forget", "B04")],
        "expect": ("absent", "B04"),
    },
    {
        "id": "C12",
        "query": "Beacon Zara",
        "scope": None,
        "setup": [("forget", "B04")],
        "expect": ("absent", "B04"),
    },
    {
        "id": "C13",
        "query": "tea coffee",
        "scope": None,
        "setup": [("forget", "D01")],
        "expect": ("top", "F01"),
    },
    {
        "id": "C14",
        "query": "pantry oat milk",
        "scope": None,
        "setup": [("forget", "D02"), ("forget", "D03")],
        "expect": ("top", "D01"),
    },
    {
        "id": "C15",
        "query": "learning pottery",
        "scope": None,
        "setup": [("forget", "F09")],
        "expect": ("fts_absent", "pottery", "F09"),
    },
    # -- D. Scope (20) --------------------------------------------------------
    {
        "id": "D01",
        "query": "Atlas launches",
        "scope": "project:atlas",
        "setup": [],
        "expect": ("top", "A01"),
    },
    {
        "id": "D02",
        "query": "launches",
        "scope": "project:atlas",
        "setup": [],
        "expect": ("top", "A01"),
    },
    {
        "id": "D03",
        "query": "launches",
        "scope": "project:beacon",
        "setup": [],
        "expect": ("top", "B01"),
    },
    {
        "id": "D04",
        "query": "launches",
        "scope": None,
        "setup": [],
        "expect": ("top", "A01"),
    },
    {
        "id": "D05",
        "query": "standup",
        "scope": "project:atlas",
        "setup": [],
        "expect": ("top", "A03"),
    },
    {
        "id": "D06",
        "query": "standup",
        "scope": "project:beacon",
        "setup": [],
        "expect": ("top", "B03"),
    },
    {
        "id": "D07",
        "query": "standup",
        "scope": None,
        "setup": [],
        "expect": ("top", "A03"),
    },
    {
        "id": "D08",
        "query": "storage",
        "scope": "project:atlas",
        "setup": [],
        "expect": ("top", "A02"),
    },
    {
        "id": "D09",
        "query": "storage",
        "scope": "project:beacon",
        "setup": [],
        "expect": ("top", "B02"),
    },
    {
        "id": "D10",
        "query": "storage",
        "scope": None,
        "setup": [],
        "expect": ("top", "A02"),
    },
    {
        "id": "D11",
        "query": "reviewer",
        "scope": "project:atlas",
        "setup": [],
        "expect": ("top", "A04"),
    },
    {
        "id": "D12",
        "query": "reviewer",
        "scope": "project:beacon",
        "setup": [],
        "expect": ("top", "B04"),
    },
    {
        "id": "D13",
        "query": "reviewer",
        "scope": None,
        "setup": [],
        "expect": ("top", "A04"),
    },
    {
        "id": "D14",
        "query": "Mira Chen",
        "scope": None,
        "setup": [],
        "expect": ("top", "F10"),
    },
    {
        "id": "D15",
        "query": "Mira Chen",
        "scope": "project:atlas",
        "setup": [],
        "expect": ("top", "F10"),
    },
    {
        "id": "D16",
        "query": "Zara",
        "scope": "project:atlas",
        "setup": [],
        "expect": ("absent", "B04"),
    },
    {
        "id": "D17",
        "query": "Zara",
        "scope": "project:beacon",
        "setup": [],
        "expect": ("top", "B04"),
    },
    {
        "id": "D18",
        "query": "Dev Patel",
        "scope": "project:beacon",
        "setup": [],
        "expect": ("absent", "A04"),
    },
    {
        "id": "D19",
        "query": "Atlas",
        "scope": "project:beacon",
        "setup": [],
        "expect": ("absent", "A01"),
    },
    {
        "id": "D20",
        "query": "Atlas",
        "scope": "project:atlas",
        "setup": [],
        "expect": ("contains", "A01"),
        "top_k": 10,
    },
    # -- E. Ranking: recency + text match + scope bonus (15) ------------------
    {
        "id": "E01",
        "query": "notebook",
        "scope": None,
        "setup": [],
        "expect": ("top", "R02"),
    },
    {
        "id": "E02",
        "query": "notebook",
        "scope": None,
        "setup": [],
        "expect": ("contains", "R01"),
    },
    {
        "id": "E03",
        "query": "green notebook",
        "scope": None,
        "setup": [],
        "expect": ("top", "R03"),
    },
    {
        "id": "E04",
        "query": "blue notebook",
        "scope": None,
        "setup": [],
        "expect": ("top", "R01"),
    },
    {
        "id": "E05",
        "query": "Atlas launch date",
        "scope": "project:atlas",
        "setup": [],
        "expect": ("top", "R05"),
    },
    {
        "id": "E06",
        "query": "Atlas launch date",
        "scope": "global",
        "setup": [],
        "expect": ("top", "R04"),
    },
    {
        "id": "E07",
        "query": "Atlas launch date",
        "scope": None,
        "setup": [],
        "expect": ("contains", "R05"),
    },
    {
        "id": "E08",
        "query": "desk",
        "scope": None,
        "setup": [],
        "expect": ("top", "R02"),
    },
    {
        "id": "E09",
        "query": "desk",
        "scope": None,
        "setup": [],
        "expect": ("contains", "F10"),
    },
    {
        "id": "E10",
        "query": "morning",
        "scope": None,
        "setup": [],
        "expect": ("top", "F07"),
    },
    {
        "id": "E11",
        "query": "morning meetings",
        "scope": None,
        "setup": [],
        "expect": ("top", "F07"),
    },
    {
        "id": "E12",
        "query": "keeps",
        "scope": None,
        "setup": [],
        "expect": ("top", "R02"),
    },
    {
        "id": "E13",
        "query": "keeps",
        "scope": None,
        "setup": [],
        "expect": ("contains", "F10"),
    },
    {
        "id": "E14",
        "query": "office",
        "scope": None,
        "setup": [],
        "expect": ("contains", "C01"),
    },
    {
        "id": "E15",
        "query": "Berlin office",
        "scope": None,
        "setup": [],
        "expect": ("top", "F03"),
    },
]


def test_benchmark_has_100_cases():
    assert len(CASES) == 100
    ids = [case["id"] for case in CASES]
    assert len(set(ids)) == 100


def test_benchmark_disclaimer_is_explicit():
    assert "NOT proof of lifelong perfect recall" in DEVELOPER_BENCHMARK_DISCLAIMER


def _build_store(tmp_path, setup):
    """Seed a fresh store and apply *setup* ops. Returns (store, key->id)."""
    store = SqliteFactStore(tmp_path / "bench.db")
    now = time.time()
    ids = {}
    for key, text, source, scope, age_days in SEEDS:
        ids[key] = store.remember(
            text, source=source, scope=scope, created_at=now - age_days * _DAY
        ).id
    for op in setup:
        if op[0] == "correct":
            _, key, new_text = op
            replacement = store.correct(ids[key], new_text)
            ids[key + "'"] = replacement.id
        elif op[0] == "forget":
            store.forget(ids[op[1]])
        else:  # pragma: no cover - benchmark data error
            raise AssertionError(f"unknown setup op {op!r}")
    return store, ids


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_benchmark_case(tmp_path, case):
    store, ids = _build_store(tmp_path, case["setup"])
    try:
        hits = store.retrieve(
            case["query"], scope=case["scope"], top_k=case.get("top_k", 5)
        )
        hit_ids = [hit.fact.id for hit in hits]
        kind = case["expect"][0]
        if kind == "top":
            assert hits, f"{case['id']}: no results for {case['query']!r}"
            assert hit_ids[0] == ids[case["expect"][1]], (
                f"{case['id']}: expected top {case['expect'][1]}, "
                f"got {[h.fact.text for h in hits]}"
            )
        elif kind == "absent":
            assert ids[case["expect"][1]] not in hit_ids, (
                f"{case['id']}: {case['expect'][1]} should be absent, "
                f"got {[h.fact.text for h in hits]}"
            )
        elif kind == "contains":
            assert ids[case["expect"][1]] in hit_ids, (
                f"{case['id']}: expected {case['expect'][1]} in results, "
                f"got {[h.fact.text for h in hits]}"
            )
        elif kind == "fts_absent":
            _, term, key = case["expect"]
            assert ids[key] not in hit_ids
            conn = sqlite3.connect(str(store.path))
            try:
                count = conn.execute(
                    "SELECT COUNT(*) FROM facts_fts WHERE facts_fts MATCH ?",
                    (term,),
                ).fetchone()[0]
            finally:
                conn.close()
            assert count == 0, f"{case['id']}: term {term!r} still in FTS index"
        else:  # pragma: no cover - benchmark data error
            raise AssertionError(f"unknown expectation {case['expect']!r}")
    finally:
        store.close()
