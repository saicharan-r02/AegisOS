from pathlib import Path

path = Path("aegis_os/cli/main.py")
content = path.read_text(encoding="utf-8")

# 1. Add parser after rewind_p
rewind_block = '''    rewind_p = subparsers.add_parser("rewind",help="Interactive time-travel rollback to step N")
    rewind_p.add_argument("step_index",type=int,help="Target step index to restore")
    rewind_p.add_argument("-s","--session-id",type=str,default=None,help="Session ID (defaults to most recent)")
    rewind_p.add_argument("--db-path",type=str,default=".aegis/checkpoints.db",help="Path to SQLite checkpoint database")'''

replay_parser_block = rewind_block + '''\n
    replay_p = subparsers.add_parser("replay",help="Replay a past mission step-by-step with zero LLM calls")
    replay_p.add_argument("session_id",type=str,help="Session ID of the mission to replay")
    replay_p.add_argument("--speed",type=float,default=0.3,help="Delay in seconds between steps (default: 0.3)")
    replay_p.add_argument("--db-path",type=str,default=".aegis/checkpoints.db",help="Path to SQLite checkpoint database")'''

assert rewind_block in content, "rewind_block not found"
content = content.replace(rewind_block, replay_parser_block, 1)

# 2. Add handle_replay before handle_benchmark
handle_rewind_end = '''    finally:
        store.close()'''

handle_replay_block = '''    finally:
        store.close()


def handle_replay(args: argparse.Namespace, display: AegisDisplay) -> int:
    """Replay historical mission step-by-step without LLM calls."""
    db = Path(args.db_path)
    if not db.exists():
        display.console.print(f"[red]Checkpoint database '{db}' does not exist.[/red]")
        return 1

    from aegis_os.tracing.replay import ReplayEngine
    engine = ReplayEngine(db_path=db)
    display.console.print(f"[bold cyan]▶ Replaying Mission {args.session_id} (speed={args.speed}s)...[/bold cyan]\\n")

    def on_step(idx: int, step):
        st_color = "green" if step.status.value == "SUCCESS" else "red"
        display.console.print(
            f"[bold cyan][Step {idx}][/bold cyan] [{step.role.value}] "
            f"{step.task_description or 'Executing action'} -> "
            f"[{st_color}]{step.status.value}[/{st_color}] ({step.duration_ms:.0f}ms)"
        )

    count = engine.replay_terminal(args.session_id, delay_sec=args.speed, step_callback=on_step)
    if count == 0:
        display.console.print(f"[yellow]No steps found for mission {args.session_id}.[/yellow]")
        return 1

    display.console.print(f"\\n[bold green]✔ Replay finished ({count} steps rendered with 0 LLM calls).[/bold green]")
    return 0'''

content = content.replace(handle_rewind_end, handle_replay_block, 1)

# 3. Add dispatch in main()
dispatch_rewind = '''    elif args.subcommand=="rewind":
        return handle_rewind(args,display)'''

dispatch_replay = dispatch_rewind + '''\n    elif args.subcommand=="replay":
        return handle_replay(args,display)'''

assert dispatch_rewind in content, "dispatch_rewind not found"
content = content.replace(dispatch_rewind, dispatch_replay, 1)

path.write_text(content, encoding="utf-8")
print("Successfully updated aegis_os/cli/main.py with replay support")
