"""Core bookmark storage behavior."""

import json
import os
import re
from pathlib import Path

import pytest

from bookmark_manager.store import BookmarkError, BookmarkStore, normalize_url

_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


def _record(**overrides) -> dict:
    bookmark = {
        "id": 1,
        "url": "https://example.com",
        "title": "Example",
        "tags": [],
        "created_at": "2020-01-01T00:00:00Z",
    }
    bookmark.update(overrides)
    return bookmark


def _write(path: Path, bookmarks: list[dict]) -> None:
    path.write_text(
        json.dumps({"bookmarks": bookmarks}, ensure_ascii=False),
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://example.com", "https://example.com"),
        ("  HTTPS://Example.COM:443/docs/  ", "https://example.com/docs"),
        ("http://Example.com:80/a/", "http://example.com/a"),
        ("https://example.com:80/a", "https://example.com:80/a"),
        (
            "https://User:Secret@Example.com/a/#Section",
            "https://User:Secret@example.com/a#Section",
        ),
        ("https://example.com/?q=A&b=2", "https://example.com?q=A&b=2"),
        ("http://[::1]:80/x/", "http://[::1]/x"),
        ("https://example.com/文档", "https://example.com/文档"),
    ],
)
def test_normalize_url(raw: str, expected: str) -> None:
    assert normalize_url(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "example.com",
        "ftp://example.com/a",
        "https://",
        "http:///missing-host",
        "javascript:alert(1)",
    ],
)
def test_normalize_url_rejects_unusable_values(raw: str) -> None:
    with pytest.raises(BookmarkError):
        normalize_url(raw)


def test_add_stores_title_tags_and_timestamp(tmp_path: Path) -> None:
    store = BookmarkStore(tmp_path / "nested" / "bookmarks.json")
    saved = store.add(
        "  https://example.com/文档/  ",
        title=" 文档 ",
        tags=(" 资料 ", "", "资料", "work"),
    )
    assert saved["id"] == 1
    assert saved["url"] == "https://example.com/文档"
    assert saved["title"] == "文档"
    assert saved["tags"] == ["资料", "work"]
    assert _TIMESTAMP.fullmatch(saved["created_at"])
    reloaded = BookmarkStore(store.path).list_bookmarks()
    assert reloaded == [saved]
    assert not (store.path.parent / "bookmarks.json.tmp").exists()


def test_blank_title_falls_back_to_url(tmp_path: Path) -> None:
    store = BookmarkStore(tmp_path / "bookmarks.json")
    saved = store.add("https://example.com", title="   ")
    assert saved["title"] == "https://example.com"


def test_duplicate_url_does_not_change_the_original(tmp_path: Path) -> None:
    store = BookmarkStore(tmp_path / "bookmarks.json")
    store.add("https://example.com/docs/", title="First", tags=["a"])
    with pytest.raises(BookmarkError, match="already exists"):
        store.add("https://EXAMPLE.com:443/docs", title="Second", tags=["b"])
    saved = store.list_bookmarks()
    assert len(saved) == 1
    assert saved[0]["title"] == "First"
    assert saved[0]["tags"] == ["a"]
    assert saved[0]["url"] == "https://example.com/docs"


def test_ids_are_not_reused_after_remove(tmp_path: Path) -> None:
    store = BookmarkStore(tmp_path / "bookmarks.json")
    store.add("https://example.com/a")
    store.add("https://example.com/b")
    store.remove(2)
    added = store.add("https://example.com/c")
    assert added["id"] == 3
    store.remove(1)
    store.remove(3)
    added = store.add("https://example.com/d")
    assert added["id"] == 4
    with pytest.raises(BookmarkError, match="No bookmark with id 1"):
        store.remove(1)


def test_search_matches_title_url_and_tag_only(tmp_path: Path) -> None:
    store = BookmarkStore(tmp_path / "bookmarks.json")
    store.add("https://example.com/notes", title="Team Notes", tags=["Dev"])
    store.add("https://example.org", title="Other", tags=["ops"])
    assert [item["id"] for item in store.search("  NOTES ")] == [1]
    assert [item["id"] for item in store.search("EXAMPLE.COM")] == [1]
    assert [item["id"] for item in store.search("dev")] == [1]
    assert store.search("1") == []
    assert store.search("missing") == []
    with pytest.raises(BookmarkError, match="must not be empty"):
        store.search("   ")


def test_tags_must_be_text(tmp_path: Path) -> None:
    store = BookmarkStore(tmp_path / "bookmarks.json")
    with pytest.raises(BookmarkError, match="Tags must be text"):
        store.add("https://example.com", tags=("ok", 1))  # type: ignore[arg-type]
    assert store.list_bookmarks() == []


