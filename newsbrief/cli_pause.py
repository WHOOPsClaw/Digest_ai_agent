"""cli_pause.py — `newsbrief pause|resume` implementations."""
from __future__ import annotations

from typing import Optional

from rich.console import Console

from newsbrief.core import pause as pause_mod


def cmd_pause(days: int = 1,
              storage=None,
              console: Optional[Console] = None) -> int:
    if storage is None:
        from newsbrief.core.storage import get_storage
        storage = get_storage()
    console = console or Console()

    if days < 1:
        console.print("[red]Invalid --days (must be >= 1).[/red]")
        return 1

    until = pause_mod.pause(storage, days=days)
    # Display as local date (YYYY-MM-DD)
    until_local = until.astimezone().date().isoformat()
    console.print(f"⏸ Digest paused until {until_local} ({days} day"
                  f"{'s' if days != 1 else ''})")
    console.print("Run [bold]newsbrief resume[/bold] to resume earlier.")
    return 0


def cmd_resume(storage=None,
               console: Optional[Console] = None,
               next_delivery: str = "tomorrow at 09:00") -> int:
    if storage is None:
        from newsbrief.core.storage import get_storage
        storage = get_storage()
    console = console or Console()

    pause_mod.resume(storage)
    console.print("▶️ Digest resumed.")
    console.print(f"Next delivery: {next_delivery}.")
    return 0
