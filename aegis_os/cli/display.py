from typing import Any,Callable,List,Optional
from rich.console import Console,Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree
from aegis_os.agents.cto.agent import MissionPlan
from aegis_os.agents.qa.agent import TestReport
from aegis_os.agents.sec.agent import SecurityReport
from aegis_os.kernel.events import KernelEvent,MissionStatusChangedEvent,StateTransitionEvent,StepCompletedEvent,StepStartedEvent
from aegis_os.kernel.state import MissionStatus,StepRecord,StepStatus
from aegis_os.orchestrator.models import MissionSummary,RepairCycleRecord
from aegis_os.judge.models import BenchmarkReport


ROLE_COLORS={
    "CTO":"bold cyan",
    "DEV":"bold green",
    "QA":"bold yellow",
    "SEC":"bold magenta",
    "OPS":"bold blue",
}

STATUS_COLORS={
    "PENDING":"yellow",
    "RUNNING":"bold blue",
    "COMPLETED":"bold green",
    "FAILED":"bold red",
    "ABORTED":"bold red",
    "PAUSED":"yellow",
}

class AegisDisplay:
    """
    Rich visual presentation layer for AegisOS.
    Renders terminal banners, live telemetry streams, reports, and mission summaries.
    """
    def __init__(self,console: Optional[Console] = None) -> None:
        self.console=console or Console()

    def show_banner(self) -> None:
        banner_text=Text()
        banner_text.append("    ___    ______ _____ _____ _____ ____  _____\n", style="bold cyan")
        banner_text.append("   /   |  / ____// ___//_  _// ___// __ \\/ ___/\n", style="bold cyan")
        banner_text.append("  / /| | / __/  / (_ /  / / / (__)/ /_/ /\\__ \\ \n", style="bold blue")
        banner_text.append(" / ___ |/ /___ _\\__ \\ _/ / _\\__ \\/ ____/___/ / \n", style="bold blue")
        banner_text.append("/_/  |_/_____//____//___//____//_/    /____/  \n", style="bold magenta")
        banner_text.append("       Autonomous AI Engineering Organization\n\n", style="dim italic")

        badges=Text()
        badges.append(" Departments:  ",style="bold white")
        badges.append("[CTO Strategy] ",style="bold cyan on black")
        badges.append("[DEV Implementation] ",style="bold green on black")
        badges.append("[QA Verification] ",style="bold yellow on black")
        badges.append("[SEC Auditing] ",style="bold magenta on black")
        badges.append("[OPS Reliability]",style="bold blue on black")

        panel=Panel(
            Group(banner_text,badges),
            border_style="cyan",
            title="[bold white]AegisOS Mission Control[/bold white]",
            subtitle="[dim]Event-Driven Autonomous Kernel[/dim]",
        )
        self.console.print(panel)

    def show_plan(self,plan: MissionPlan) -> None:
        tree=Tree(f"[bold cyan]Mission Plan:[/bold cyan] {plan.mission_title}")
        tree.add(f"[dim]Objective:[/dim] {plan.objective}")

        tasks_branch=tree.add(f"[bold]Tasks ({len(plan.tasks)})[/bold]")
        for task in plan.tasks:
            role_style=ROLE_COLORS.get(task.assigned_to.replace("Aegis", "").upper(),"white")
            deps= f" [dim](depends on: {', '.join(task.depends_on)})[/dim]" if task.depends_on else ""
            task_node=tasks_branch.add(
                f"[bold yellow]{task.task_id}[/bold yellow]: {task.title} "
                f"[{role_style}][{task.assigned_to}][/{role_style}]{deps}"
            )
            task_node.add(f"[dim]{task.description}[/dim]")

        if plan.risk_flags:
            risks_branch=tree.add("[bold red]Identified Risk Flags[/bold red]")
            for risk in plan.risk_flags:
                risks_branch.add(f"[yellow]⚠ {risk}[/yellow]")

        self.console.print(Panel(tree,border_style="cyan",title="[bold cyan]Planning Phase[/bold cyan]"))

    def show_qa_report(self,report: TestReport) -> None:
        table=Table(title="AegisQA Test Verification Report",border_style="yellow")
        table.add_column("Passed",style="bold green",justify="center")
        table.add_column("Failed",style="bold red",justify="center")
        table.add_column("Errors",style="bold red",justify="center")
        table.add_column("Status",justify="center")

        status_text="[bold green]PASSING[/bold green]" if report.failed==0 and report.errors==0 else "[bold red]FAILING[/bold red]"
        table.add_row(str(report.passed),str(report.failed),str(report.errors),status_text)
        self.console.print(table)

        if report.findings:
            f_table=Table(title="Test Failure Diagnostics",border_style="red")
            f_table.add_column("Test Name",style="bold white")
            f_table.add_column("Error Message",style="red")
            f_table.add_column("Hypothesis",style="yellow")
            for f in report.findings:
                f_table.add_row(f.test_name,f.error_message[:80],f.root_cause_hypothesis[:80])
            self.console.print(f_table)

    def show_sec_report(self,report: SecurityReport) -> None:
        s=report.summary
        has_critical_or_high=(s.critical>0) or (s.high>0)
        border="red" if has_critical_or_high else "green"

        table=Table(title=f"AegisSec Security Audit: {report.audit_target}",border_style=border)
        table.add_column("Critical",style="bold red",justify="center")
        table.add_column("High",style="bold magenta",justify="center")
        table.add_column("Medium",style="bold yellow",justify="center")
        table.add_column("Low",style="bold blue",justify="center")
        table.add_column("Info",style="dim white",justify="center")
        table.add_row(str(s.critical),str(s.high),str(s.medium),str(s.low),str(s.info))
        self.console.print(table)

        if report.findings:
            f_table=Table(title="Security Vulnerabilities",border_style="red")
            f_table.add_column("ID",style="bold white",width=10)
            f_table.add_column("Severity",justify="center",width=10)
            f_table.add_column("Category",style="cyan",width=18)
            f_table.add_column("Location",style="yellow",width=20)
            f_table.add_column("Description",style="white")
            f_table.add_column("Remediation",style="green")

            for f in report.findings:
                sev_style="bold red" if f.severity in ("CRITICAL","HIGH") else "yellow"
                loc=f"{f.file}:{f.line}" if f.line else f.file
                f_table.add_row(
                    f.id,
                    f"[{sev_style}]{f.severity}[/{sev_style}]",
                    f.category,
                    loc,
                    f.description,
                    f.remediation,
                )
            self.console.print(f_table)

    def show_repair_cycle(self,record: RepairCycleRecord) -> None:
        status_text="[bold green]RESOLVED[/bold green]" if record.resolved else "[bold yellow]IN PROGRESS[/bold yellow]"
        title=f"Closed-Loop Repair Cycle #{record.cycle_index} ({status_text})"

        body=Text()
        body.append(f"Trigger: {record.trigger}\n",style="bold yellow")
        body.append("Issues Detected:\n",style="bold white")
        for issue in record.issues_detected:
            body.append(f"  •{issue}\n",style="red")

        if record.dev_patch_summary:
            body.append("\nAegisDev Patch Summary:\n",style="bold green")
            body.append(f"{record.dev_patch_summary}\n",style="dim green")

        self.console.print(Panel(body, border_style="magenta", title=title))

    def show_summary(self, summary: MissionSummary) -> None:
        status_style=STATUS_COLORS.get(summary.status.value,"white")
        title=f"[bold white]Mission Summary:[/bold white] [{status_style}]{summary.status.value}[/{status_style}]"

        text=Text()
        text.append(f"Session ID:       {summary.session_id}\n",style="dim")
        text.append(f"Objective:        {summary.goal}\n",style="bold white")
        text.append(f"Duration:         {summary.duration_seconds:.2f}s\n",style="cyan")
        text.append(f"Total Steps:      {summary.total_steps}\n",style="cyan")
        text.append(f"Tasks Executed:   {', '.join(summary.tasks_executed) if summary.tasks_executed else 'None'}\n",style="yellow")
        text.append(f"Repair Cycles:    {summary.repair_cycles}\n",style="magenta")

        if summary.qa_report:
            text.append(
                f"QA Final Result:  {summary.qa_report.passed} passed, {summary.qa_report.failed} failed, {summary.qa_report.errors} errors\n",
                style="green" if summary.qa_report.failed==0 else "red"
            )
        if summary.sec_report:
            s=summary.sec_report.summary
            text.append(
                f"Sec Final Audit:  {s.critical} critical, {s.high} high, {s.medium} medium, {s.low} low\n",
                style="green" if s.critical==0 and s.high==0 else "red"
            )
        if summary.ops_report:
            text.append(f"Ops Sanity Check: {summary.ops_report[:100]}...\n",style="blue")
        if summary.error:
            text.append(f"\nTerminal Error:   {summary.error}\n",style="bold red")

        border="green" if summary.status==MissionStatus.COMPLETED else "red"
        self.console.print(Panel(text,border_style=border,title=title))

    def show_mission_list(self,missions: List[dict[str,Any]]) -> None:
        table=Table(title="AegisOS Past Mission Sessions",border_style="cyan")
        table.add_column("Session ID",style="bold white",width=36)
        table.add_column("Goal", style="yellow", width=30)
        table.add_column("Status", justify="center", width=12)
        table.add_column("Steps", justify="center", width=8)
        table.add_column("Last Updated", style="dim", width=25)

        for m in missions:
            status_style=STATUS_COLORS.get(str(m.get("status")),"white")
            table.add_row(
                str(m.get("session_id")),
                str(m.get("goal", ""))[:30],
                f"[{status_style}]{m.get('status')}[/{status_style}]",
                str(m.get("current_step_index",0)),
                str(m.get("updated_at", ""))[:19]
            )
        self.console.print(table)

    def show_step_history(self, session_id: str, steps: List[StepRecord]) -> None:
        table = Table(title=f"Execution Step History for Session: {session_id}", border_style="blue")
        table.add_column("#", justify="center", width=4)
        table.add_column("Role", justify="center", width=8)
        table.add_column("Task Description", style="white")
        table.add_column("Tool", style="cyan", width=18)
        table.add_column("Status", justify="center", width=10)
        table.add_column("Duration", justify="right", width=10)

        for step in steps:
            role_style = ROLE_COLORS.get(step.role.value, "white")
            status_style = "green" if step.status == StepStatus.SUCCESS else "red"
            dur = f"{step.duration_ms:.1f}ms" if step.duration_ms is not None else "-"
            table.add_row(
                str(step.step_index),
                f"[{role_style}]{step.role.value}[/{role_style}]",
                step.task_description[:50],
                step.tool_name or "-",
                f"[{status_style}]{step.status.value}[/{status_style}]",
                dur
            )
        self.console.print(table)

    def create_telemetry_handler(self) -> Callable[[KernelEvent], None]:
        def handle_event(event: KernelEvent) -> None:
            if isinstance(event, StateTransitionEvent):
                from_str = f"[{event.from_role.value}]" if event.from_role else "[None]"
                to_str = f"[{event.to_role.value}]"
                from_style = ROLE_COLORS.get(event.from_role.value, "white") if event.from_role else "dim"
                to_style = ROLE_COLORS.get(event.to_role.value, "white")
                self.console.print(
                    f"  [bold]➜ Control handoff:[/bold] "
                    f"[{from_style}]{from_str}[/{from_style}] ➔ "
                    f"[{to_style}]{to_str}[/{to_style}] (Step {event.step_index})"
                )
            elif isinstance(event, StepStartedEvent):
                role_style=ROLE_COLORS.get(event.step.role.value, "white")
                tool_info=f" [cyan]call: {event.step.tool_name}[/cyan]" if event.step.tool_name else ""
                self.console.print(
                    f"    [dim]● Step {event.step.step_index}[/dim] "
                    f"[{role_style}][{event.step.role.value}][/{role_style}] "
                    f"{event.step.task_description[:65]}{tool_info}"
                )
            elif isinstance(event, StepCompletedEvent):
                if event.step.status == StepStatus.SUCCESS:
                    dur = f"{event.step.duration_ms:.0f}ms" if event.step.duration_ms else "ok"
                    self.console.print(f"      [green]✔ Success ({dur})[/green]")
                else:
                    err = event.step.error or "Step failed"
                    self.console.print(f"      [red]✘ Failed: {err[:80]}[/red]")
            elif isinstance(event, MissionStatusChangedEvent):
                old_style = STATUS_COLORS.get(event.old_status.value, "white")
                new_style = STATUS_COLORS.get(event.new_status.value, "white")
                self.console.print(
                    f"[bold]★ Mission Status:[/bold] "
                    f"[{old_style}]{event.old_status.value}[/{old_style}] ➔ "
                    f"[{new_style}]{event.new_status.value}[/{new_style}]"
                )

        return handle_event

    def show_benchmark_report(self, report: BenchmarkReport) -> None:
        table = Table(title="AegisJudge Benchmark Results", border_style="cyan")
        table.add_column("Task ID", style="bold white")
        table.add_column("Pass/Fail", justify="center")
        table.add_column("Pass@1", justify="center")
        table.add_column("Cycles", justify="right", style="magenta")
        table.add_column("Steps", justify="right", style="blue")
        table.add_column("Duration", justify="right", style="green")

        for r in report.results:
            status_str = "[bold green]PASS[/bold green]" if r.passed else "[bold red]FAIL[/bold red]"
            p1_str = "[green]Yes[/green]" if r.pass_at_1 else "[dim]No[/dim]"
            
            table.add_row(
                r.task_id,
                status_str,
                p1_str,
                str(r.repair_cycles),
                str(r.total_steps),
                f"{r.duration_sec:.1f}s"
            )
        
        self.console.print(table)
        
        summary_text = Text()
        summary_text.append(f"Total Tasks:  {report.total_tasks}\n", style="white")
        summary_text.append(f"Passed Tasks: {report.passed_tasks}\n", style="green")
        summary_text.append(f"Pass Rate:    {report.pass_rate:.1f}%\n", style="bold cyan")
        
        self.console.print(Panel(summary_text, title="Benchmark Summary", border_style="cyan"))