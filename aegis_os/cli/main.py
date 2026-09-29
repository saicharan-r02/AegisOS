import argparse
from pathlib import Path
import sys
from typing import List,Optional

from aegis_os.agents.ops.agent import AegisOps
from aegis_os.agents.qa.agent import AegisQA
from aegis_os.agents.sec.agent import AegisSec
from aegis_os.cli.display import AegisDisplay
from aegis_os.kernel.checkpoint import CheckpointStore
from aegis_os.kernel.events import EventBus
from aegis_os.kernel.state import MissionStatus
from aegis_os.orchestrator.coordinator import MissionOrchestrator
from aegis_os.judge.dataset import get_golden_dataset
from aegis_os.judge.engine import AegisJudge
from aegis_os.judge.models import BenchmarkReport


def build_parser() -> argparse.ArgumentParser:
    """Construct command-line parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="aegis",
        description="AegisOS: Autonomous AI Engineering Organization CLI",
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Operational Subcommands")

    run_p = subparsers.add_parser("run",help="Launch an autonomous closed-loop engineering mission")
    run_p.add_argument("goal",type=str,help="High-level engineering objective or specification")
    run_p.add_argument("-w","--workspace",type=str,default=".",help="Target workspace root (default: current dir)")
    run_p.add_argument("-p","--provider",type=str,default="openai",help="LLM Provider: openai, groq, or ollama")
    run_p.add_argument("-m","--model",type=str,default=None,help="Model name identifier (e.g. gpt-4o, llama-3.3-70b-versatile)")
    run_p.add_argument("--max-repairs",type=int,default=3,help="Max closed-loop repair iterations (default: 3)")
    run_p.add_argument("--max-steps",type=int,default=50,help="Hard limit on total mission steps (default: 50)")
    run_p.add_argument("--db-path",type=str,default=".aegis/checkpoints.db",help="Path to SQLite checkpoint database")

    audit_p = subparsers.add_parser("audit",help="Run OWASP security audit and ops sanity checks")
    audit_p.add_argument("-w","--workspace",type=str,default=".",help="Target workspace root")
    audit_p.add_argument("-t","--target",type=str,default="aegis_os/",help="Target directory to audit")
    audit_p.add_argument("-p","--provider",type=str,default="openai",help="LLM Provider")
    audit_p.add_argument("-m","--model",type=str,default=None,help="Model identifier")

    test_p = subparsers.add_parser("test",help="Run QA test verification with structured diagnostic reporting")
    test_p.add_argument("-w","--workspace",type=str,default=".",help="Target workspace root")
    test_p.add_argument("-t","--target",type=str,default="tests/",help="Target test directory or file")
    test_p.add_argument("-p","--provider",type=str,default="openai",help="LLM Provider")
    test_p.add_argument("-m","--model",type=str,default=None,help="Model identifier")

    status_p = subparsers.add_parser("status",help="Inspect past mission runs or detailed step traces")
    status_p.add_argument("session_id",nargs="?",default=None,help="Optional session ID to inspect steps")
    status_p.add_argument("--db-path",type=str,default=".aegis/checkpoints.db",help="Path to SQLite checkpoint database")

    rollback_p = subparsers.add_parser("rollback",help="Revert a mission to a prior checkpoint snapshot")
    rollback_p.add_argument("session_id",type=str,help="Target session ID to rollback")
    rollback_p.add_argument("step_index",type=int,help="Target step index to restore")
    rollback_p.add_argument("--db-path",type=str,default=".aegis/checkpoints.db",help="Path to SQLite checkpoint database")

    benchmark_p = subparsers.add_parser("benchmark",help="Run AegisJudge evaluation suite")
    benchmark_p.add_argument("command", choices=["run"], help="Command to execute")
    benchmark_p.add_argument("-t","--task-id",type=str,default=None,help="Specific task ID to run (optional)")
    benchmark_p.add_argument("-p","--provider",type=str,default="openai",help="LLM Provider")
    benchmark_p.add_argument("-m","--model",type=str,default=None,help="Model identifier")

    return parser


def handle_run(args: argparse.Namespace, display: AegisDisplay) -> int:
    """Execute autonomous closed-loop mission."""
    ws=Path(args.workspace).resolve()
    db=Path(args.db_path)
    if not db.parent.exists():
        db.parent.mkdir(parents=True, exist_ok=True)

    display.show_banner()
    display.console.print(f"[bold cyan]Mission Objective:[/bold cyan] {args.goal}")
    display.console.print(f"[dim]Workspace: {ws} | Provider: {args.provider} | Max Repairs: {args.max_repairs}[/dim]\n")

    store = CheckpointStore(db_path=db)
    bus = EventBus()
    telemetry_listener = display.create_telemetry_handler()
    bus.subscribe("*", telemetry_listener)

    orchestrator = MissionOrchestrator(
        workspace_root=ws,
        llm_provider=args.provider,
        llm_model=args.model,
        checkpoint_store=store,
        event_bus=bus,
        max_repair_cycles=args.max_repairs,
        max_steps=args.max_steps,
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
    display.show_banner()
    display.console.print(f"[bold magenta]Starting Security & Reliability Audit on:[/bold magenta] {args.target}")

    sec=AegisSec(workspace_root=ws,llm_provider=args.provider,llm_model=args.model)
    ops=AegisOps(workspace_root=ws,llm_provider=args.provider,llm_model=args.model)

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
    display.show_banner()
    display.console.print(f"[bold yellow]Running AegisQA Test Suite on:[/bold yellow] {args.target}")

    qa=AegisQA(workspace_root=ws,llm_provider=args.provider,llm_model=args.model)
    report=qa.run_and_report(target=args.target)
    display.show_qa_report(report)

    return 0 if report.failed==0 and report.errors==0 else 1


def handle_status(args: argparse.Namespace, display: AegisDisplay) -> int:
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
        restored = store.rollback_to_step(args.session_id, args.step_index)
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


def handle_benchmark(args: argparse.Namespace, display: AegisDisplay) -> int:
    """Execute AegisJudge benchmarks."""
    display.show_banner()
    display.console.print("[bold cyan]Initializing AegisJudge Benchmarking Suite...[/bold cyan]")
    
    dataset = get_golden_dataset()
    if getattr(args, "task_id", None):
        dataset = [t for t in dataset if t.id == args.task_id]
        if not dataset:
            display.console.print(f"[bold red]Task '{args.task_id}' not found in golden dataset.[/bold red]")
            return 1
            
    judge = AegisJudge(provider=args.provider, model=args.model)
    report = BenchmarkReport()
    
    for task in dataset:
        display.console.print(f"\n[bold yellow]Running Task:[/bold yellow] {task.id} - {task.goal}")
        result = judge.run_task(task)
        report.results.append(result)
        
    display.show_benchmark_report(report)
    return 0 if report.pass_rate == 100.0 else 1


def main(argv: Optional[List[str]] = None) -> int:
    """CLI application entrypoint."""
    parser=build_parser()
    args=parser.parse_args(argv)

    display=AegisDisplay()

    if not args.subcommand:
        display.show_banner()
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
    elif args.subcommand=="benchmark":
        return handle_benchmark(args,display)
    return 0

if __name__=="__main__":
    sys.exit(main())