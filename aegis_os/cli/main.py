import argparse
import os

os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
import json
import sys
import threading
import urllib.request
from pathlib import Path

import uvicorn

from aegis_os.agents.ops.agent import AegisOps
from aegis_os.agents.qa.agent import AegisQA
from aegis_os.agents.sec.agent import AegisSec
from aegis_os.api import app, init_app
from aegis_os.cli.display import AegisDisplay
from aegis_os.kernel.checkpoint import CheckpointStore
from aegis_os.kernel.events import EventBus
from aegis_os.kernel.state import MissionStatus
from aegis_os.kernel.state_machine import MissionOrchestrator


def build_parser() -> argparse.ArgumentParser:
    """Construct command-line parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="aegis",
        description="AegisOS: Autonomous AI Engineering Organization CLI"
    )
    subparsers=parser.add_subparsers(dest="subcommand",help="Operational Subcommands")

    run_p = subparsers.add_parser("run",help="Launch an autonomous closed-loop engineering mission")
    run_p.add_argument("goal",type=str,help="High-level engineering objective or specification")
    run_p.add_argument("-w","--workspace",type=str,default=".",help="Target workspace root (default: current dir)")
    run_p.add_argument("-p","--provider",type=str,default=None,help="Override the configured role provider")
    run_p.add_argument("-m","--model",type=str,default=None,help="Override the configured role model ID")
    run_p.add_argument("--max-repairs",type=int,default=3,help="Max closed-loop repair iterations (default: 3)")
    run_p.add_argument("--max-steps",type=int,default=50,help="Hard limit on total mission steps (default: 50)")
    run_p.add_argument("--max-tokens",type=int,default=None,help="Mission token budget (defaults to aegis.toml)")
    run_p.add_argument("--max-cost-usd",type=float,default=None,help="Mission cost budget in USD (defaults to aegis.toml)")
    run_p.add_argument("--max-wall-seconds",type=float,default=None,help="Mission wall-clock budget (defaults to aegis.toml)")
    run_p.add_argument("--unsafe-local",action="store_true",help="Use host subprocess mode instead of Docker; command policy still applies.")
    run_p.add_argument("--strategy",type=str,default="adaptive",choices=["adaptive","waterfall"],help="Mission execution strategy: adaptive (DAG supervisor) or waterfall (legacy pipeline)")
    run_p.add_argument("--db-path",type=str,default=".aegis/checkpoints.db",help="Path to SQLite checkpoint database")

    audit_p=subparsers.add_parser("audit",help="Run OWASP security audit and ops sanity checks")
    audit_p.add_argument("-w","--workspace",type=str,default=".",help="Target workspace root")
    audit_p.add_argument("-t","--target",type=str,default="aegis_os/",help="Target directory to audit")
    audit_p.add_argument("-p","--provider",type=str,default=None,help="Override the configured role provider")
    audit_p.add_argument("-m","--model",type=str,default=None,help="Model identifier")
    audit_p.add_argument("--unsafe-local",action="store_true",help="Use host subprocess mode instead of Docker; command policy still applies.")

    test_p=subparsers.add_parser("test",help="Run QA test verification with structured diagnostic reporting")
    test_p.add_argument("-w","--workspace",type=str,default=".",help="Target workspace root")
    test_p.add_argument("-t","--target",type=str,default="tests/",help="Target test directory or file")
    test_p.add_argument("-p","--provider",type=str,default=None,help="Override the configured role provider")
    test_p.add_argument("-m","--model",type=str,default=None,help="Model identifier")
    test_p.add_argument("--unsafe-local",action="store_true",help="Use host subprocess mode instead of Docker; command policy still applies.")

    status_p=subparsers.add_parser("status",help="Inspect past mission runs or detailed step traces")
    status_p.add_argument("session_id",nargs="?",default=None,help="Optional session ID to inspect steps")
    status_p.add_argument("--db-path",type=str,default=".aegis/checkpoints.db",help="Path to SQLite checkpoint database")

    rollback_p = subparsers.add_parser("rollback",help="Revert a mission to a prior checkpoint snapshot")
    rollback_p.add_argument("session_id",type=str,help="Target session ID to rollback")
    rollback_p.add_argument("step_index",type=int,help="Target step index to restore")
    rollback_p.add_argument("--db-path",type=str,default=".aegis/checkpoints.db",help="Path to SQLite checkpoint database")
    rewind_p = subparsers.add_parser("rewind",help="Interactive time-travel rollback to step N")
    rewind_p.add_argument("step_index",type=int,help="Target step index to restore")
    rewind_p.add_argument("-s","--session-id",type=str,default=None,help="Session ID (defaults to most recent)")
    rewind_p.add_argument("--db-path",type=str,default=".aegis/checkpoints.db",help="Path to SQLite checkpoint database")

    replay_p = subparsers.add_parser("replay",help="Replay a past mission step-by-step with zero LLM calls")
    replay_p.add_argument("session_id",type=str,help="Session ID of the mission to replay")
    replay_p.add_argument("--speed",type=float,default=0.3,help="Delay in seconds between steps (default: 0.3)")
    replay_p.add_argument("--db-path",type=str,default=".aegis/checkpoints.db",help="Path to SQLite checkpoint database")

    benchmark_p = subparsers.add_parser("benchmark",help="Run AegisJudge evaluation suite")
    benchmark_p.add_argument("command", choices=["run"], help="Command to execute")
    benchmark_p.add_argument("-t","--task-id",type=str,default=None,help="Specific task ID to run (optional)")
    benchmark_p.add_argument("-p","--provider",type=str,default=None,help="Override the configured role provider")
    benchmark_p.add_argument("-m","--model",type=str,default=None,help="Model identifier")
    benchmark_p.add_argument("--unsafe-local",action="store_true",help="Use host subprocess mode instead of Docker; command policy still applies.")

    server_p = subparsers.add_parser("server",help="Launch the War Room Web Dashboard backend")
    server_p.add_argument("--host",type=str,default="127.0.0.1",help="Host IP to bind to")
    server_p.add_argument("--port",type=int,default=8000,help="Port to run on")
    server_p.add_argument("--db-path",type=str,default=".aegis/checkpoints.db",help="Path to SQLite checkpoint database")

    return parser


def handle_run(args: argparse.Namespace, display: AegisDisplay) -> int:
    """Execute autonomous closed-loop mission."""
    ws=Path(args.workspace).resolve()
    db=Path(args.db_path)
    if not db.parent.exists():
        db.parent.mkdir(parents=True, exist_ok=True)


    display.console.print(f"[bold cyan]Mission Objective:[/bold cyan] {args.goal}")
    if args.unsafe_local:
        display.console.print("[bold red]WARNING: UNSAFE LOCAL MODE — commands run on the host.[/bold red]")
    display.console.print(f"[dim]Workspace: {ws} | Provider: {args.provider or 'from aegis.toml'} | Max Repairs: {args.max_repairs}[/dim]\n")

    store = CheckpointStore(db_path=db)
    bus = EventBus()
    telemetry_listener = display.create_telemetry_handler()
    bus.subscribe("*", telemetry_listener)

    # HTTP bridge: forward events to the War Room dashboard if it's running
    _server_url = "http://127.0.0.1:8000"
    def _http_bridge(event) -> None:
        try:
            body = json.dumps({
                "event_type": event.__class__.__name__,
                "payload": event.model_dump(mode="json")
            }).encode()
            req = urllib.request.Request(
                f"{_server_url}/api/events/ingest",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=0.5)
        except Exception:
            pass  # server not running — silent skip
    bus.subscribe("*", lambda e: threading.Thread(target=_http_bridge, args=(e,), daemon=True).start())

    orchestrator = MissionOrchestrator(
        workspace_root=ws,
        llm_provider=args.provider,
        llm_model=args.model,
        checkpoint_store=store,
        event_bus=bus,
        max_repair_cycles=args.max_repairs,
        max_steps=args.max_steps,
        max_tokens=args.max_tokens,
        max_cost_usd=args.max_cost_usd,
        max_wall_seconds=args.max_wall_seconds,
        unsafe_local=args.unsafe_local,
        strategy=getattr(args, "strategy", "adaptive"),
    )

    summary=orchestrator.execute_mission(args.goal)

    display.console.print("\n")
    if summary.plan:
        display.show_plan(summary.plan)

    for repair in summary.repair_history:
        display.show_repair_cycle(repair)

    if summary.qa_report:
        display.show_qa_report(summary.qa_report)

    if summary.sec_report:
        display.show_sec_report(summary.sec_report)

    display.show_summary(summary)

    return 0 if summary.status==MissionStatus.COMPLETED else 1


def handle_audit(args: argparse.Namespace, display: AegisDisplay) -> int:
    """Execute security scan and ops sanity check."""
    ws=Path(args.workspace).resolve()

    display.console.print(f"[bold magenta]Starting Security & Reliability Audit on:[/bold magenta] {args.target}")

    if args.unsafe_local:
        display.console.print("[bold red]WARNING: UNSAFE LOCAL MODE — commands run on the host.[/bold red]")
    sec=AegisSec(workspace_root=ws,llm_provider=args.provider,llm_model=args.model)
    ops=AegisOps(workspace_root=ws,llm_provider=args.provider,llm_model=args.model,unsafe_local=args.unsafe_local)

    sec_report=sec.audit(target=args.target)
    display.show_sec_report(sec_report)

    ops_report=ops.health_check()
    display.console.print("\n[bold blue]AegisOps Reliability Check:[/bold blue]")
    display.console.print(ops_report)

    has_critical=(sec_report.summary.critical>0) or (sec_report.summary.high>0)
    return 1 if has_critical else 0


def handle_test(args: argparse.Namespace, display: AegisDisplay) -> int:
    """Execute QA test suite and display diagnostics."""
    ws=Path(args.workspace).resolve()

    display.console.print(f"[bold yellow]Running AegisQA Test Suite on:[/bold yellow] {args.target}")

    if args.unsafe_local:
        display.console.print("[bold red]WARNING: UNSAFE LOCAL MODE — commands run on the host.[/bold red]")
    qa=AegisQA(workspace_root=ws,llm_provider=args.provider,llm_model=args.model,unsafe_local=args.unsafe_local)
    report=qa.run_and_report(target=args.target)
    display.show_qa_report(report)

    return 0 if report.failed==0 and report.errors==0 else 1


def handle_status(args: argparse.Namespace,display: AegisDisplay) -> int:
    """List missions or inspect step history."""
    db=Path(args.db_path)
    if not db.exists():
        display.console.print(f"[yellow]No checkpoint database found at '{db}'.[/yellow]")
        return 0

    store=CheckpointStore(db_path=db)
    if args.session_id:
        steps=store.list_steps(args.session_id)
        if not steps:
            display.console.print(f"[yellow]No steps found for session '{args.session_id}'.[/yellow]")
        else:
            display.show_step_history(args.session_id, steps)
    else:
        missions=store.list_missions()
        if not missions:
            display.console.print("[dim]No past missions recorded yet.[/dim]")
        else:
            display.show_mission_list(missions)
    store.close()
    return 0


def handle_rollback(args: argparse.Namespace, display: AegisDisplay) -> int:
    """Revert mission to a prior checkpoint."""
    db=Path(args.db_path)
    if not db.exists():
        display.console.print(f"[red]Checkpoint database '{db}' does not exist.[/red]")
        return 1

    store=CheckpointStore(db_path=db)
    try:
        from aegis_os.timetravel.controller import TimeTravelController
        tt = TimeTravelController(workspace_root=Path.cwd(), checkpoint_store=store)
        restored, _ = tt.rollback(args.session_id, args.step_index)
        display.console.print(
            f"[bold green]✔ Successfully rolled back session '{args.session_id}' to Step {args.step_index}.[/bold green]"
        )
        display.console.print(f"Current Status: [bold cyan]{restored.status.value}[/bold cyan]")
        return 0
    except Exception as exc:
        display.console.print(f"[bold red]Rollback failed:[/bold red] {exc}")
        return 1
    finally:
        store.close()


def handle_replay(args: argparse.Namespace, display: AegisDisplay) -> int:
    """Replay historical mission step-by-step without LLM calls."""
    db = Path(args.db_path)
    if not db.exists():
        display.console.print(f"[red]Checkpoint database '{db}' does not exist.[/red]")
        return 1

    from aegis_os.tracing.replay import ReplayEngine
    engine = ReplayEngine(db_path=db)
    display.console.print(f"[bold cyan]▶ Replaying Mission {args.session_id} (speed={args.speed}s)...[/bold cyan]\n")

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

    display.console.print(f"\n[bold green]✔ Replay finished ({count} steps rendered with 0 LLM calls).[/bold green]")
    return 0
 
 
def handle_rewind(args: argparse.Namespace, display: AegisDisplay) -> int:
    """Interactive time-travel rewind to step N."""
    db = Path(args.db_path)
    if not db.exists():
        display.console.print(f"[red]Checkpoint database '{db}' does not exist.[/red]")
        return 1

    store = CheckpointStore(db_path=db)
    try:
        from aegis_os.timetravel.controller import TimeTravelController
        tt = TimeTravelController(workspace_root=Path.cwd(), checkpoint_store=store)
        restored, msg = tt.rewind(args.step_index, session_id=args.session_id)
        display.console.print(f"[bold green]✔ Rewound to Step {args.step_index}.[/bold green]")
        display.console.print(f"[dim]{msg}[/dim]")
        display.console.print(f"Session Status: [bold cyan]{restored.status.value}[/bold cyan]")
        return 0
    except Exception as exc:
        display.console.print(f"[bold red]Rewind failed:[/bold red] {exc}")
        return 1
    finally:
        store.close()


def handle_benchmark(args: argparse.Namespace, display: AegisDisplay) -> int:
    """Execute AegisJudge benchmarks."""

    display.console.print("[bold cyan]Initializing AegisJudge Benchmarking Suite...[/bold cyan]")

    try:
        from eval.dataset import get_golden_dataset
        from eval.engine import AegisJudge
        from eval.models import BenchmarkReport
    except ImportError as e:
        display.console.print(f"[bold red]Eval framework not available: {e}[/bold red]")
        return 1

    dataset = get_golden_dataset()
    if getattr(args, "task_id", None):
        dataset = [t for t in dataset if t.id == args.task_id]
        if not dataset:
            display.console.print(f"[bold red]Task '{args.task_id}' not found in golden dataset.[/bold red]")
            return 1

    if args.unsafe_local:
        display.console.print("[bold red]WARNING: UNSAFE LOCAL MODE — commands run on the host.[/bold red]")
    judge = AegisJudge(provider=args.provider, model=args.model,unsafe_local=args.unsafe_local)
    report = BenchmarkReport()

    for task in dataset:
        display.console.print(f"\n[bold yellow]Running Task:[/bold yellow] {task.id} - {task.goal}")
        result = judge.run_task(task)
        report.results.append(result)

    display.show_benchmark_report(report)
    return 0 if report.pass_rate == 100.0 else 1


def handle_server(args: argparse.Namespace, display: AegisDisplay) -> int:
    """Launch the FastAPI server."""
    db = Path(args.db_path)
    if not db.parent.exists():
        db.parent.mkdir(parents=True, exist_ok=True)

    display.console.print(f"[bold cyan]AegisOS War Room[/bold cyan]  http://{args.host}:{args.port}")
    display.console.print(f"[dim]Checkpoint DB : {db.resolve()}[/dim]")
    display.console.print("[dim]Press Ctrl+C to stop.[/dim]\n")

    init_app(db)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0



def main(argv: list[str] | None = None) -> int:
    """CLI application entrypoint."""
    parser=build_parser()
    args=parser.parse_args(argv)

    display=AegisDisplay()

    if not args.subcommand:
        parser.print_help()
        return 0

    if args.subcommand=="run":
        return handle_run(args,display)
    elif args.subcommand=="audit":
        return handle_audit(args,display)
    elif args.subcommand=="test":
        return handle_test(args,display)
    elif args.subcommand=="status":
        return handle_status(args,display)
    elif args.subcommand=="rollback":
        return handle_rollback(args,display)
    elif args.subcommand=="rewind":
        return handle_rewind(args,display)
    elif args.subcommand=="replay":
        return handle_replay(args,display)
    elif args.subcommand=="benchmark":
        return handle_benchmark(args,display)
    elif args.subcommand=="server":
        return handle_server(args,display)
    return 0

if __name__=="__main__":
    sys.exit(main())
