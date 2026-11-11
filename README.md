# Bookmark Manager

## 简介

bookmark-manager 是一个本地书签命令行工具，用来在终端里保存网址、标题和标签，并支持列出、搜索和按编号删除。书签保存在本机的 JSON 文件中。相同链接只保留一条（忽略主机名大小写、默认端口和多余的结尾斜杠）。网址里的方括号会按原样保存和显示，不会被终端颜色标记截断或让命令报错。

A small command-line bookmark manager. It stores http(s) URLs, titles, and tags in a JSON file on your machine, then lists, searches, and removes them.

## Installation

Python 3.10 or newer is required.

```bash
git clone https://github.com/Master-626/bookmark-manager.git
cd bookmark-manager
python -m pip install .
```

To work on the code, install the development tools as well:

```bash
python -m pip install -e ".[dev]"
```

## Usage

```bash
bookmark-manager add https://github.com -t "GitHub" -g dev -g git
bookmark-manager list
bookmark-manager search github
bookmark-manager search dev
bookmark-manager remove 1
```

`add` prints the saved title, URL, and tags. `list` prints every bookmark. `search` matches a case-insensitive substring of the title, URL, or tags. `remove` deletes one bookmark by the id shown in the list.

A second add of the same page fails and leaves the original bookmark unchanged:

```bash
bookmark-manager add https://example.com/docs/
bookmark-manager add https://EXAMPLE.com/docs
# Error: Bookmark already exists: https://example.com/docs (#1).
```

These values are not URLs and are rejected: an empty string, a host with no scheme (`example.com`), and any scheme other than `http` or `https`.

Use another file when you do not want the default location. The option belongs on the main command, before `add`, `list`, `search`, or `remove`:

```bash
bookmark-manager --data ./bookmarks.json add https://example.com -t "Example"
BOOKMARK_MANAGER_DATA=./bookmarks.json bookmark-manager list
```

## Options

### Every command

| Option | Description |
| --- | --- |
| `--data PATH` | JSON file to read and write. Overrides `BOOKMARK_MANAGER_DATA`. |
| `--version` | Print the program version. |
| `--help` | Print help. Commands also have their own `--help`. |

When `--data` and `BOOKMARK_MANAGER_DATA` are both unset, bookmarks are stored in `$XDG_DATA_HOME/bookmark-manager/bookmarks.json`, or `~/.local/share/bookmark-manager/bookmarks.json` when `XDG_DATA_HOME` is unset.

### `add URL`

| Option | Description |
| --- | --- |
| `-t`, `--title TEXT` | Title to show in the list. Defaults to the saved URL. |
| `-g`, `--tag TEXT` | Tag. Repeat the option for more than one tag. Blank tags are dropped, and tags that differ only by case are stored once. |

The saved URL is normalized: surrounding whitespace is removed, the scheme and host are lowercased, a default `:80` or `:443` port is removed, and a trailing slash is removed. The query string, fragment, and userinfo are kept. `https://Example.com:443/docs/` and `https://example.com/docs` are the same bookmark.

### `list`

Prints the id, title, URL, and tags. When the file is missing or empty, it prints `No bookmarks yet.`

### `search KEYWORD`

Finds bookmarks whose title, URL, or tags contain `KEYWORD`. Matching is case-insensitive. The id is not searched. A blank keyword is an error.

### `remove ID`

Deletes the bookmark with that positive integer id. Ids are not reused.

## Data file

The file is JSON:

```json
{
  "next_id": 2,
  "bookmarks": [
    {
      "id": 1,
      "url": "https://github.com",
      "title": "GitHub",
      "tags": ["dev", "git"],
      "created_at": "2026-11-11T17:30:00Z"
    }
  ]
}
```

`next_id` is the next id to assign, so deleting a bookmark does not reuse its id. A file that omits `next_id` still loads; the next id is one higher than the largest id already stored. Extra fields on the file or on an entry are preserved the next time the program saves. If the JSON is corrupt, or an entry is missing a field, the command stops with an error and does not overwrite the file.

## Running tests

```bash
python -m pip install -e ".[dev]"
python -m ruff check .
python -m ruff format --check .
python -m pytest
```

GitHub Actions runs those same commands on Python 3.10, 3.11, 3.12, 3.13, and 3.14.

## License

MIT License. See [LICENSE](LICENSE).
