"""CLI interface."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.text import Text

from bookmark_manager import __version__
from bookmark_manager.store import BookmarkError, BookmarkStore, default_data_path

console = Console()


@click.group()
@click.option(
    "--data",
    "data_path",
    envvar="BOOKMARK_MANAGER_DATA",
    type=click.Path(dir_okay=False),
    help="JSON file used to store bookmarks. Defaults to the user data directory.",
)
@click.version_option(__version__, prog_name="bookmark-manager")
@click.pass_context
def main(ctx: click.Context, data_path: str | None) -> None:
    """Save, find, and remove bookmarks from the terminal."""
    ctx.ensure_object(dict)
    path = Path(data_path) if data_path else default_data_path()
    ctx.obj["store"] = BookmarkStore(path)


@main.command()
@click.argument("url")
@click.option("--title", "-t", help="Bookmark title. Defaults to the URL.")
@click.option(
    "--tag",
    "-g",
    multiple=True,
    help="Tag to attach. Repeat for more than one.",
)
@click.pass_context
def add(ctx: click.Context, url: str, title: str | None, tag: tuple[str, ...]) -> None:
    """Add a bookmark.

    The URL must be http or https. A URL that points at an existing bookmark
    is rejected. Host case, default ports, and a trailing slash do not make
    a URL unique.
    """
    store = _store(ctx)
    try:
        bookmark = store.add(url, title=title, tags=tag)
    except BookmarkError as exc:
        raise click.ClickException(str(exc)) from exc
    line = Text("✅ Added bookmark: ")
    if bookmark["title"] != bookmark["url"]:
        line.append(bookmark["title"], style="bold green")
        line.append(" - ")
    line.append(bookmark["url"], style="bold")
    if bookmark["tags"]:
        line.append(" [" + ", ".join(bookmark["tags"]) + "]")
    console.print(line)


@main.command("list")
@click.pass_context
def list_bookmarks(ctx: click.Context) -> None:
    """List saved bookmarks."""
    bookmarks = _call(ctx, BookmarkStore.list_bookmarks)
    if not bookmarks:
        console.print("No bookmarks yet.")
        return
    _print_bookmarks(bookmarks, "Bookmarks")


@main.command()
@click.argument("keyword")
@click.pass_context
def search(ctx: click.Context, keyword: str) -> None:
    """Search titles, URLs, and tags (case-insensitive)."""
    try:
        matches = _store(ctx).search(keyword)
    except BookmarkError as exc:
        raise click.ClickException(str(exc)) from exc
    if not matches:
        line = Text('No bookmarks matched "')
        line.append(keyword)
        line.append('".')
        console.print(line)
        return
    _print_bookmarks(matches, f'Matches for "{keyword}"')


@main.command()
@click.argument("bookmark_id", type=click.IntRange(min=1))
@click.pass_context
def remove(ctx: click.Context, bookmark_id: int) -> None:
    """Remove a bookmark by its id."""
    try:
        bookmark = _store(ctx).remove(bookmark_id)
    except BookmarkError as exc:
        raise click.ClickException(str(exc)) from exc
    line = Text(f"✅ Removed bookmark #{bookmark['id']}: ")
    line.append(bookmark["title"], style="bold")
    line.append(" (")
    line.append(bookmark["url"])
    line.append(")")
    console.print(line)


def _store(ctx: click.Context) -> BookmarkStore:
    return ctx.obj["store"]


def _call(
    ctx: click.Context, action: Callable[[BookmarkStore], list[dict]]
) -> list[dict]:
    try:
        return action(_store(ctx))
    except BookmarkError as exc:
        raise click.ClickException(str(exc)) from exc


def _print_bookmarks(bookmarks: list[dict], title: str) -> None:
    table = Table(title=Text(title))
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Title", style="green", overflow="fold")
    table.add_column("URL", overflow="fold")
    table.add_column("Tags", overflow="fold")
    for bookmark in bookmarks:
        table.add_row(
            Text(str(bookmark["id"])),
            Text(bookmark["title"]),
            Text(bookmark["url"]),
            Text(", ".join(bookmark["tags"])),
        )
    console.print(table)


if __name__ == "__main__":
    main()
