"""Test fixtures."""

import pytest
from rich.console import Console

from bookmark_manager import cli


@pytest.fixture(autouse=True)
def _wide_console(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep table cells intact so assertions can see full URLs."""
    monkeypatch.setattr(
        cli,
        "console",
        Console(width=200, force_terminal=False, color_system=None),
    )
