"""CLI interface."""
import click
from rich.console import Console
from rich.table import Table

console = Console()

@click.group()
@click.version_option(version="0.1.0")
def main():
    """Bookmark Manager - Organize your bookmarks from the terminal."""
    pass

@main.command()
@click.argument("url")
@click.option("--title", "-t", help="Bookmark title")
@click.option("--tag", "-g", multiple=True, help="Tags")
def add(url, title, tag):
    """Add a new bookmark."""
    console.print(f"✅ Added bookmark: [bold green]{url}[/bold green]")

@main.command()
def list():
    """List all bookmarks."""
    table = Table(title="Bookmarks")
    table.add_column("ID", style="cyan")
    table.add_column("Title", style="green")
    table.add_column("URL")
    table.add_row("1", "GitHub", "https://github.com")
    console.print(table)

@main.command()
@click.argument("keyword")
def search(keyword):
    """Search bookmarks."""
    console.print(f"🔍 Searching for: {keyword}")

if __name__ == "__main__":
    main()
