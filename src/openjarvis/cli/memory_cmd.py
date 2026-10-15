"""``jarvis memory`` — memory management subcommands."""

from __future__ import annotations

import time
from pathlib import Path

import click
from rich.console import Console
from rich.progress import track
from rich.table import Table

from openjarvis.core.config import load_config
from openjarvis.core.registry import MemoryRegistry
from openjarvis.tools.storage.chunking import ChunkConfig
from openjarvis.tools.storage.ingest import ingest_path


def _get_backend(backend_key: str | None = None):
    """Instantiate the configured (or overridden) memory backend."""
    config = load_config()
    key = backend_key or config.memory.default_backend

    # Ensure backends are registered
    import openjarvis.tools.storage  # noqa: F401

    if not MemoryRegistry.contains(key):
        raise click.ClickException(
            f"Memory backend '{key}' not found. "
            f"Available: {', '.join(MemoryRegistry.keys())}"
        )

    if key == "sqlite":
        return MemoryRegistry.create(key, db_path=config.memory.db_path)
    return MemoryRegistry.create(key)


@click.group()
def memory() -> None:
    """Manage the memory store."""


@memory.command()
@click.argument("path")
@click.option(
    "--backend",
    "-b",
    default=None,
    help="Override the default memory backend.",
)
@click.option(
    "--chunk-size",
    default=512,
    type=click.IntRange(min=1),
    help="Chunk size in tokens.",
)
@click.option(
    "--chunk-overlap",
    default=64,
    type=click.IntRange(min=0),
    help="Overlap between chunks in tokens.",
)
def index(
    path: str,
    backend: str | None,
    chunk_size: int,
    chunk_overlap: int,
) -> None:
    """Index documents from a file or directory."""
    console = Console(stderr=True)
    target = Path(path)

    if not target.exists():
        console.print(f"[red]Path not found:[/red] {path}")
        raise SystemExit(1)

    t0 = time.time()
    cfg = ChunkConfig(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    console.print(f"[cyan]Indexing[/cyan] {path} ...")
    chunks = ingest_path(target, config=cfg)

    if not chunks:
        console.print("[yellow]No indexable content found.[/yellow]")
        return

    mem = _get_backend(backend)
    try:
        replace_source = getattr(mem, "replace_source", None)
        if callable(replace_source):
            documents_by_source = {}
            for chunk in chunks:
                documents_by_source.setdefault(chunk.source, []).append(
                    (
                        chunk.content,
                        {
                            "offset": chunk.offset,
                            "index": chunk.index,
                        },
                    )
                )
            for source, documents in track(
                documents_by_source.items(),
                description="Replacing sources...",
                console=console,
            ):
                replace_source(source, documents)
        else:
            for chunk in track(
                chunks,
                description="Storing chunks...",
                console=console,
            ):
                mem.store(
                    chunk.content,
                    source=chunk.source,
                    metadata={
                        "offset": chunk.offset,
                        "index": chunk.index,
                    },
                )
    finally:
        if hasattr(mem, "close"):
            mem.close()

    elapsed = time.time() - t0
    sources = {c.source for c in chunks}
    console.print(
        f"[green]Indexed {len(chunks)} chunks "
        f"from {len(sources)} file(s) "
        f"in {elapsed:.1f}s.[/green]"
    )


@memory.command()
@click.argument("query", nargs=-1, required=True)
@click.option(
    "--top-k",
    "-k",
    default=5,
    type=int,
    help="Number of results to return.",
)
@click.option(
    "--backend",
    "-b",
    default=None,
    help="Override the default memory backend.",
)
def search(
    query: tuple[str, ...],
    top_k: int,
    backend: str | None,
) -> None:
    """Search the memory store."""
    console = Console()
    query_text = " ".join(query)

    mem = _get_backend(backend)
    try:
        results = mem.retrieve(query_text, top_k=top_k)
    finally:
        if hasattr(mem, "close"):
            mem.close()

    if not results:
        console.print("[yellow]No results found.[/yellow]")
        return

    table = Table(title=f"Search: {query_text}")
    table.add_column("#", style="dim", width=3)
    table.add_column("Score", width=8)
    table.add_column("Source", style="cyan")
    table.add_column("Content")

    for i, r in enumerate(results, 1):
        # Truncate content for display
        preview = r.content[:200]
        if len(r.content) > 200:
            preview += "..."
        table.add_row(
            str(i),
            f"{r.score:.4f}",
            r.source or "-",
            preview,
        )

    console.print(table)


def _get_fact_store():
    """Instantiate the automatic-memory fact store from config."""
    from openjarvis.memory.store import create_fact_store

    config = load_config()
    mem = config.memory
    return create_fact_store(
        getattr(mem, "backend", "local"),
        path=getattr(mem, "facts_path", "~/.openjarvis/memory_facts.jsonl"),
        max_facts=getattr(mem, "max_facts", 1000),
    )


@memory.command(name="list")
def list_facts() -> None:
    """List durable facts captured by the automatic memory service."""
    console = Console()

    store = _get_fact_store()
    facts = store.list()
    if not facts:
        console.print("[yellow]No memory facts stored yet.[/yellow]")
        return

    table = Table(title=f"Memory Facts ({len(facts)})")
    table.add_column("#", style="dim", width=4)
    table.add_column("Fact")
    table.add_column("Source", style="cyan")
    table.add_column("Trust")
    any_quarantined = False
    for i, fact in enumerate(facts, 1):
        quarantined = not fact.trusted_for_recall
        any_quarantined = any_quarantined or quarantined
        trust_disp = (
            "[red]⚠ quarantined[/red]"
            if quarantined
            else f"[green]{fact.trust or 'legacy'}[/green]"
        )
        table.add_row(str(i), fact.text, fact.source or "-", trust_disp)
    console.print(table)
    if any_quarantined:
        console.print(
            "[red]⚠ quarantined[/red] facts are retained for audit but excluded "
            "from model recall because they may contain hostile input. Review "
            "one and run [bold]jarvis memory trust <#>[/bold] to allow recall."
        )


@memory.command(name="trust")
@click.argument("index", type=int)
def trust_fact(index: int) -> None:
    """Promote quarantined fact INDEX (as shown by `memory list`) to trusted.

    Only do this after reading the fact: a quarantined fact matched an
    injection pattern, and promoting it puts its text into future prompts.
    """
    console = Console()

    store = _get_fact_store()
    facts = store.list()
    if not 1 <= index <= len(facts):
        console.print(
            f"[red]No fact #{index}.[/red] "
            f"{len(facts)} fact(s) stored — see [bold]jarvis memory list[/bold]."
        )
        raise SystemExit(1)

    fact = facts[index - 1]
    if fact.trusted_for_recall:
        console.print(f"[yellow]Fact #{index} is already recallable.[/yellow]")
        return
    if not store.promote_reviewed(index - 1, fact.text):
        console.print(f"[red]Could not update fact #{index}.[/red]")
        raise SystemExit(1)
    console.print(f"[green]Fact #{index} is now trusted for recall:[/green]")
    console.print(f"  {fact.text}")


@memory.command()
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    default=False,
    help="Skip the confirmation prompt.",
)
def clear(yes: bool) -> None:
    """Remove all durable facts captured by the automatic memory service."""
    console = Console()

    store = _get_fact_store()
    count = store.count()
    if count == 0:
        console.print("[yellow]No memory facts to clear.[/yellow]")
        return

    if not yes:
        if not click.confirm(f"Remove all {count} stored memory fact(s)?"):
            console.print("[dim]Aborted.[/dim]")
            return

    removed = store.clear()
    console.print(f"[green]Cleared {removed} memory fact(s).[/green]")


