"""JSON storage and bookmark rules."""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

_DEFAULT_PORTS = {"http": "80", "https": "443"}


class BookmarkError(Exception):
    """Invalid bookmark data or a storage problem the user can fix."""


def default_data_path() -> Path:
    """Return the default bookmark file under the user data directory."""
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "bookmark-manager" / "bookmarks.json"


def normalize_url(url: str) -> str:
    """Return a canonical http(s) URL used for storage and duplicate checks.

    Host case, default ports, and a trailing slash are ignored so the same
    page is not stored twice. The query string and fragment are preserved.
    """
    raw = url.strip()
    if not raw:
        raise BookmarkError("URL must not be empty.")
    parts = urlsplit(raw)
    if not parts.scheme or not parts.netloc:
        raise BookmarkError(
            "URL must include a scheme and host, for example https://example.com."
        )
    scheme = parts.scheme.lower()
    if scheme not in _DEFAULT_PORTS:
        raise BookmarkError("Only http and https URLs are supported.")
    path = parts.path
    if path == "/":
        path = ""
    elif len(path) > 1:
        path = path.rstrip("/")
    return urlunsplit(
        (
            scheme,
            _normalize_netloc(parts.netloc, scheme),
            path,
            parts.query,
            parts.fragment,
        )
    )


class BookmarkStore:
    """Bookmarks saved in one JSON file.

    The file is an object with a ``bookmarks`` list and a ``next_id`` counter.
    Unknown fields are kept, so a hand-edited note is not dropped on the next save.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def list_bookmarks(self) -> list[dict]:
        return self._load()

    def add(
        self,
        url: str,
        title: str | None = None,
        tags: Iterable[str] = (),
    ) -> dict:
        normalized = normalize_url(url)
        cleaned_tags = _clean_tags(tags)
        if title is None:
            cleaned_title = normalized
        else:
            if not isinstance(title, str):
                raise BookmarkError("Title must be text.")
            cleaned_title = title.strip() or normalized
        document = self._load_document()
        bookmarks = document["bookmarks"]
        for existing in bookmarks:
            if _same_target(existing["url"], normalized):
                raise BookmarkError(
                    f"Bookmark already exists: {existing['url']} (#{existing['id']})."
                )
        saved = {
            "id": document["next_id"],
            "url": normalized,
            "title": cleaned_title,
            "tags": cleaned_tags,
            "created_at": _utc_now(),
        }
        document["next_id"] += 1
        bookmarks.append(saved)
        self._save_document(document)
        return saved

    def search(self, keyword: str) -> list[dict]:
        needle = keyword.strip().casefold()
        if not needle:
            raise BookmarkError("Search keyword must not be empty.")
        matches = []
        for bookmark in self._load():
            haystack = " ".join(
                [bookmark["title"], bookmark["url"], *bookmark["tags"]]
            ).casefold()
            if needle in haystack:
                matches.append(bookmark)
        return matches

    def remove(self, bookmark_id: int) -> dict:
        if isinstance(bookmark_id, bool) or not isinstance(bookmark_id, int):
            raise BookmarkError("Bookmark id must be an integer.")
        if bookmark_id < 1:
            raise BookmarkError("Bookmark id must be positive.")
        document = self._load_document()
        bookmarks = document["bookmarks"]
        for index, bookmark in enumerate(bookmarks):
            if bookmark["id"] == bookmark_id:
                removed = bookmarks.pop(index)
                self._save_document(document)
                return removed
        raise BookmarkError(f"No bookmark with id {bookmark_id}.")

    def _load(self) -> list[dict]:
        return self._load_document()["bookmarks"]

    def _load_document(self) -> dict:
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {"next_id": 1, "bookmarks": []}
        except OSError as exc:
            raise BookmarkError(f"Could not read {self.path}: {exc.strerror}") from exc
        if not raw.strip():
            return {"next_id": 1, "bookmarks": []}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise BookmarkError(
                f"Bookmark file is not valid JSON: {self.path}"
            ) from exc
        if not isinstance(data, dict) or not isinstance(data.get("bookmarks"), list):
            raise BookmarkError(
                f"Bookmark file must be an object with a 'bookmarks' list: {self.path}"
            )
        bookmarks: list[dict] = []
        seen_ids: set[int] = set()
        for item in data["bookmarks"]:
            bookmarks.append(_validate_bookmark(item, self.path, seen_ids))
        document = dict(data)
        document["bookmarks"] = bookmarks
        document["next_id"] = _assigned_next_id(data, bookmarks, self.path)
        return document

    def _save_document(self, document: dict) -> None:
        ordered = {
            "next_id": document["next_id"],
            "bookmarks": document["bookmarks"],
        }
        for key, value in document.items():
            if key not in ordered:
                ordered[key] = value
        text = json.dumps(ordered, indent=2, ensure_ascii=False) + "\n"
        temporary = self.path.with_name(self.path.name + ".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(text, encoding="utf-8")
            temporary.replace(self.path)
        except OSError as exc:
            raise BookmarkError(f"Could not write {self.path}: {exc.strerror}") from exc


def _normalize_netloc(netloc: str, scheme: str) -> str:
    userinfo, separator, hostport = netloc.rpartition("@")
    host, port = _split_host_port(hostport)
    host = host.lower()
    if port == _DEFAULT_PORTS[scheme]:
        port = None
    rebuilt = host if port is None else f"{host}:{port}"
    if separator:
        return f"{userinfo}@{rebuilt}"
    return rebuilt


def _split_host_port(hostport: str) -> tuple[str, str | None]:
    if hostport.startswith("["):
        end = hostport.find("]")
        if end == -1:
            return hostport, None
        host = hostport[: end + 1]
        rest = hostport[end + 1 :]
        if rest.startswith(":") and rest[1:].isdigit():
            return host, rest[1:]
        return host, None
    if hostport.count(":") == 1:
        host, port = hostport.split(":")
        if port.isdigit():
            return host, port
    return hostport, None


def _clean_tags(tags: Iterable[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        if not isinstance(tag, str):
            raise BookmarkError("Tags must be text.")
        text = tag.strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    return cleaned


def _same_target(stored_url: str, normalized: str) -> bool:
    try:
        return normalize_url(stored_url) == normalized
    except BookmarkError:
        return False


def _assigned_next_id(data: dict, bookmarks: list[dict], path: Path) -> int:
    highest = max((bookmark["id"] for bookmark in bookmarks), default=0)
    if "next_id" not in data:
        return highest + 1
    next_id = data["next_id"]
    if isinstance(next_id, bool) or not isinstance(next_id, int) or next_id < 1:
        raise BookmarkError(f"next_id must be a positive integer in {path}.")
    return max(next_id, highest + 1)


def _utc_now() -> str:
    stamped = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return stamped.replace("+00:00", "Z")


def _validate_bookmark(item: object, path: Path, seen_ids: set[int]) -> dict:
    if not isinstance(item, dict):
        raise BookmarkError(f"Invalid bookmark entry in {path}.")
    required = ("id", "url", "title", "tags", "created_at")
    missing = [key for key in required if key not in item]
    if missing:
        names = ", ".join(missing)
        raise BookmarkError(f"Bookmark entry is missing {names} in {path}.")
    bookmark_id = item["id"]
    if (
        isinstance(bookmark_id, bool)
        or not isinstance(bookmark_id, int)
        or bookmark_id < 1
    ):
        raise BookmarkError(f"Bookmark id must be a positive integer in {path}.")
    if bookmark_id in seen_ids:
        raise BookmarkError(f"Duplicate bookmark id {bookmark_id} in {path}.")
    if not isinstance(item["url"], str) or not isinstance(item["title"], str):
        raise BookmarkError(f"Bookmark url and title must be text in {path}.")
    tags = item["tags"]
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        raise BookmarkError(f"Bookmark tags must be a list of text in {path}.")
    if not isinstance(item["created_at"], str):
        raise BookmarkError(f"Bookmark created_at must be text in {path}.")
    seen_ids.add(bookmark_id)
    return item
