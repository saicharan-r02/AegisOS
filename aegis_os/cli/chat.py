"""Interactive pairing REPL session for developer pairing with AegisOS tools."""

from __future__ import annotations

from pathlib import Path

from aegis_os.cli.display import AegisDisplay
from aegis_os.intelligence.repo_map import RepoMap
from aegis_os.intelligence.search import CodeSearchEngine
from aegis_os.tools.filesystem_tools import ListDirTool, ReadFileTool
from aegis_os.tools.git_tools import GitDiffTool, GitStatusTool
from aegis_os.tools.registry import ToolRegistry


class AegisChatSession:
    """Terminal-based interactive pairing session."""

    def __init__(
        self,
        workspace_root: Path | str = ".",
        provider: str | None = None,
        model: str | None = None,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.display = AegisDisplay()
        self.provider = provider
        self.model = model
        self.registry = ToolRegistry()
        self._init_tools()

    def _init_tools(self) -> None:
        self.registry.register(ReadFileTool(self.workspace_root))
        self.registry.register(ListDirTool(self.workspace_root))
        self.registry.register(GitStatusTool(self.workspace_root))
        self.registry.register(GitDiffTool(self.workspace_root))

    def run_interactive_loop(self) -> int:
        """Run the REPL pairing loop."""
        self.display.console.print(
            "\n[bold cyan]╔═══════════════════════════════════════════════════════════╗[/bold cyan]"
        )
        self.display.console.print(
            "[bold cyan]║[/bold cyan]   [bold white]AegisOS Interactive Developer Pairing Shell (v2.0)[/bold white]     [bold cyan]║[/bold cyan]"
        )
        self.display.console.print(
            "[bold cyan]╚═══════════════════════════════════════════════════════════╝[/bold cyan]"
        )
        self.display.console.print(f"[dim]Workspace: {self.workspace_root}[/dim]")
        self.display.console.print(
            "[dim]Type your inquiry, or '/help', '/tools', '/map', '/exit'[/dim]\n"
        )

        while True:
            try:
                user_input = input("aegis> ").strip()
            except (EOFError, KeyboardInterrupt):
                self.display.console.print("\n[dim]Exiting interactive session.[/dim]")
                break

            if not user_input:
                continue

            if user_input in {"/exit", "/quit", ":q"}:
                self.display.console.print("[dim]Exiting interactive session.[/dim]")
                break
            elif user_input == "/help":
                self.display.console.print("[bold yellow]Commands:[/bold yellow]")
                self.display.console.print("  /tools   List loaded engineering tools")
                self.display.console.print("  /map     Generate compact RepoMap summary")
                self.display.console.print("  /exit    Exit pairing shell")
            elif user_input == "/tools":
                tools = self.registry.list_tools()
                self.display.console.print(
                    f"[bold cyan]Registered Tools ({len(tools)}):[/bold cyan]"
                )
                for t in tools:
                    self.display.console.print(f"  • [bold]{t.name}[/bold]: {t.description}")
            elif user_input == "/map":
                self.display.console.print("[dim]Generating RepoMap...[/dim]")
                rm = RepoMap(self.workspace_root)
                outline = rm.render_outline(max_tokens=500)
                self.display.console.print(
                    f"[bold green]Repository Map Outline:[/bold green]\n{outline}"
                )
            else:
                # Answer inquiry using local search or summary
                self.display.console.print(f"[dim]Investigating: {user_input}[/dim]")
                search = CodeSearchEngine(self.workspace_root)
                results = search.search(user_input, top_k=3)
                if results:
                    self.display.console.print("[bold green]Relevant Code References:[/bold green]")
                    for r in results:
                        self.display.console.print(
                            f"  [cyan]{r.file_path}:{r.line_number}[/cyan] (Score: {r.score:.2f})"
                        )
                        self.display.console.print(f"    [dim]{r.content.strip()[:100]}[/dim]")
                else:
                    self.display.console.print(
                        "[yellow]No direct code matches located. Use /tools or /map to inspect repository.[/yellow]"
                    )

        return 0