def _get_sqlite_fact_store():
    """Instantiate the structured-fact (SQLite + FTS5) store.

    Separate from the JSONL auto-extracted facts used by ``memory list`` /
    ``trust`` / ``clear``: this store holds facts recorded deliberately via
    ``remember`` / ``correct``, with scopes, supersede history, and ranked
    retrieval.
    """
    from openjarvis.core.paths import get_config_dir
    from openjarvis.memory.sqlite_facts import SqliteFactStore

    return SqliteFactStore(get_config_dir() / "memory_facts.db")


def _resolve_fact_ref(store, ref: str):
    """Resolve a ``forget`` / ``correct`` reference to a fact.

    Accepts a full id, a unique id prefix, or the 1-based index shown by
    ``memory show``. Returns the fact or ``None``.
    """
    facts = store.list()
    for fact in facts:
        if fact.id == ref:
            return fact
    if ref.isdigit():
        index = int(ref)
        if 1 <= index <= len(facts):
            return facts[index - 1]
    matches = [fact for fact in facts if fact.id.startswith(ref)]
    if len(matches) == 1:
        return matches[0]
    return None


@memory.command()
@click.argument("text", nargs=-1, required=True)
@click.option("--source", default="", help="Where this fact came from.")
@click.option(
    "--scope",
    default="global",
    help="Scope the fact applies to (default: global).",
)
def remember(text: tuple[str, ...], source: str, scope: str) -> None:
    """Remember a fact: ``jarvis memory remember --source notes <text>``."""
    console = Console()
    store = _get_sqlite_fact_store()
    try:
        fact = store.remember(" ".join(text), source=source, scope=scope)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise SystemExit(1)
    console.print(f"[green]Remembered fact {fact.id[:8]}:[/green]")
    console.print(f"  {fact.text}")


