"""Banner do ATOM."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel

ART = r"""
    _   _____ ___  __  __
   / \ |_   _/ _ \|  \/  |
  / _ \  | || | | | |\/| |
 / ___ \ | || |_| | |  | |
/_/   \_\|_| \___/|_|  |_|
"""


def show(console: Console, engine: str, tools: int, skills: int) -> None:
    body = (f"[bold cyan]{ART.strip()}[/]\n\n"
            f"[dim]assistente local-first do Mestre Gabriel[/]\n"
            f"engine [bold]{engine}[/]  |  tools [bold]{tools}[/]  |  skills [bold]{skills}[/]")
    console.print(Panel(body, border_style="cyan", title="ATOM v0.1", expand=False))
