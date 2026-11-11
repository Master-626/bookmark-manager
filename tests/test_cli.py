"""Command-line behavior, including bugs in the original stub."""

import json
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import pytest
from click.testing import CliRunner

from bookmark_manager import __version__
from bookmark_manager.cli import main

runner = CliRunner()

BRACKET_URLS = [
    "https://example.com/[docs]",
    "https://example.com/a[/]b",
    "https://example.com/[link=http://evil.example]x[/link]",
    "https://example.com/[/bold]",
]


def invoke(path: Path, *args: str, env: dict[str, str] | None = None):
    return runner.invoke(main, ["--data", str(path), *args], env=env)


def test_version_option() -> None:
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_distribution_version_matches_package() -> None:
    try:
        distributed = version("bookmark-manager")
    except PackageNotFoundError:
        pytest.skip("package is not installed")
    assert distributed == __version__


def test_declared_version_matches_pyproject() -> None:
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    assert f'version = "{__version__}"' in pyproject.read_text(encoding="utf-8")


def test_add_persists_title_and_tags_instead_of_a_placeholder(tmp_path: Path) -> None:
    path = tmp_path / "bookmarks.json"
    added = invoke(
        path,
        "add",
        "https://github.com",
        "-t",
        "GitHub",
        "-g",
        "dev",
        "-g",
        "git",
    )
    assert added.exit_code == 0
    assert "GitHub" in added.output
    assert "https://github.com" in added.output
    assert "dev" in added.output

    listed = invoke(path, "list")
    assert listed.exit_code == 0
    assert "GitHub" in listed.output
    assert "https://github.com" in listed.output
    assert "dev, git" in listed.output

    empty = invoke(tmp_path / "empty.json", "list")
    assert empty.exit_code == 0
    assert "No bookmarks yet." in empty.output
    assert "https://github.com" not in empty.output

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["bookmarks"][0]["title"] == "GitHub"
    assert saved["bookmarks"][0]["tags"] == ["dev", "git"]


@pytest.mark.parametrize("url", BRACKET_URLS)
def test_brackets_in_urls_are_stored_and_shown_literally(
    tmp_path: Path, url: str
) -> None:
    path = tmp_path / "bookmarks.json"
    added = invoke(path, "add", url, "-t", "Docs [/bold]")
    assert added.exit_code == 0, added.output
    assert added.exception is None
    assert url in added.output
    assert "Docs [/bold]" in added.output

    listed = invoke(path, "list")
    assert listed.exit_code == 0, listed.output
    assert url in listed.output
    assert "Docs [/bold]" in listed.output

    found = invoke(path, "search", "[/bold]")
    assert found.exit_code == 0, found.output
    assert url in found.output


def test_search_keyword_with_brackets_does_not_crash(tmp_path: Path) -> None:
    result = invoke(tmp_path / "bookmarks.json", "search", "a[/]b")
    assert result.exit_code == 0
    assert result.exception is None
    assert 'No bookmarks matched "a[/]b".' in result.output


def test_search_finds_real_bookmarks(tmp_path: Path) -> None:
    path = tmp_path / "bookmarks.json"
    invoke(path, "add", "https://example.com/notes", "-t", "Team Notes", "-g", "dev")
    invoke(path, "add", "https://example.org", "-t", "Other")

    by_title = invoke(path, "search", "team")
    assert by_title.exit_code == 0
    assert "https://example.com/notes" in by_title.output
    assert "https://example.org" not in by_title.output

    by_tag = invoke(path, "search", "DEV")
    assert "https://example.com/notes" in by_tag.output

    missing = invoke(path, "search", "absent")
    assert missing.exit_code == 0
    assert 'No bookmarks matched "absent".' in missing.output

    blank = invoke(path, "search", "   ")
    assert blank.exit_code == 1
    assert "must not be empty" in blank.output


def test_duplicate_and_invalid_urls_fail(tmp_path: Path) -> None:
    path = tmp_path / "bookmarks.json"
    assert invoke(path, "add", "https://example.com/docs/").exit_code == 0
    duplicate = invoke(path, "add", "https://EXAMPLE.com/docs")
    assert duplicate.exit_code == 1
    assert "already exists" in duplicate.output
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert len(saved["bookmarks"]) == 1

    for raw in ("", "example.com", "ftp://example.com/a"):
        rejected = invoke(path, "add", raw)
        assert rejected.exit_code != 0
        assert len(json.loads(path.read_text(encoding="utf-8"))["bookmarks"]) == 1


def test_corrupt_file_is_reported_without_a_traceback(tmp_path: Path) -> None:
    path = tmp_path / "bookmarks.json"
    path.write_text("{", encoding="utf-8")
    result = invoke(path, "list")
    assert result.exit_code == 1
    assert "not valid JSON" in result.output
    assert "Traceback" not in result.output
    assert path.read_text(encoding="utf-8") == "{"


def test_remove_deletes_one_bookmark(tmp_path: Path) -> None:
    path = tmp_path / "bookmarks.json"
    invoke(path, "add", "https://example.com/a", "-t", "Alpha")
    invoke(path, "add", "https://example.com/b", "-t", "Beta")

    removed = invoke(path, "remove", "1")
    assert removed.exit_code == 0
    assert "Alpha" in removed.output
    assert "https://example.com/a" in removed.output

    listed = invoke(path, "list")
    assert "https://example.com/a" not in listed.output
    assert "https://example.com/b" in listed.output
    assert invoke(path, "search", "Alpha").exit_code == 0
    assert "https://example.com/a" not in invoke(path, "search", "Alpha").output

    missing = invoke(path, "remove", "1")
    assert missing.exit_code == 1
    assert "No bookmark with id 1" in missing.output
    assert invoke(path, "remove", "nope").exit_code == 2
    assert invoke(path, "remove", "0").exit_code == 2
    assert invoke(path, "remove", "-1").exit_code == 2


def test_data_option_overrides_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / "env.json"
    cli_file = tmp_path / "cli.json"
    monkeypatch.setenv("BOOKMARK_MANAGER_DATA", str(env_file))
    result = runner.invoke(
        main, ["--data", str(cli_file), "add", "https://example.com"]
    )
    assert result.exit_code == 0
    assert cli_file.is_file()
    assert not env_file.exists()


def test_environment_selects_the_data_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "from-env.json"
    monkeypatch.setenv("BOOKMARK_MANAGER_DATA", str(path))
    result = runner.invoke(main, ["add", "https://example.com", "-t", "Env"])
    assert result.exit_code == 0
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["bookmarks"][0]["title"] == "Env"


def test_default_path_uses_xdg_data_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.delenv("BOOKMARK_MANAGER_DATA", raising=False)
    result = runner.invoke(main, ["add", "https://example.com"])
    expected = tmp_path / "bookmark-manager" / "bookmarks.json"
    assert result.exit_code == 0
    assert expected.is_file()
