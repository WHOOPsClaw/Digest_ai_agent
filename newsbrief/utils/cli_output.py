"""Shared rich-based CLI output helpers for newsbrief.

Keeps a single `Console` instance and a small set of helpers so commands
have consistent styling (emoji + colour).
"""
from __future__ import annotations

from rich.console import Console
from rich.table import Table  # re-exported for convenience
from rich.progress import Progress  # re-exported for convenience

console = Console()


def success(msg: str) -> None:
    console.print(f"✅ {msg}", style="green")


def warn(msg: str) -> None:
    console.print(f"⚠️  {msg}", style="yellow")


def error(msg: str) -> None:
    console.print(f"❌ {msg}", style="red bold")


def info(msg: str) -> None:
    console.print(f"ℹ️  {msg}")


def heading(msg: str) -> None:
    console.print(f"\n━━━ {msg} ━━━\n", style="bold")


def plain(msg: str = "") -> None:
    console.print(msg)


__all__ = [
    "console",
    "Table",
    "Progress",
    "success",
    "warn",
    "error",
    "info",
    "heading",
    "plain",
]