def test_empty_file_has_no_bookmarks(tmp_path: Path) -> None:
    path = tmp_path / "bookmarks.json"
    path.write_text("\n", encoding="utf-8")
    assert BookmarkStore(path).list_bookmarks() == []


def test_missing_file_has_no_bookmarks(tmp_path: Path) -> None:
    assert BookmarkStore(tmp_path / "missing.json").list_bookmarks() == []


def test_hand_edited_fields_survive_the_next_save(tmp_path: Path) -> None:
    path = tmp_path / "bookmarks.json"
    path.write_text(
        json.dumps(
            {"source": "import", "bookmarks": [{**_record(), "note": "hand edited"}]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    BookmarkStore(path).add("https://example.org")
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["source"] == "import"
    assert saved["bookmarks"][0]["note"] == "hand edited"
    assert saved["bookmarks"][1]["url"] == "https://example.org"
    assert saved["next_id"] == 3


def test_low_next_id_does_not_collide(tmp_path: Path) -> None:
    path = tmp_path / "bookmarks.json"
    path.write_text(
        json.dumps({"next_id": 1, "bookmarks": [_record(id=5)]}),
        encoding="utf-8",
    )
    saved = BookmarkStore(path).add("https://example.org")
    assert saved["id"] == 6


def test_hand_edited_url_still_counts_as_a_duplicate(tmp_path: Path) -> None:
    path = tmp_path / "bookmarks.json"
    _write(path, [_record(url="HTTPS://Example.com/docs/")])
    with pytest.raises(BookmarkError, match="already exists"):
        BookmarkStore(path).add("https://example.com/docs")
    assert BookmarkStore(path).list_bookmarks()[0]["url"] == "HTTPS://Example.com/docs/"


def test_list_keeps_a_hand_edited_non_url(tmp_path: Path) -> None:
    path = tmp_path / "bookmarks.json"
    _write(path, [_record(url="not a url", title="Legacy")])
    listed = BookmarkStore(path).list_bookmarks()
    assert listed[0]["url"] == "not a url"
    added = BookmarkStore(path).add("https://example.org", title="New")
    assert added["id"] == 2
    matches = BookmarkStore(path).search("legacy")
    assert [item["title"] for item in matches] == ["Legacy"]


def test_invalid_next_id_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bookmarks.json"
    path.write_text(
        json.dumps({"next_id": True, "bookmarks": []}),
        encoding="utf-8",
    )
    with pytest.raises(BookmarkError, match="next_id"):
        BookmarkStore(path).list_bookmarks()


def _without(bookmark: dict, key: str) -> dict:
    return {name: value for name, value in bookmark.items() if name != key}


@pytest.mark.parametrize(
    ("bookmarks", "match"),
    [
        ([{"id": True, **_without(_record(), "id")}], "positive integer"),
        ([_without(_record(), "title")], "missing title"),
        (
            [_record(), _record(id=1, url="https://example.org")],
            "Duplicate bookmark id",
        ),
        (
            [
                {
                    "id": 1,
                    "url": "https://example.com",
                    "title": "T",
                    "tags": [1],
                    "created_at": "x",
                }
            ],
            "tags",
        ),
        ("not-a-list", "bookmarks"),
    ],
)
def test_corrupt_entries_are_rejected(
    tmp_path: Path, bookmarks: object, match: str
) -> None:
    path = tmp_path / "bookmarks.json"
    if bookmarks == "not-a-list":
        path.write_text('{"bookmarks": {}}', encoding="utf-8")
    else:
        _write(path, bookmarks)  # type: ignore[arg-type]
    with pytest.raises(BookmarkError, match=match):
        BookmarkStore(path).list_bookmarks()


def test_invalid_json_names_the_file(tmp_path: Path) -> None:
    path = tmp_path / "bookmarks.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(BookmarkError, match="not valid JSON"):
        BookmarkStore(path).add("https://example.com")
    assert path.read_text(encoding="utf-8") == "{"


def test_unreadable_file_raises_bookmark_error(tmp_path: Path) -> None:
    if os.geteuid() == 0:
        pytest.skip("root ignores file mode bits")
    path = tmp_path / "bookmarks.json"
    path.write_text("{}", encoding="utf-8")
    path.chmod(0)
    try:
        with pytest.raises(BookmarkError, match="Could not read"):
            BookmarkStore(path).list_bookmarks()
    finally:
        path.chmod(0o644)
