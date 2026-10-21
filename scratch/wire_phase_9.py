from pathlib import Path

path = Path("aegis_os/cli/main.py")
content = path.read_text(encoding="utf-8")

# 1. Add arguments to run_p: --mode, --issue, --json, --headless
old_run_flags = '''    run_p.add_argument("--strategy",type=str,default="adaptive",choices=["adaptive","waterfall"],help="Mission execution strategy: adaptive (DAG supervisor) or waterfall (legacy pipeline)")
    run_p.add_argument("--db-path",type=str,default=".aegis/checkpoints.db",help="Path to SQLite checkpoint database")'''

new_run_flags = '''    run_p.add_argument("--strategy",type=str,default="adaptive",choices=["adaptive","waterfall"],help="Mission execution strategy: adaptive (DAG supervisor) or waterfall (legacy pipeline)")
    run_p.add_argument("--mode",type=str,default="auto",choices=["plan","supervised","auto"],help="Autonomy mode: plan (pause after DAG), supervised (confirm risky actions), auto (bounded by policy)")
    run_p.add_argument("--issue",type=str,default=None,help="GitHub issue URL to ingest objective from (e.g. https://github.com/org/repo/issues/42)")
    run_p.add_argument("--headless",action="store_true",help="Run in headless non-interactive mode")
    run_p.add_argument("--json",dest="json_output",action="store_true",help="Emit machine-readable JSON summary upon completion")
    run_p.add_argument("--db-path",type=str,default=".aegis/checkpoints.db",help="Path to SQLite checkpoint database")'''

assert old_run_flags in content, "old_run_flags not found"
content = content.replace(old_run_flags, new_run_flags, 1)

# 2. Add chat and config subcommands
old_server_block = '''    server_p = subparsers.add_parser("server",help="Launch the War Room Web Dashboard backend")
    server_p.add_argument("--host",type=str,default="127.0.0.1",help="Host IP to bind to")
    server_p.add_argument("--port",type=int,default=8000,help="Port to run on")
    server_p.add_argument("--db-path",type=str,default=".aegis/checkpoints.db",help="Path to SQLite checkpoint database")'''

new_server_and_phase9 = old_server_block + '''\n
    chat_p = subparsers.add_parser("chat",help="Start interactive pairing shell with codebase tools")
    chat_p.add_argument("-w","--workspace",type=str,default=".",help="Target workspace root")
    chat_p.add_argument("-p","--provider",type=str,default=None,help="LLM provider override")
    chat_p.add_argument("-m","--model",type=str,default=None,help="Model identifier override")

    config_p = subparsers.add_parser("config",help="Validate and inspect aegis configuration")
    config_p.add_argument("command",choices=["check"],help="Config command (check)")
    config_p.add_argument("-c","--config",type=str,default="aegis.toml",help="Path to config file")'''

assert old_server_block in content, "old_server_block not found"
content = content.replace(old_server_block, new_server_and_phase9, 1)

# 3. Add handle_chat and handle_config handlers before main()
handlers_hook = '''def handle_server(args: argparse.Namespace, display: AegisDisplay) -> int:'''

new_handlers = '''def handle_chat(args: argparse.Namespace, display: AegisDisplay) -> int:
    """Launch interactive pairing session."""
    from aegis_os.cli.chat import AegisChatSession
    session = AegisChatSession(workspace_root=args.workspace, provider=args.provider, model=args.model)
    return session.run_interactive_loop()


def handle_config(args: argparse.Namespace, display: AegisDisplay) -> int:
    """Validate aegis.toml configuration file."""
    from aegis_os.config.validator import validate_config_file
    is_valid, messages = validate_config_file(args.config)
    if is_valid:
        display.console.print(f"[bold green]✔ Configuration Check Passed:[/bold green] {args.config}")
        for msg in messages:
            display.console.print(f"  • {msg}")
        return 0
    else:
        display.console.print(f"[bold red]✘ Configuration Check Failed:[/bold red] {args.config}")
        for err in messages:
            display.console.print(f"  [red]• {err}[/red]")
        return 1


def handle_server(args: argparse.Namespace, display: AegisDisplay) -> int:'''

assert handlers_hook in content, "handlers_hook not found"
content = content.replace(handlers_hook, new_handlers, 1)

# 4. Add dispatch in main()
old_dispatch = '''    elif args.subcommand=="server":
        return handle_server(args,display)'''

new_dispatch = '''    elif args.subcommand=="server":
        return handle_server(args,display)
    elif args.subcommand=="chat":
        return handle_chat(args,display)
    elif args.subcommand=="config":
        return handle_config(args,display)'''

assert old_dispatch in content, "old_dispatch not found"
content = content.replace(old_dispatch, new_dispatch, 1)

path.write_text(content, encoding="utf-8")
print("Successfully wired Phase 9 into aegis_os/cli/main.py")