@memory.command()
@click.argument("ref")
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    default=False,
    help="Skip the confirmation prompt.",
)
def forget(ref: str, yes: bool) -> None:
    """Forget a fact by id, id prefix, or number from ``memory show``.

    The fact is hard-deleted from the store AND the FTS index; only its id
    is kept in the deletion log for audit.
    """
    console = Console()
    store = _get_sqlite_fact_store()
    fact = _resolve_fact_ref(store, ref)
    if fact is None:
        console.print(f"[red]No fact matching {ref!r}.[/red]")
        raise SystemExit(1)
    if not yes and not click.confirm(f"Forget this fact?\n  {fact.text}"):
        console.print("[dim]Aborted.[/dim]")
        return
    store.forget(fact.id)
    console.print(f"[green]Forgot fact {fact.id[:8]}.[/green]")


@memory.command()
@click.option("--query", "-q", default="", help="Ranked search over facts.")
@click.option("--scope", default=None, help="Only show facts in this scope.")
@click.option(
    "--top-k",
    "-k",
    default=50,
    type=int,
    help="Max results (only with --query).",
)
def show(query: str, scope: str | None, top_k: int) -> None:
    """Show stored facts, optionally ranked by relevance to --query."""
    console = Console()
    store = _get_sqlite_fact_store()
    if query:
        hits = store.retrieve(query, scope=scope, top_k=top_k)
        rows = [(hit.fact, f"{hit.score:.3f}") for hit in hits]
    else:
        rows = [(fact, "-") for fact in store.list(scope=scope)]
    if not rows:
        console.print("[yellow]No memory facts stored yet.[/yellow]")
        return
    table = Table(title=f"Memory Facts ({len(rows)})")
    table.add_column("#", style="dim", width=4)
    table.add_column("ID", style="dim", width=8)
    table.add_column("Score", width=7)
    table.add_column("Scope", style="cyan")
    table.add_column("Source", style="cyan")
    table.add_column("Fact")
    for i, (fact, score) in enumerate(rows, 1):
        table.add_row(
            str(i), fact.id[:8], score, fact.scope, fact.source or "-", fact.text
        )
    console.print(table)


@memory.command()
@click.argument("ref")
@click.argument("text", nargs=-1, required=True)
def correct(ref: str, text: tuple[str, ...]) -> None:
    """Correct a fact: the old fact is superseded, never returned again.

    ``jarvis memory correct 3 <new text>`` — REF is an id, id prefix, or the
    number shown by ``memory show``.
    """
    console = Console()
    store = _get_sqlite_fact_store()
    fact = _resolve_fact_ref(store, ref)
    if fact is None:
        console.print(f"[red]No fact matching {ref!r}.[/red]")
        raise SystemExit(1)
    try:
        replacement = store.correct(fact.id, " ".join(text))
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise SystemExit(1)
    console.print("[green]Corrected:[/green]")
    console.print(f"  old: {fact.text}")
    console.print(f"  new: {replacement.text}")


@memory.command()
def summary() -> None:
    """Show per-source summaries: fact counts + latest fact per source."""
    console = Console()
    store = _get_sqlite_fact_store()
    summaries = store.summaries_by_source()
    if not summaries:
        console.print("[yellow]No memory facts stored yet.[/yellow]")
        return
    table = Table(title="Memory Facts by Source")
    table.add_column("Source", style="cyan")
    table.add_column("Facts", width=6)
    table.add_column("Latest Fact")
    for entry in summaries:
        table.add_row(
            entry["source"] or "-",
            str(entry["count"]),
            entry["latest_text"],
        )
    console.print(table)


@memory.command()
@click.option(
    "--backend",
    "-b",
    default=None,
    help="Override the default memory backend.",
)
def stats(backend: str | None) -> None:
    """Show memory store statistics."""
    console = Console()

    mem = _get_backend(backend)
    try:
        count = 0
        if hasattr(mem, "count"):
            count = mem.count()

        table = Table(title="Memory Statistics")
        table.add_column("Property", style="cyan")
        table.add_column("Value")
        table.add_row("Backend", mem.backend_id)
        table.add_row("Documents", str(count))

        if hasattr(mem, "_db_path"):
            db_path = Path(mem._db_path)
            if db_path.exists():
                size_kb = db_path.stat().st_size / 1024
                table.add_row(
                    "Database size",
                    f"{size_kb:.1f} KB",
                )
            table.add_row("Database path", str(db_path))

        console.print(table)
    finally:
        if hasattr(mem, "close"):
            mem.close()
